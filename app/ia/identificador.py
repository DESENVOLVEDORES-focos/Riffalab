"""Identificação musical com a Groq + conferência na MusicBrainz.

Divisão de responsabilidades (proposta §7):

    yt-dlp    → acha o vídeo e o melhor áudio   (não muda nada aqui)
    FFmpeg    → converte para MP3               (não muda nada aqui)
    GROQ      → identifica a música e o álbum   (este módulo)
    MusicBrainz / Cover Art Archive
              → CONFIRMA o álbum e fornece a capa oficial
    Mutagen   → grava os metadados              (não muda nada aqui)

Regra contra invenção: o modelo é instruído a devolver `null` quando não sabe,
e o que ele responde passa por três filtros antes de virar tag:

1. **saneamento** (`_limpar`): tipos, faixas de valor, texto vazio → vazio;
2. **conferência na MusicBrainz**: se o álbum não existir lá com aquele artista,
   o dado continua marcado como NÃO verificado (e a capa não é usada);
3. **prioridade**: o que veio da IA só sobrescreve título/artista se o campo
   estiver coerente; nunca apaga informação confirmada por iTunes/MusicBrainz.

Sem chave ou com a IA desligada, `identificar()` devolve `ok=False` e o pipeline
segue o caminho antigo — o download nunca quebra por causa da IA.
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

from ..config import Config
from ..models import Identificacao, TrackResult
from ..metadata import musicbrainz
from ..texto import normalizar
from . import cliente_groq

SISTEMA = (
    "Você é um especialista em catalogação musical (bancos como MusicBrainz, "
    "Discogs e AllMusic). Recebe dados de um vídeo musical e deve identificar a "
    "GRAVAÇÃO que ele contém, separando com rigor os papéis.\n\n"
    "REGRAS OBRIGATÓRIAS:\n"
    "1. NUNCA invente. Se não tiver certeza de um dado, devolva null (ou lista "
    "vazia). É preferível um campo vazio a um campo errado.\n"
    "2. Não confunda papéis: 'artista' é quem interpreta; 'banda' é o grupo, se "
    "houver; 'compositores' escreveram a música; 'letristas' escreveram a letra; "
    "'produtores' produziram a gravação. Se o vídeo é de um canal que não é o "
    "artista (ex.: canal de covers, canal de selo, canal Topic), não use o nome "
    "do canal como artista sem confirmar.\n"
    "3. 'album' deve ser o ÁLBUM ORIGINAL em que essa gravação foi lançada. Se a "
    "gravação é ao vivo, o álbum é o álbum ao vivo correspondente (se existir).\n"
    "4. Detecte a versão a partir do título do vídeo (Live, Ao Vivo, Remaster, "
    "Acoustic, Cover, Remix, Demo, Instrumental, Edit) e preencha 'versao' com "
    "um destes valores: estudio, ao vivo, remaster, acustico, cover, remix, "
    "demo, instrumental, edit, desconhecido.\n"
    "5. 'artistas_participantes' são convidados/featuring creditados; não repita "
    "o artista principal.\n"
    "6. 'confianca' é sua confiança real na identificação como um todo, de 0 a 1.\n"
    "7. Liste em 'campos_incertos' o nome dos campos que você preencheu com menos "
    "de 80% de certeza.\n"
    "8. 'ano' e 'data_lancamento' se referem ao lançamento ORIGINAL da gravação.\n"
    "9. Responda SOMENTE com o JSON do schema, sem comentários e sem cercas de código."
)

ESQUEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["identificado", "confianca", "titulo", "artista", "banda",
                 "artistas_participantes", "compositores", "letristas", "produtores",
                 "album", "ano", "data_lancamento", "genero", "faixa", "gravadora",
                 "isrc", "mbid_gravacao", "versao", "campos_incertos", "observacoes"],
    "properties": {
        "identificado": {"type": "boolean"},
        "confianca": {"type": "number"},
        "titulo": {"type": ["string", "null"]},
        "artista": {"type": ["string", "null"]},
        "banda": {"type": ["string", "null"]},
        "artistas_participantes": {"type": "array", "items": {"type": "string"}},
        "compositores": {"type": "array", "items": {"type": "string"}},
        "letristas": {"type": "array", "items": {"type": "string"}},
        "produtores": {"type": "array", "items": {"type": "string"}},
        "album": {"type": ["string", "null"]},
        "ano": {"type": ["integer", "null"]},
        "data_lancamento": {"type": ["string", "null"]},
        "genero": {"type": ["string", "null"]},
        "faixa": {"type": ["integer", "null"]},
        "gravadora": {"type": ["string", "null"]},
        "isrc": {"type": ["string", "null"]},
        "mbid_gravacao": {"type": ["string", "null"]},
        "versao": {"type": ["string", "null"]},
        "campos_incertos": {"type": "array", "items": {"type": "string"}},
        "observacoes": {"type": ["string", "null"]},
    },
}


# --------------------------------------------------------------------- utilidades
def _texto(valor: Any) -> str:
    if valor is None:
        return ""
    return " ".join(str(valor).split()).strip()


def _lista(valor: Any) -> List[str]:
    if not valor:
        return []
    if isinstance(valor, str):
        valor = [valor]
    saida, vistos = [], set()
    for item in valor:
        nome = _texto(item)
        chave = normalizar(nome)
        if nome and chave not in vistos:
            vistos.add(chave)
            saida.append(nome)
    return saida


def _ano(valor: Any) -> Optional[int]:
    try:
        numero = int(str(valor)[:4])
    except (TypeError, ValueError):
        return None
    return numero if 1900 <= numero <= time.gmtime().tm_year + 1 else None


def _faixa(valor: Any) -> Optional[int]:
    try:
        numero = int(valor)
    except (TypeError, ValueError):
        return None
    return numero if 1 <= numero <= 300 else None


def _data(valor: Any, ano: Optional[int]) -> str:
    texto = _texto(valor)
    if len(texto) == 10 and texto[4] == "-" and texto[7] == "-":
        return texto
    return f"{ano}" if ano else ""


def montar_pedido(resultado: TrackResult) -> str:
    """Só o necessário — nunca cookies, nunca credenciais (proposta §9)."""
    dados = {
        "titulo_do_video": resultado.titulo,
        "canal": resultado.extra.get("canal") or resultado.artista,
        "url": resultado.pagina_url,
        "duracao_segundos": int(resultado.duracao_s or 0),
        "titulo_sugerido_pela_busca": resultado.titulo,
        "artista_sugerido_pela_busca": resultado.artista,
        "album_sugerido": resultado.album or None,
        "ano_sugerido": resultado.ano,
    }
    return ("Identifique a música deste vídeo. Dados disponíveis:\n"
            + json.dumps(dados, ensure_ascii=False, indent=2))


def _conferir_musicbrainz(ident: Identificacao) -> None:
    """Confirma o álbum na MusicBrainz e guarda o mbid do release-group."""
    if not ident.album:
        return
    try:
        grupos = musicbrainz.buscar_release_group(ident.album, ident.artista, ident.ano)
    except Exception:                                             # noqa: BLE001
        return
    if not grupos:
        ident.campos_incertos = sorted(set(ident.campos_incertos + ["album"]))
        return
    melhor = grupos[0]
    ident.verificado_musicbrainz = True
    ident.mbid_release_group = melhor.get("mbid") or ""
    # a MusicBrainz é a fonte de verdade do nome do álbum
    if melhor.get("album"):
        ident.album = melhor["album"]
    if not ident.ano and melhor.get("ano"):
        ident.ano = melhor["ano"]


# ------------------------------------------------------------------- principal
def identificar(resultado: TrackResult, config: Config,
                progresso=None) -> Identificacao:
    """Identifica a música com a Groq. Nunca levanta exceção."""
    inicio = time.time()
    ok, motivo = cliente_groq.disponivel(config)
    if not ok:
        return Identificacao(ok=False, erro=motivo, origem="groq")

    if progresso:
        try:
            progresso(55, "identificando música com IA…")
        except Exception:                                         # noqa: BLE001
            pass

    try:
        bruto, modelo = cliente_groq.completar_json(
            config, SISTEMA, montar_pedido(resultado), ESQUEMA)
    except cliente_groq.ErroGroq as exc:
        return Identificacao(ok=False, erro=str(exc), origem="groq",
                             segundos=round(time.time() - inicio, 1))
    except Exception as exc:                                      # noqa: BLE001
        return Identificacao(ok=False, erro=f"{exc.__class__.__name__}: {exc}",
                             origem="groq", segundos=round(time.time() - inicio, 1))

    ident = Identificacao(
        ok=bool(bruto.get("identificado")),
        origem="groq",
        modelo=modelo,
        confianca=max(0.0, min(1.0, float(bruto.get("confianca") or 0))),
        titulo=_texto(bruto.get("titulo")),
        artista=_texto(bruto.get("artista")),
        banda=_texto(bruto.get("banda")),
        artistas_participantes=_lista(bruto.get("artistas_participantes")),
        compositores=_lista(bruto.get("compositores")),
        letristas=_lista(bruto.get("letristas")),
        produtores=_lista(bruto.get("produtores")),
        album=_texto(bruto.get("album")),
        ano=_ano(bruto.get("ano")),
        genero=_texto(bruto.get("genero")),
        faixa=_faixa(bruto.get("faixa")),
        gravadora=_texto(bruto.get("gravadora")),
        isrc=_texto(bruto.get("isrc")),
        mbid_gravacao=_texto(bruto.get("mbid_gravacao")),
        versao=_texto(bruto.get("versao")).lower() or "desconhecido",
        campos_incertos=sorted(set(_lista(bruto.get("campos_incertos")))),
        observacoes=_texto(bruto.get("observacoes")),
        segundos=round(time.time() - inicio, 1),
    )
    ident.data_lancamento = _data(bruto.get("data_lancamento"), ident.ano)

    # sem título ou sem artista a identificação não serve para nada
    if not ident.titulo or not ident.artista:
        ident.ok = False
        ident.erro = "a IA não confirmou título e artista"

    if ident.ok:
        _conferir_musicbrainz(ident)
    return ident

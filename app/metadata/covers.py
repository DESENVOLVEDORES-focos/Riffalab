"""Busca de candidatos de capa e cache local.

Sem revisão, apenas singles são candidatos. Na tela de revisão, também
aparecem álbuns e coleções. Classificações podem estar erradas, por isso
as imagens devem ser conferidas pelo usuário.
"""
from __future__ import annotations

import hashlib
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..config import PASTA_CACHE_CAPAS
from ..image_utils import dimensoes, eh_imagem, extensao
from ..models import CoverResult
from ..texto import normalizar
from . import itunes, musicbrainz

UA = "RiffLab/0.1 (uso local)"
TIMEOUT = 30


# ------------------------------------------------------------------ download
def baixar_imagem(url: str, timeout: int = TIMEOUT) -> Optional[bytes]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            dados = resp.read()
        if len(dados) < 1024 or not eh_imagem(dados):
            return None
        return dados
    except Exception as exc:
        from ..logging_setup import registrar_erro
        registrar_erro('Baixar imagem de capa', f'{type(exc).__name__}: {exc}')
        return None


def caminho_cache(url: str, dados: bytes) -> Path:
    PASTA_CACHE_CAPAS.mkdir(parents=True, exist_ok=True)
    chave = hashlib.sha1(url.encode("utf-8")).hexdigest()[:20]
    return PASTA_CACHE_CAPAS / f"{chave}{extensao(dados)}"


def salvar_cache(url: str, dados: bytes) -> Path:
    destino = caminho_cache(url, dados)
    if not destino.exists():
        destino.write_bytes(dados)
    return destino


def copiar_para_capas(origem: Path, titulo: str, artista: str, album: str) -> Path:
    """Guarda uma cópia com nome legível em capas/ (além do cache)."""
    from ..organizer import sanitizar
    nome = sanitizar(f"{artista or 'Artista'} - {album or titulo or 'capa'}{origem.suffix}", limite=100)
    destino = origem.parent.parent / nome
    try:
        if not destino.exists():
            destino.write_bytes(origem.read_bytes())
    except OSError:
        return origem
    return destino


# ------------------------------------------------------------------ principal
def _padrao_fontes(fontes: Optional[List[str]]) -> List[str]:
    return ["coverartarchive", "itunes", "deezer"] if fontes is None else fontes


def candidatos_capa(
    titulo: str,
    artista: str = "",
    album: str = "",
    ano: Optional[int] = None,
    fontes: Optional[List[str]] = None,
    minimo_lado: int = 300,
    thumb_extra: str = "",
    usar_miniatura: bool = False,
    identificacao=None,
    exigir_quadrada: bool = False,
    incluir_albuns_para_revisao: bool = False,
) -> Tuple[CoverResult, List[CoverResult]]:
    """(melhor capa, alternativas) — todas já baixadas e validadas.

    É isso que permite a tela de confirmação (proposta §2): o usuário vê a
    imagem, o álbum, o artista, o ano, a fonte e o grau de correspondência, e
    pode trocar por outra opção ou recusar a capa.
    """
    from . import busca_capas

    aprovadas, reprovadas = busca_capas.coletar(
        titulo, artista, album, ano, fontes=_padrao_fontes(fontes),
        minimo_lado=minimo_lado, thumb_extra=thumb_extra,
        usar_miniatura=usar_miniatura, identificacao=identificacao,
        exigir_quadrada=exigir_quadrada, incluir_albuns_para_revisao=incluir_albuns_para_revisao)

    if not aprovadas:
        if not titulo or not artista:
            motivo = ("É preciso informar título e artista para procurar capa. "
                      "Em Downloads, use Editar dados e tente novamente.")
        elif not _padrao_fontes(fontes):
            motivo = ("Nenhuma fonte de capa está ativada. Ative fontes em Configurações "
                      "ou escolha uma imagem salva.")
        else:
            if incluir_albuns_para_revisao:
                motivo = ("Nenhuma capa de álbum ou single identificada com confiança. "
                          "Os serviços podem não responder ou não ter resultados compatíveis. "
                          "Você pode escolher uma imagem salva ou colada, ou seguir sem capa.")
                tipo_indefinido = 'não foi possível confirmar que é álbum ou single'
                nome_tipo = 'sem tipo de álbum ou single confirmado'
            else:
                motivo = ("Nenhuma capa de single identificada com confiança. Os serviços podem "
                          "não responder ou não ter um single reconhecido. Não usamos capa de álbum "
                          "como substituta; escolha uma imagem salva ou siga sem capa.")
                tipo_indefinido = 'não foi possível confirmar que a capa é de um single'
                nome_tipo = 'sem confirmação de single'
            sem_tipo = sum(a.motivo == tipo_indefinido for a in reprovadas)
            outras = len(reprovadas) - sem_tipo
            if reprovadas:
                motivo += (f" Candidatos descartados: {sem_tipo} {nome_tipo}"
                           f" e {outras} por imagem ou correspondência.")
            else:
                motivo += " Nenhum candidato chegou à avaliação; veja erros das fontes na janela de iniciar."
        return CoverResult(observacao=motivo), []

    resultados = [a.como_cover_result() for a in aprovadas]
    melhor = resultados[0]
    return melhor, resultados[1:]


def encontrar_capa(
    titulo: str,
    artista: str = "",
    album: str = "",
    ano: Optional[int] = None,
    fontes: Optional[List[str]] = None,
    minimo_lado: int = 300,
    thumb_extra: str = "",
    sobrescrever_cache: bool = False,
    identificacao=None,
    usar_miniatura: bool = False,
    incluir_albuns_para_revisao: bool = False,
) -> CoverResult:
    """Devolve a melhor capa encontrada (com caminho local) ou CoverResult vazio.

    `identificacao` pode complementar artista e outros dados. O álbum e a
    miniatura não são usados como capa substituta automática; álbuns só
    são incluídos quando solicitados para revisão explícita.
    """
    if sobrescrever_cache:
        _limpar_cache_urls()
    melhor, alternativas = candidatos_capa(
        titulo, artista, album, ano=ano, fontes=fontes, minimo_lado=minimo_lado,
        thumb_extra=thumb_extra, usar_miniatura=usar_miniatura,
        identificacao=identificacao, incluir_albuns_para_revisao=incluir_albuns_para_revisao)
    melhor.alternativas = alternativas
    return melhor


def _limpar_cache_urls() -> None:
    """Forçar nova busca: apaga as imagens em cache (só as de capa)."""
    try:
        for arq in PASTA_CACHE_CAPAS.iterdir():
            if arq.is_file():
                arq.unlink()
    except OSError:
        pass


def _genero_canonico(genero: str) -> str:
    nomes = {'rock':'Rock', 'pop':'Pop', 'hard rock':'Hard Rock',
             'heavy metal':'Heavy Metal', 'metal':'Metal', 'jazz':'Jazz',
             'blues':'Blues', 'hip hop':'Hip-Hop', 'r b soul':'R&B/Soul'}
    genero = str(genero or '').strip()
    return nomes.get(normalizar(genero), genero)


def metadados_completos(titulo: str, artista: str = "", album: str = "",
                         ano: Optional[int] = None) -> Dict[str, Any]:
    """Procura a gravação e um álbum vinculado; não toma a sugestão como prova."""
    from ..texto import limpar_titulo_tags, normalizar
    from . import album_original
    from .correspondencia import identidade_metadados, pontuar
    titulo = limpar_titulo_tags(titulo)
    dados: Dict[str, Any] = {"titulo": titulo, "artista": artista, "album": "",
                             "ano": None, "faixa": None, "total_faixas": None,
                             "disco": None, "genero": "", "artista_album": "", "fontes": []}
    original = album_original.encontrar(titulo, artista)
    if original.get('album'):
        for chave in ('titulo', 'artista', 'album', 'ano', 'faixa', 'total_faixas', 'disco', 'genero', 'artista_album'):
            if original.get(chave):
                dados[chave] = original[chave]
        dados['fontes'].append('musicbrainz')
    try:
        it = itunes.melhor_faixa(titulo, artista, dados['album'])
    except Exception as exc:
        from ..logging_setup import registrar_erro
        registrar_erro('Metadados iTunes', f'{type(exc).__name__}: {exc}')
        it = None
    if it and (not identidade_metadados(titulo, artista, it)
               or not pontuar(titulo, artista, cand=it).aprovado):
        it = None
    if it:
        dados['fontes'].append('itunes')
        dados['titulo'] = limpar_titulo_tags(it.get('titulo') or titulo)
        dados['artista'] = it.get('artista') or artista
        # Gênero é do catálogo para a mesma faixa; a IA não o substitui.
        if it.get('genero'):
            dados['genero'] = it['genero']
        # Um número de faixa só pertence à edição correspondente, não a uma
        # coletânea/remaster com o mesmo nome de música.
        mesmo_album = (dados['album'] and normalizar(it.get('album') or '') == normalizar(dados['album']))
        if mesmo_album and it.get('ano') and it.get('ano') == dados['ano']:
            for chave in ('faixa', 'total_faixas', 'disco', 'artista_album'):
                if not dados.get(chave) and it.get(chave):
                    dados[chave] = it[chave]
    dados['genero'] = _genero_canonico(dados['genero'])
    return dados


def limpar_cache(dias: int = 30) -> int:
    """Remove imagens antigas do cache. Devolve quantas foram removidas."""
    if not PASTA_CACHE_CAPAS.exists():
        return 0
    limite = time.time() - dias * 86400
    removidos = 0
    for arq in PASTA_CACHE_CAPAS.iterdir():
        try:
            if arq.is_file() and arq.stat().st_mtime < limite:
                arq.unlink()
                removidos += 1
        except OSError:
            continue
    return removidos

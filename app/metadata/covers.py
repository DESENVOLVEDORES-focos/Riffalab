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


def metadados_completos(titulo: str, artista: str = "", album: str = "",
                         ano: Optional[int] = None) -> Dict[str, Any]:
    """Cruza iTunes + MusicBrainz para preencher o máximo de metadados."""
    dados: Dict[str, Any] = {"titulo": titulo, "artista": artista, "album": album,
                             "ano": ano, "faixa": None, "total_faixas": None,
                             "disco": None, "genero": "", "artista_album": "", "fontes": []}
    try:
        it = itunes.melhor_faixa(titulo, artista, album)
    except Exception:
        it = None
    if it:
        from .correspondencia import pontuar
        if not pontuar(titulo, artista, album, cand=it).aprovado:
            it = None
    if it:
        dados["fontes"].append("itunes")
        # Só normalizar a identidade com uma correspondência forte e a mesma versão.
        from ..texto import similaridade
        from .correspondencia import pontuar
        if (titulo and artista and similaridade(titulo, it.get("titulo") or "") >= .90
                and similaridade(artista, it.get("artista") or "") >= .90
                and pontuar(titulo, artista, cand=it).aprovado):
            dados["titulo"] = it.get("titulo") or titulo
            dados["artista"] = it.get("artista") or artista
        for chave in ("titulo", "artista", "album", "ano", "faixa", "total_faixas", "disco", "genero", "artista_album"):
            if not dados.get(chave) and it.get(chave):
                dados[chave] = it[chave]
        dados["capa_url"] = it.get("capa_url")

    if not dados.get("album") or not dados.get("faixa") or not dados.get("genero") or not dados.get("artista_album"):
        try:
            for grav in musicbrainz.buscar_gravacao(titulo, artista, album, limite=3):
                from ..texto import similaridade
                from .correspondencia import pontuar
                if not pontuar(titulo, artista, cand=grav).aprovado:
                    continue
                if dados.get("album") and similaridade(dados["album"], grav.get("album") or "") < .80:
                    continue
                det = musicbrainz.detalhes_release(grav.get("release_id", ""), titulo) if grav.get("release_id") else {}
                if det:
                    dados["fontes"].append("musicbrainz")
                    for chave in ("album", "ano", "faixa", "total_faixas", "genero", "artista_album"):
                        if not dados.get(chave) and det.get(chave):
                            dados[chave] = det[chave]
                    break
        except Exception:
            pass

    if dados.get("genero") and isinstance(dados["genero"], str):
        dados["genero"] = dados["genero"].strip()
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

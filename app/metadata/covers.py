"""Busca de candidatos de capa de single e cache local.

Apenas lançamentos identificados pelo catálogo como single são candidatos.
Não há substituição automática por álbum ou miniatura. Classificações podem
estar erradas, por isso as imagens devem ser conferidas pelo usuário.
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
    except Exception:
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
) -> Tuple[CoverResult, List[CoverResult]]:
    """(melhor capa, alternativas) — todas já baixadas e validadas.

    É isso que permite a tela de confirmação (proposta §2): o usuário vê a
    imagem, o álbum, o artista, o ano, a fonte e o grau de correspondência, e
    pode trocar por outra opção ou recusar a capa.
    """
    from . import busca_capas

    aprovadas, _reprovadas = busca_capas.coletar(
        titulo, artista, album, ano, fontes=_padrao_fontes(fontes),
        minimo_lado=minimo_lado, thumb_extra=thumb_extra,
        usar_miniatura=usar_miniatura, identificacao=identificacao,
        exigir_quadrada=exigir_quadrada)

    if not aprovadas:
        if not artista and not album:
            motivo = ("artista e álbum não confirmados: capa não aplicada para não "
                      "pegar a capa de outra música com o mesmo nome")
        else:
            motivo = ("Nenhuma capa de single identificada com confiança. "
                      "Não substituímos pela capa de álbum; escolha imagem manualmente ou siga sem capa.")
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
) -> CoverResult:
    """Devolve a melhor capa encontrada (com caminho local) ou CoverResult vazio.

    `identificacao` pode complementar artista e outros dados. O álbum e a
    miniatura não são usados como capa substituta, mesmo se solicitados.
    """
    if sobrescrever_cache:
        _limpar_cache_urls()
    melhor, alternativas = candidatos_capa(
        titulo, artista, album, ano=ano, fontes=fontes, minimo_lado=minimo_lado,
        thumb_extra=thumb_extra, usar_miniatura=usar_miniatura,
        identificacao=identificacao)
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
                             "disco": None, "genero": "", "fontes": []}
    try:
        it = itunes.melhor_faixa(titulo, artista, album)
    except Exception:
        it = None
    if it:
        dados["fontes"].append("itunes")
        for chave in ("titulo", "artista", "album", "ano", "faixa", "total_faixas", "disco", "genero"):
            if not dados.get(chave) and it.get(chave):
                dados[chave] = it[chave]
        dados["capa_url"] = it.get("capa_url")

    if not dados.get("album") or not dados.get("faixa"):
        try:
            for grav in musicbrainz.buscar_gravacao(titulo, artista, album, limite=3):
                det = musicbrainz.detalhes_release(grav.get("release_id", ""), titulo) if grav.get("release_id") else {}
                if det:
                    dados["fontes"].append("musicbrainz")
                    for chave in ("album", "ano", "faixa", "total_faixas", "genero"):
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

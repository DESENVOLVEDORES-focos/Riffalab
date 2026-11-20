"""Registro de fontes de pesquisa/áudio disponíveis no aplicativo."""
from __future__ import annotations

from typing import Dict, List, Optional

from ..config import Config
from .archive_org import FonteArchiveOrg
from .base import FonteBase, Progresso, emitir
from .local_library import FonteBibliotecaLocal
from .ytdlp import FonteYtDlp

__all__ = ["FonteBase", "FonteArchiveOrg", "FonteBibliotecaLocal", "FonteYtDlp",
           "todas_as_fontes", "fontes_ativas", "por_id", "emitir", "Progresso"]


def todas_as_fontes(config: Optional[Config] = None) -> Dict[str, FonteBase]:
    fontes: List[FonteBase] = [
        FonteArchiveOrg(),
        FonteBibliotecaLocal(config),
        FonteYtDlp(config),
    ]
    return {f.id: f for f in fontes}


def fontes_ativas(config: Config) -> Dict[str, FonteBase]:
    """Somente as fontes ligadas na configuração E realmente utilizáveis."""
    ativas = set(config.get("fontes_ativas") or [])
    saida: Dict[str, FonteBase] = {}
    for fid, fonte in todas_as_fontes(config).items():
        if fid not in ativas:
            continue
        ok, _motivo = fonte.disponivel()
        if ok:
            saida[fid] = fonte
    return saida


def por_id(fid: str, config: Optional[Config] = None) -> Optional[FonteBase]:
    return todas_as_fontes(config).get(fid)

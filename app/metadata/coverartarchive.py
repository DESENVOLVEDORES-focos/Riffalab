"""Cover Art Archive: **apenas capa frontal** do lançamento.

Documentação: https://musicbrainz.org/doc/Cover_Art_Archive/API

Cada imagem no CAA traz `types` (Front, Back, Booklet, Medium, Tray…) e
`front` (true/false). A regra aqui é rígida: só entra "Front" (ou imagem sem
tipo declarado, marcada como front). Contracapa, encarte, mídia e bandeja
ficam de fora — é o que a proposta §1.1 pede explicitamente.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from . import musicbrainz

TIPOS_PROIBIDOS = ("back", "booklet", "medium", "tray", "obi", "spine",
                   "matrix", "runout", "sticker", "liner")


def _frontal_aceita(imagem: Dict[str, Any]) -> bool:
    if not imagem.get("frontal"):
        return False
    tipos = [str(t).lower() for t in (imagem.get("tipos") or [])]
    if any(t in tip for t in TIPOS_PROIBIDOS for tip in tipos):
        return False
    if not tipos:
        return True                       # sem tipo declarado: vale como front
    return any("front" in t for t in tipos)


def imagens(release_id: str = "", release_group: str = "",
            incluir_nao_frontais: bool = False) -> List[Dict[str, Any]]:
    if not release_id and not release_group:
        return []
    if incluir_nao_frontais:
        try:
            return musicbrainz.capas_release(release_id=release_id, release_group=release_group)
        except Exception:                                         # noqa: BLE001
            return []
    # Uma edição pode ter apenas contracapa. Isso não deve impedir a busca
    # pela capa frontal do mesmo grupo de lançamento (single).
    for rel, grupo in ((release_id, ""), ("", release_group)):
        if not rel and not grupo:
            continue
        try:
            todas = musicbrainz.capas_release(release_id=rel, release_group=grupo)
        except Exception:                                         # noqa: BLE001
            continue
        frontais = [img for img in todas if _frontal_aceita(img)]
        if frontais:
            return frontais
    return []


def melhor_frontal(release_id: str = "", release_group: str = "") -> Optional[Dict[str, Any]]:
    for imagem in imagens(release_id, release_group):
        if imagem.get("url"):
            return imagem
    return None


def descricao_tipos(imagem: Dict[str, Any]) -> str:
    tipos = [str(t) for t in (imagem.get("tipos") or [])]
    return ", ".join(tipos) if tipos else "capa frontal"

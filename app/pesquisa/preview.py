"""Pré-visualização: reproduzir o vídeo SEM baixar o arquivo.

Regras (proposta §2.2):

* usa o player **oficial** da plataforma (iframe `/embed/…`), nunca um
  download parcial nem scraping;
* respeita `playable_in_embed` (quando o yt-dlp informa) e a disponibilidade
  do vídeo;
* quando a incorporação não for permitida/possível, a tela oferece abrir a
  página original — em vez de fingir que toca.
"""
from __future__ import annotations

from typing import Optional, Tuple

from ..models import TrackResult


def id_video(r: TrackResult) -> str:
    """ID do vídeo ('' quando a fonte não é vídeo/embeddable)."""
    extra = r.extra or {}
    ident = str(extra.get("id") or "")
    if ident:
        return ident
    url = str(r.pagina_url or extra.get("url") or "")
    for marcador in ("watch?v=", "youtu.be/", "/shorts/", "/embed/"):
        if marcador in url:
            return url.split(marcador, 1)[1].split("&")[0].split("?")[0].strip("/")
    return ""


def url_incorporada(r: TrackResult) -> str:
    """URL do player oficial (iframe). Vazia se não houver vídeo."""
    ident = id_video(r)
    if not ident or r.fonte != "ytdlp":
        return ""
    return f"https://www.youtube-nocookie.com/embed/{ident}?rel=0&modestbranding=1&playsinline=1&enablejsapi=1"


def pode_incorporar(r: TrackResult) -> Tuple[bool, str]:
    """(pode, motivo) — motivo pronto para mostrar ao usuário."""
    if r.fonte != "ytdlp":
        return False, "a pré-visualização embutida existe apenas para vídeos"
    if not id_video(r):
        return False, "não foi possível identificar o vídeo"
    extra = r.extra or {}
    if r.incorporavel is False or extra.get("playable_in_embed") is False:
        return False, "o dono do vídeo não permite reprodução incorporada"
    if extra.get("availability") in ("private", "premium_only", "subscriber_only"):
        return False, "o vídeo não está disponível publicamente"
    if extra.get("age_limit") and int(extra["age_limit"]) >= 18:
        return False, "vídeo com restrição de idade não abre no player embutido"
    if not url_incorporada(r):
        return False, "sem endereço de incorporação"
    return True, ""


def tem_player() -> bool:
    """O Qt WebEngine está instalado? (é o que desenha o iframe)"""
    try:
        from PySide6 import QtWebEngineWidgets  # noqa: F401
        return True
    except Exception:                                             # noqa: BLE001
        return False


def url_externa(r: TrackResult) -> str:
    return r.pagina_url or str((r.extra or {}).get("url") or "")


def descricao_preview(r: TrackResult) -> str:
    """Texto curto: '5:56 · canal · 1,2 mi de visualizações'."""
    partes = []
    if r.duracao_s:
        from ..models import hhmmss
        partes.append(hhmmss(r.duracao_s))
    if r.canal:
        partes.append(r.canal)
    resumo = r.resumo_publico()
    if resumo:
        partes.append(resumo)
    return "  ·  ".join(partes)

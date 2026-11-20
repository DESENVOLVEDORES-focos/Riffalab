"""Normalização dos resultados de pesquisa (o que a tela mostra)."""
from __future__ import annotations

from typing import Iterable, List

from ..models import TrackResult
from ..texto import (artista_do_titulo, limpar_titulo, parece_canal,
                     similaridade)


def enriquecer(r: TrackResult) -> TrackResult:
    """Completa o que o yt-dlp devolveu torto, sem inventar nada.

    * `canal` guarda o nome do canal/uploader;
    * se o "artista" é só o nome do canal, tenta o padrão "Artista - Título";
    * limpa ruído do título ("(Official Video)", "[HD]"...).
    """
    extra = r.extra or {}
    if not r.canal:
        r.canal = str(extra.get("canal") or extra.get("channel")
                      or extra.get("uploader") or r.artista or "")
    if r.artista and parece_canal(r.artista):
        esquerda, direita = artista_do_titulo(r.extra.get("titulo_original")
                                              or r.titulo or "")
        if esquerda:
            r.artista, r.titulo = esquerda, limpar_titulo(direita)
    if r.titulo:
        r.titulo = limpar_titulo(r.titulo)
    if r.canal and r.artista and similaridade(r.canal, r.artista) >= 0.9:
        r.artista = r.artista          # canal do próprio artista: mantém
    return r


def normalizar_resultados(resultados: Iterable[TrackResult]) -> List[TrackResult]:
    return [enriquecer(r) for r in resultados]

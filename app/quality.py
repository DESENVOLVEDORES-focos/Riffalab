"""Comparação de qualidade de áudio.

A ordenação é uma sugestão simples baseada nos dados informados; não mede
a qualidade sonora e não permite comparar codecs ou gravações com certeza.
"""
from __future__ import annotations

from typing import Iterable, List, Optional

from .models import AudioFormat

CODECS_LOSSLESS = {"flac", "alac", "wav", "aiff", "ape", "wv", "dsf"}

# Fatores legados usados para escolher bitrate de saída na conversão automática.
# São heurísticos; não demonstram equivalência de qualidade entre codecs.
FATOR_EQUIV = {"opus": 1.80, "aac": 1.30, "m4a": 1.30, "vorbis": 1.15, "ogg": 1.10,
               "mp3": 1.00, "wma": 0.85, "ac3": 0.80}

def eh_lossless(codec: str) -> bool:
    c = (codec or "").lower()
    if c in CODECS_LOSSLESS:
        return True
    # WAV/PCM em contêiner (pcm_s16le, pcm_s24le, ...) também é sem perda
    return c.startswith("pcm_") or c.startswith("pcm")


def pontuar(fmt: AudioFormat) -> float:
    """Ordem preliminar: codec sem perda primeiro; depois bitrate informado.

    Não compara a qualidade real entre codecs ou gravações. Taxa desconhecida
    não é substituída por um valor suposto. Usado para sugerir ordem, não medir.
    """
    codec = (fmt.codec or "unknown").lower()
    if fmt.lossless or eh_lossless(codec):
        return 1000.0
    if not fmt.bitrate_kbps or fmt.bitrate_kbps <= 0:
        return 0.0
    return min(999.0, float(fmt.bitrate_kbps) / 320.0 * 999.0)


def rotulo(fmt: Optional[AudioFormat]) -> str:
    if not fmt:
        return "não verificado"
    if fmt.lossless or eh_lossless(fmt.codec):
        return "Sem perda (codec)"
    if not fmt.bitrate_kbps:
        return "Bitrate não informado"
    return "Comparação aproximada"


def cor_rotulo(fmt: Optional[AudioFormat]) -> str:
    """Cores da paleta neon (usadas nos selos da interface)."""
    r = rotulo(fmt)
    return {"Sem perda (codec)": "#22E8FF", "Comparação aproximada": "#FFE13D",
            "Bitrate não informado": "#A98BC8", "não verificado": "#A98BC8"}.get(r, "#A98BC8")


def melhor_de(formatos: Iterable[AudioFormat]) -> Optional[AudioFormat]:
    formatos = list(formatos)
    return max(formatos, key=pontuar) if formatos else None


def comparar(a: Optional[AudioFormat], b: Optional[AudioFormat]) -> str:
    """Texto curto comparando dois formatos (usado no histórico/log)."""
    if not a or not b:
        return "-"
    pa, pb = pontuar(a), pontuar(b)
    if abs(pa - pb) < 1:
        return "pontuação estimada semelhante"
    if pa > pb:
        return f"{a.descricao_curta()} tem pontuação estimada maior que {b.descricao_curta()}"
    return f"{b.descricao_curta()} tem pontuação estimada maior que {a.descricao_curta()}"


def deduplicar_formatos(formatos: List[AudioFormat]) -> List[AudioFormat]:
    vistos, saida = set(), []
    for f in sorted(formatos, key=pontuar, reverse=True):
        chave = (f.codec.lower(), f.bitrate_kbps, f.sample_rate, f.url)
        if chave in vistos:
            continue
        vistos.add(chave)
        saida.append(f)
    return saida

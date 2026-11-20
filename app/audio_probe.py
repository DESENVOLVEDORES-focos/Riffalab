"""Análise de arquivos de áudio: codec, bitrate, taxa, duração, tags e capa.

Usa ffprobe quando disponível; se não existir (caso comum no Windows, onde
muitas pessoas só têm o ffmpeg.exe), cai para a saída de `ffmpeg -i` e,
como último recurso, para o Mutagen.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Dict, Optional

from .config import CRIAR_SEM_JANELA
from .models import ArquivoInfo
from .quality import eh_lossless
from .tools import ffmpeg, ffprobe

_RE_STREAM = re.compile(
    r"Stream #\d+:\d+.*?: Audio: (?P<codec>[\w\-]+)[^,]*, "
    r"(?P<sr>\d+) Hz, (?P<canal>mono|stereo|[\d.]+\(.*?\)|[\d.]+ channels)"
    r"(?P<resto>[^\n]*)"
)
_RE_BITRATE = re.compile(r"(\d+)\s*kb/s")
_RE_DURACAO = re.compile(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)")


def _float(v) -> Optional[float]:
    try:
        if v in (None, "", "N/A"):
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _int(v) -> Optional[int]:
    f = _float(v)
    return int(f) if f is not None else None


# --------------------------------------------------------------- ffprobe
def _por_ffprobe(caminho: Path) -> Optional[ArquivoInfo]:
    exe = ffprobe()
    if not exe.ok:
        return None
    try:
        saida = subprocess.run(
            [exe.caminho, "-v", "error", "-print_format", "json",
             "-show_format", "-show_streams", str(caminho)],
            capture_output=True, text=True, timeout=60, encoding='utf-8', errors='replace',
            creationflags=CRIAR_SEM_JANELA,
        )
        if saida.returncode != 0 or not saida.stdout.strip():
            return None
        dados = json.loads(saida.stdout)
    except Exception:
        return None

    streams = dados.get("streams") or []
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if not audio:
        return None
    fmt = dados.get("format") or {}
    codec = (audio.get("codec_name") or "").lower()
    bitrate = _int(audio.get("bit_rate")) or _int(fmt.get("bit_rate"))
    tags = {str(k).lower(): str(v) for k, v in (fmt.get("tags") or {}).items()}
    tags.update({str(k).lower(): str(v) for k, v in (audio.get("tags") or {}).items()})

    return ArquivoInfo(
        caminho=str(caminho),
        codec=codec,
        bitrate_kbps=round(bitrate / 1000) if bitrate else None,
        sample_rate=_int(audio.get("sample_rate")),
        canais=_int(audio.get("channels")),
        duracao_s=_float(fmt.get("duration")) or _float(audio.get("duration")),
        container=(fmt.get("format_name") or "").split(",")[0],
        lossless=eh_lossless(codec),
        tamanho=caminho.stat().st_size,
        tags=tags,
    )


# --------------------------------------------------------------- ffmpeg -i
def _por_ffmpeg(caminho: Path) -> Optional[ArquivoInfo]:
    exe = ffmpeg()
    if not exe.ok:
        return None
    try:
        p = subprocess.run(
            [exe.caminho, "-hide_banner", "-i", str(caminho)],
            capture_output=True, text=True, timeout=60, encoding='utf-8', errors='replace',
            creationflags=CRIAR_SEM_JANELA,
        )
        texto = (p.stderr or "") + (p.stdout or "")
    except Exception:
        return None

    m = _RE_STREAM.search(texto)
    if not m:
        return None
    codigo = m.group("codec").lower()
    resto = m.group("resto") or ""
    br = _RE_BITRATE.search(resto)
    dur = _RE_DURACAO.search(texto)
    duracao = None
    if dur:
        duracao = int(dur.group(1)) * 3600 + int(dur.group(2)) * 60 + float(dur.group(3))

    canal_txt = m.group("canal")
    canais = 1 if canal_txt == "mono" else 2 if canal_txt == "stereo" else _int(canal_txt.split()[0] if canal_txt else "")
    bitrate = int(br.group(1)) if br else None

    info = ArquivoInfo(
        caminho=str(caminho), codec=codigo, bitrate_kbps=bitrate,
        sample_rate=int(m.group("sr")), canais=canais, duracao_s=duracao,
        container=caminho.suffix.lstrip(".").lower(), lossless=eh_lossless(codigo),
        tamanho=caminho.stat().st_size,
    )
    # Metadados de texto (linhas "titulo : valor" do bloco Metadata)
    for linha in texto.splitlines():
        if ":" in linha and not linha.strip().startswith(("Stream", "Duration", "Input", "Output")):
            chave, _, valor = linha.strip().partition(":")
            chave = chave.strip().lower()
            if chave in ("title", "artist", "album", "date", "genre", "track", "titulo", "artista"):
                info.tags.setdefault(chave, valor.strip())
    return info


# --------------------------------------------------------------- mutagen
_NOMES_MUTAGEN = {
    "titulo": ("TIT2", "©nam", "title"),
    "artista": ("TPE1", "©ART", "artist"),
    "album": ("TALB", "©alb", "album"),
    "ano": ("TDRC", "TYER", "©day", "date", "year"),
    "genero": ("TCON", "©gen", "genre"),
    "faixa": ("TRCK", "trkn", "tracknumber"),
}


def _por_mutagen(caminho: Path, info: Optional[ArquivoInfo] = None) -> Optional[ArquivoInfo]:
    try:
        import mutagen  # noqa: WPS433
    except Exception:
        return info
    try:
        arq = mutagen.File(str(caminho))
    except Exception:
        return info
    if arq is None:
        return info

    codec = caminho.suffix.lstrip(".").lower()
    if info is None:
        info = ArquivoInfo(caminho=str(caminho), codec=codec, container=codec,
                           lossless=eh_lossless(codec), tamanho=caminho.stat().st_size)

    try:
        if getattr(arq, "info", None) is not None:
            info.bitrate_kbps = info.bitrate_kbps or round((getattr(arq.info, "bitrate", 0) or 0) / 1000) or None
            info.sample_rate = info.sample_rate or getattr(arq.info, "sample_rate", None)
            info.canais = info.canais or getattr(arq.info, "channels", None)
            info.duracao_s = info.duracao_s or getattr(arq.info, "length", None)
            if not info.codec or info.codec in ("", "?"):
                info.codec = (getattr(arq.info, "codec", "") or codec).lower()
            info.lossless = info.lossless or eh_lossless(info.codec) or bool(getattr(arq.info, "lossless", False))
    except Exception:
        pass

    # tags legíveis
    try:
        for chave, ids in _NOMES_MUTAGEN.items():
            if info.tags.get(chave):
                continue
            for ident in ids:
                valor = None
                if hasattr(arq, "tags") and arq.tags:
                    if ident in arq.tags:
                        bruto = arq.tags[ident]
                        texto = getattr(bruto, 'text', None)
                        valor = ', '.join(str(v) for v in texto) if texto is not None else str(bruto)
                    elif hasattr(arq.tags, "get"):
                        bruto = arq.tags.get(ident)
                        valor = str(bruto) if bruto else None
                if valor:
                    info.tags[chave] = valor.strip("[]'\"")
                    break
    except Exception:
        pass

    # capa embutida
    try:
        if info.codec == "mp3" or caminho.suffix.lower() == ".mp3":
            from mutagen.id3 import ID3
            tags = ID3(str(caminho))
            apics = tags.getall("APIC")
            info.tem_capa = bool(apics)
            info.capa_bytes = len(apics[0].data) if apics else 0
        else:
            capas = getattr(arq, "pictures", None) or []
            info.tem_capa = bool(capas)
            info.capa_bytes = len(capas[0].data) if capas else 0
    except Exception:
        pass
    return info


# --------------------------------------------------------------- público
def analisar(caminho: str | Path) -> ArquivoInfo:
    """Análise completa (metadados do contêiner + tags + capa)."""
    p = Path(caminho)
    if not p.is_file():
        return ArquivoInfo(caminho=str(p), erro="arquivo não encontrado")
    info = _por_ffprobe(p) or _por_ffmpeg(p)
    info = _por_mutagen(p, info) or info
    if info is None:
        return ArquivoInfo(caminho=str(p), erro="formato não reconhecido")
    if not info.codec:
        info.codec = p.suffix.lstrip(".").lower()
    if info.lossless:
        info.bitrate_kbps = info.bitrate_kbps or None
    return info


def duracao(caminho: str | Path) -> Optional[float]:
    return analisar(caminho).duracao_s

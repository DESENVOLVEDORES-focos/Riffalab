"""Leitura de dimensões de imagem sem dependências externas (JPEG/PNG/WEBP/GIF)."""
from __future__ import annotations

import struct
from typing import Optional, Tuple


def dimensoes(dados: bytes) -> Optional[Tuple[int, int]]:
    """Devolve (largura, altura) lendo apenas o cabeçalho do arquivo."""
    if not dados or len(dados) < 16:
        return None
    try:
        if dados[:8] == b"\x89PNG\r\n\x1a\n":
            w, h = struct.unpack(">II", dados[16:24])
            return int(w), int(h)
        if dados[:3] == b"GIF":
            w, h = struct.unpack("<HH", dados[6:10])
            return int(w), int(h)
        if dados[:4] == b"RIFF" and dados[8:12] == b"WEBP":
            fmt = dados[12:16]
            if fmt == b"VP8X":
                w = int.from_bytes(dados[24:27], "little") + 1
                h = int.from_bytes(dados[27:30], "little") + 1
                return w, h
            if fmt == b"VP8 ":
                w = int.from_bytes(dados[26:28], "little") & 0x3FFF
                h = int.from_bytes(dados[28:30], "little") & 0x3FFF
                return w, h
            if fmt == b"VP8L":
                b = dados[21:25]
                bits = int.from_bytes(b, "little")
                return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
            return None
        if dados[:2] == b"\xff\xd8":                      # JPEG: varre os marcadores
            i = 2
            n = len(dados)
            while i < n - 9:
                if dados[i] != 0xFF:
                    i += 1
                    continue
                marcador = dados[i + 1]
                if marcador in (0xD8, 0xD9) or 0xD0 <= marcador <= 0xD7:
                    i += 2
                    continue
                tam = struct.unpack(">H", dados[i + 2:i + 4])[0]
                if marcador in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                                0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                    h, w = struct.unpack(">HH", dados[i + 5:i + 9])
                    return int(w), int(h)
                i += 2 + tam
            return None
    except (struct.error, IndexError, ValueError):
        return None
    return None


def eh_imagem(dados: bytes) -> bool:
    if not dados:
        return False
    return (dados[:2] == b"\xff\xd8" or dados[:8] == b"\x89PNG\r\n\x1a\n"
            or dados[:3] == b"GIF" or (dados[:4] == b"RIFF" and dados[8:12] == b"WEBP"))


def extensao(dados: bytes) -> str:
    if dados[:2] == b"\xff\xd8":
        return ".jpg"
    if dados[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if dados[:3] == b"GIF":
        return ".gif"
    if dados[:4] == b"RIFF" and dados[8:12] == b"WEBP":
        return ".webp"
    return ".jpg"

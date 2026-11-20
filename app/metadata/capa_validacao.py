"""Validação das imagens antes de virarem capa (proposta §6).

Uma capa só entra no MP3 se: for imagem de verdade, tiver tamanho mínimo,
não for duplicata de outra que já está no cache e tiver proporção plausível.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Optional, Tuple

from ..image_utils import dimensoes, eh_imagem

MIN_LADO_PADRAO = 300
# capa de álbum é quadrada (ou quase); 3:1, 16:9 etc. costumam ser banner/arte
PROPORCAO_MAX = 1.35


@dataclass
class Validacao:
    ok: bool = False
    motivo: str = ""
    largura: int = 0
    altura: int = 0
    hash: str = ""

    def dimensoes_texto(self) -> str:
        return f"{self.largura}x{self.altura}" if self.ok else "-"


def validar(dados: bytes, minimo_lado: int = MIN_LADO_PADRAO,
            exigir_quadrada: bool = False) -> Validacao:
    if not dados:
        return Validacao(motivo="imagem vazia")
    if len(dados) < 1024:
        return Validacao(motivo="arquivo pequeno demais para ser capa")
    if not eh_imagem(dados):
        return Validacao(motivo="não é uma imagem válida")
    largura, altura = dimensoes(dados) or (0, 0)
    if not largura or not altura:
        return Validacao(motivo="não foi possível medir a imagem")
    resumo = hashlib.sha1(dados).hexdigest()[:20]
    if min(largura, altura) < minimo_lado:
        return Validacao(motivo=f"imagem menor que {minimo_lado}px "
                                f"({largura}x{altura})", largura=largura,
                         altura=altura, hash=resumo)
    proporcao = max(largura, altura) / max(1, min(largura, altura))
    if proporcao > PROPORCAO_MAX:
        return Validacao(motivo=f"proporção estranha para capa ({largura}x{altura})",
                         largura=largura, altura=altura, hash=resumo)
    if exigir_quadrada and proporcao > 1.08:
        return Validacao(motivo=f"capa não é quadrada ({largura}x{altura})",
                         largura=largura, altura=altura, hash=resumo)
    return Validacao(ok=True, largura=largura, altura=altura, hash=resumo)


def mesma_imagem(a: str, b: str) -> bool:
    return bool(a) and a == b

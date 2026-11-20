"""Contrato comum das fontes de pesquisa/áudio.

Cada fonte declara sua situação legal e, opcionalmente, se depende de
cookies do próprio usuário. O aplicativo só oferece o que estiver
disponível e autorizado no contexto local do usuário.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Optional, Tuple

from ..models import AudioFormat, TrackResult

Progresso = Optional[Callable[[int, str], None]]


class FonteBase:
    id: str = "base"
    nome: str = "Fonte"
    descricao: str = ""
    #: True = acervo público/licenciado (biblioteca local, domínio público, CC)
    autorizada: bool = True
    #: texto mostrado na interface sobre o que a fonte oferece
    aviso_legal: str = ""
    #: True = o download usa os cookies.txt do próprio usuário
    usa_cookies: bool = False

    # -- ciclo de vida -------------------------------------------------
    def disponivel(self) -> Tuple[bool, str]:
        """(pode usar?, motivo)."""
        return True, ""

    def buscar(self, consulta: str, limite: int = 20) -> List[TrackResult]:
        raise NotImplementedError

    def baixar(self, resultado: TrackResult, formato: AudioFormat,
               destino: Path, progresso: Progresso = None) -> Path:
        raise NotImplementedError

    # -- opcional ------------------------------------------------------
    def detalhar(self, resultado: TrackResult) -> TrackResult:
        """Completa a lista de formatos (quando a busca é resumida)."""
        return resultado

    def __repr__(self) -> str:                                   # pragma: no cover
        return f"<Fonte {self.id}>"


def emitir(cb: Progresso, pct: int, msg: str) -> None:
    if cb:
        try:
            cb(max(0, min(100, int(pct))), msg)
        except Exception:
            pass

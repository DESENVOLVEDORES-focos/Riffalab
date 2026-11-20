"""Log em arquivo, com cuidado para não registrar nada sensível.

Regra: nada de conteúdo de cookies.txt, nada de URLs com tokens. Só a
mensagem, o nível e o horário — e um filtro que apaga padrões suspeitos.
"""
from __future__ import annotations

import logging
import re
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import ARQ_LOG

_RE_SENSIVEL = re.compile(
    r"(cookie\s*[:=]\s*\S+|set-cookie:\s*\S+|authorization:\s*\S+|"
    r"token[=:]\s*\S+|senha[=:]\s*\S+|password[=:]\s*\S+)",
    re.IGNORECASE,
)


class FiltroSensivel(logging.Filter):
    """Substitui qualquer coisa parecida com credencial por ***."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            mensagem = record.getMessage()
        except Exception:
            return True
        limpa = _RE_SENSIVEL.sub("***", mensagem)
        if limpa != mensagem:
            record.msg = limpa
            record.args = ()
        return True


def configurar(nivel: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger("rifflab")
    if logger.handlers:
        return logger
    logger.setLevel(nivel)

    formato = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%d/%m/%Y %H:%M:%S")

    try:
        arquivo = RotatingFileHandler(ARQ_LOG, maxBytes=1_500_000, backupCount=3, encoding="utf-8")
        arquivo.setFormatter(formato)
        arquivo.addFilter(FiltroSensivel())
        logger.addHandler(arquivo)
    except OSError:
        pass

    if sys.stderr is not None:
        console = logging.StreamHandler()
        console.setFormatter(formato)
        console.addFilter(FiltroSensivel())
        logger.addHandler(console)
    return logger

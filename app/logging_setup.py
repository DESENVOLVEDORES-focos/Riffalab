"""Diagnósticos no console do INICIAR.bat e no log local, com proteção básica.

A saída é uma ajuda ao diagnóstico, não uma garantia de anonimização: sempre
revise mensagens e caminhos pessoais antes de compartilhá-los.
"""
from __future__ import annotations

import logging
import re
import sys
from logging.handlers import RotatingFileHandler

from .config import ARQ_LOG

# URLs completas podem carregar assinaturas, identificadores e tokens em
# qualquer posição. Não enviar o link ao console nem ao log de diagnóstico.
_URL = re.compile(r'https?://[^\s<>"\']+', re.IGNORECASE)
_CABECALHO = re.compile(r'''(?im)\b(?:set-cookie|cookie|authorization)["']?\s*[:=][^\r\n]*''')
_SEGREDO = re.compile(
    r'(?i)(?:["\']?(?:api[_-]?key|access[_-]?token|refresh[_-]?token|token|senha|password)'
    r'["\']?\s*[:=]\s*["\']?)[^\s,;"\']+'
)
_BEARER = re.compile(r'(?i)\bbearer\s+[^\s,;]+')
_CHAVE = re.compile(r'\b(?:gsk_[a-zA-Z0-9_-]{8,}|sk-[a-zA-Z0-9_-]{8,})\b')
_COOKIE_LINHA = re.compile(r'(?m)^([^\r\n]*\t){6,}[^\r\n]*$')


def texto_seguro(texto: object) -> str:
    """Retira URLs, cabeçalhos, tokens comuns e linhas Netscape do diagnóstico."""
    texto = str(texto)
    texto = _COOKIE_LINHA.sub('[linha de cookies ocultada]', texto)
    texto = _CABECALHO.sub('[cabeçalho sensível ocultado]', texto)
    texto = _URL.sub('[URL ocultada]', texto)
    texto = _SEGREDO.sub('[credencial ocultada]', texto)
    texto = _BEARER.sub('[autorização ocultada]', texto)
    return _CHAVE.sub('[chave ocultada]', texto)


class FiltroSensivel(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = texto_seguro(record.getMessage())
            record.args = ()
            # O formatter acrescenta exc_info depois dos filtros. Tratar aqui
            # para não escapar um traceback contendo URLs ou credenciais.
            if record.exc_info:
                import traceback
                record.msg += '\n' + texto_seguro(''.join(traceback.format_exception(*record.exc_info)))
                record.exc_info = None
                record.exc_text = None
            if record.stack_info:
                record.stack_info = texto_seguro(record.stack_info)
        except Exception:
            record.msg, record.args = '[diagnóstico indisponível]', ()
            record.exc_info, record.exc_text, record.stack_info = None, None, None
        return True


def registrar_erro(etapa: str, mensagem: object) -> None:
    """Registra erro tratado mesmo se o logger ainda não foi configurado."""
    # Sanitizar antes do logger: o lastResort do Python pode não ter filtros.
    logging.getLogger('rifflab').error('%s: %s', texto_seguro(etapa), texto_seguro(mensagem))


def configurar(nivel: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger('rifflab')
    if logger.handlers:
        return logger
    logger.setLevel(nivel)
    logger.propagate = False
    formato = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', '%d/%m/%Y %H:%M:%S')
    try:
        arquivo = RotatingFileHandler(ARQ_LOG, maxBytes=1_500_000, backupCount=3, encoding='utf-8')
        arquivo.setFormatter(formato)
        arquivo.addFilter(FiltroSensivel())
        logger.addHandler(arquivo)
    except OSError as exc:
        if sys.stderr is not None:
            print(texto_seguro(f'[AVISO] Não foi possível abrir rifflab.log: {exc}'), file=sys.stderr)
    if sys.stderr is not None:
        console = logging.StreamHandler(sys.stderr)
        console.setFormatter(formato)
        console.addFilter(FiltroSensivel())
        logger.addHandler(console)
    return logger

"""Ponte thread ⇄ interface para a confirmação da capa (etapa 9).

O download roda numa thread do pool; o diálogo só pode abrir na thread da
interface. Esta ponte faz o pedido atravessar com segurança:

    thread de download  ──sinal──▶  thread da interface (diálogo)
                        ◀──Evento──  resposta

Se a interface não responder em 5 minutos (janela fechando, por exemplo), a
capa automática é usada e o download continua — nada fica travado.
"""
from __future__ import annotations

import threading
from typing import Any, Dict, Optional

from PySide6.QtCore import QObject, Signal

from ..models import CoverResult

ESPERA_MAXIMA = 300.0           # segundos


class PedidoCapa:
    """Pedido de confirmação de capa, com a resposta do usuário."""

    def __init__(self, capa: CoverResult, musica: Optional[Dict[str, Any]] = None) -> None:
        self.capa = capa
        self.musica = musica or {}
        self.evento = threading.Event()
        self.escolha: Optional[CoverResult] = capa
        self.recusou = False
        self.respondido = False

    def responder(self, escolha: Optional[CoverResult], recusou: bool = False) -> None:
        self.escolha = escolha
        self.recusou = recusou
        self.respondido = True
        self.evento.set()


class Ponte(QObject):
    pedir_capa = Signal(object)          # PedidoCapa

    def __init__(self) -> None:
        super().__init__()
        self.janela = None
        self.ativo = True

    def ligar(self, janela) -> None:
        self.janela = janela

    # chamado na thread de download --------------------------------
    def aprovador_capa(self, capa: CoverResult,
                       musica: Optional[Dict[str, Any]] = None) -> Optional[CoverResult]:
        if not self.ativo or self.janela is None or not getattr(capa, "caminho", ""):
            return capa
        pedido = PedidoCapa(capa, musica)
        try:
            self.pedir_capa.emit(pedido)
        except RuntimeError:
            return capa
        if not pedido.evento.wait(ESPERA_MAXIMA):
            return capa               # ninguém respondeu: segue com a automática
        return None if pedido.recusou else pedido.escolha


PONTE = Ponte()

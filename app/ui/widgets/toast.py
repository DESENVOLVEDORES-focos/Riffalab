"""Aviso flutuante (toast) no rodapé da janela."""
from __future__ import annotations

from PySide6.QtCore import QPropertyAnimation, Qt, QTimer
from PySide6.QtWidgets import QGraphicsOpacityEffect, QLabel, QWidget

from ..theme import PALETA


class Toast(QLabel):
    def __init__(self, pai: QWidget) -> None:
        super().__init__(pai)
        self.setWordWrap(True)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet(
            f"background: {PALETA['surface3']}; color: {PALETA['texto']};"
            f"border: 1px solid {PALETA['violeta']}; border-radius: 11px;"
            f"padding: 10px 18px; font-weight: 600;"
        )
        self.setVisible(False)
        self._efeito = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._efeito)
        self._anim = QPropertyAnimation(self._efeito, b"opacity", self)
        self._anim.setDuration(220)

    def mostrar(self, texto: str, segundos: int = 4) -> None:
        self.setText(texto)
        self.adjustSize()
        self._posicionar()
        self.setVisible(True)
        self._efeito.setOpacity(0.0)
        self._anim.stop()
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()
        QTimer.singleShot(segundos * 1000, self.esconder)

    def esconder(self) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._efeito.opacity())
        self._anim.setEndValue(0.0)
        self._anim.start()
        QTimer.singleShot(240, lambda: self.setVisible(False))

    def _posicionar(self) -> None:
        pai = self.parentWidget()
        if not pai:
            return
        largura = min(680, max(280, self.sizeHint().width()))
        self.setFixedWidth(largura)
        self.move((pai.width() - largura) // 2, pai.height() - self.height() - 26)

    def resizeEvent(self, evento) -> None:      # noqa: N802
        super().resizeEvent(evento)
        self._posicionar()

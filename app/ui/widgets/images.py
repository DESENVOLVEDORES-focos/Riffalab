"""Carregamento de miniaturas em segundo plano (sem travar a interface)."""
from __future__ import annotations

import hashlib
import urllib.request
from pathlib import Path
from typing import Callable, Dict, List, Optional

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QPixmap

from ...config import PASTA_CACHE_CAPAS
from ...workers import EXECUTOR_GLOBAL

UA = "RiffLab/0.1 (uso local)"


def pixmap_de_bytes(dados: bytes, lado: int) -> QPixmap:
    pm = QPixmap()
    if not dados or not pm.loadFromData(dados):
        return QPixmap()
    return pm.scaled(lado, lado, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)


def cortar_quadrado(pm: QPixmap, lado: int) -> QPixmap:
    """Escala preenchendo e recorta o centro (capa quadrada bonita)."""
    if pm.isNull():
        return pm
    esc = pm.scaled(lado, lado, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    x = max(0, (esc.width() - lado) // 2)
    y = max(0, (esc.height() - lado) // 2)
    return esc.copy(x, y, lado, lado)


class CarregadorImagens(QObject):
    """Baixa cada URL uma única vez e guarda em memória + disco."""

    _pronto = Signal(str, bytes)

    def __init__(self, parent: Optional[QObject] = None, pasta_cache: Optional[Path] = None) -> None:
        super().__init__(parent)
        self.memoria: Dict[str, bytes] = {}
        self.esperando: Dict[str, List[Callable[[bytes], None]]] = {}
        self.pasta = Path(pasta_cache or (PASTA_CACHE_CAPAS / "thumbs"))
        self.pasta.mkdir(parents=True, exist_ok=True)
        self._pronto.connect(self._entregar)

    # ------------------------------------------------------------------ API
    def pedir(self, url: str, callback: Callable[[bytes], None]) -> None:
        if not url:
            callback(b"")
            return
        if url in self.memoria:
            callback(self.memoria[url])
            return
        arquivo = self._arquivo(url)
        if arquivo.exists():
            try:
                dados = arquivo.read_bytes()
                self.memoria[url] = dados
                callback(dados)
                return
            except OSError:
                pass
        self.esperando.setdefault(url, []).append(callback)
        if len(self.esperando[url]) == 1:
            EXECUTOR_GLOBAL.rodar(self._baixar, url,
                                  ao_resultado=lambda par: self._pronto.emit(par[0], par[1]))

    # -------------------------------------------------------------- interno
    def _arquivo(self, url: str) -> Path:
        chave = hashlib.sha1(url.encode("utf-8")).hexdigest()
        return self.pasta / f"{chave}.img"

    @staticmethod
    def _baixar(url: str) -> tuple[str, bytes]:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=25) as resp:
                dados = resp.read()
            if len(dados) < 512:
                dados = b""
            return url, dados
        except Exception:
            return url, b""

    def _entregar(self, url: str, dados: bytes) -> None:
        if dados:
            self.memoria[url] = dados
            try:
                self._arquivo(url).write_bytes(dados)
            except OSError:
                pass
        for cb in self.esperando.pop(url, []):
            try:
                cb(dados)
            except RuntimeError:
                continue        # widget já foi destruído

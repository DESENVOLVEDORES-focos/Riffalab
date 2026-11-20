"""Execução em segundo plano: nada de travar a interface."""
from __future__ import annotations

import traceback
from typing import Any, Callable, Optional

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal


class SinaisTarefa(QObject):
    iniciou = Signal()
    progresso = Signal(int, str)          # porcentagem, mensagem
    resultado = Signal(object)
    erro = Signal(str)
    terminou = Signal()


class Tarefa(QRunnable):
    """Roda `fn` em uma thread do pool. Se `com_progresso`, injeta o callback."""

    def __init__(self, fn: Callable[..., Any], *args: Any,
                 com_progresso: bool = False, **kwargs: Any) -> None:
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.com_progresso = com_progresso
        self.sinais = SinaisTarefa()
        # A referência ao objeto PRECISA sobreviver ao run(): se o wrapper
        # Python for coletado pelo GC, os sinais deixam de ser entregues.
        self.setAutoDelete(False)

    def run(self) -> None:                                     # pragma: no cover
        try:
            self.sinais.iniciou.emit()
        except RuntimeError:
            return                                   # app encerrando
        try:
            if self.com_progresso:
                resultado = self.fn(*self.args, progresso=self.sinais.progresso.emit,
                                    **self.kwargs)
            else:
                resultado = self.fn(*self.args, **self.kwargs)
        except Exception as exc:                                  # noqa: BLE001
            traceback.print_exc()
            try:
                self.sinais.erro.emit(f"{exc.__class__.__name__}: {exc}")
            except RuntimeError:
                pass
        else:
            try:
                self.sinais.resultado.emit(resultado)
            except RuntimeError:
                pass
        finally:
            try:
                self.sinais.terminou.emit()
            except RuntimeError:
                pass


class Executor:
    """Fachada simples sobre o QThreadPool."""

    def __init__(self, max_threads: int = 4) -> None:
        # Não criar objetos Qt no import: o QApplication deve existir antes do
        # pool ser construído, inclusive ao importar módulos em testes.
        self._pool: Optional[QThreadPool] = None
        self._max_threads = max(2, max_threads)
        self._ativas: set = set()

    @property
    def pool(self) -> QThreadPool:
        if self._pool is None:
            self._pool = QThreadPool()
            self._pool.setMaxThreadCount(self._max_threads)
        return self._pool

    def rodar(self, fn: Callable[..., Any], *args: Any,
              ao_resultado: Optional[Callable[[Any], None]] = None,
              ao_erro: Optional[Callable[[str], None]] = None,
              ao_progresso: Optional[Callable[[int, str], None]] = None,
              ao_terminar: Optional[Callable[[], None]] = None,
              com_progresso: bool = False,
              **kwargs: Any) -> Tarefa:
        tarefa = Tarefa(fn, *args, com_progresso=com_progresso, **kwargs)
        if ao_resultado:
            tarefa.sinais.resultado.connect(ao_resultado)
        if ao_erro:
            tarefa.sinais.erro.connect(ao_erro)
        if ao_progresso:
            tarefa.sinais.progresso.connect(ao_progresso)
        if ao_terminar:
            tarefa.sinais.terminou.connect(ao_terminar)
        self._ativas.add(tarefa)

        def _limpar(_t=tarefa) -> None:
            self._ativas.discard(_t)

        tarefa.sinais.terminou.connect(_limpar)
        self.pool.start(tarefa)
        return tarefa

    def aguardar(self, ms: int = 5000) -> bool:
        return self._pool is None or self._pool.waitForDone(ms)


# pool global para tarefas curtas (miniaturas, verificações)
EXECUTOR_GLOBAL = Executor(6)

# Consultas demoradas de formatos não devem ocupar o pool das pesquisas e downloads.
EXECUTOR_FORMATOS = Executor(3)

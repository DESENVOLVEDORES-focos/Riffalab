"""Histórico: pesquisas feitas e processamentos realizados."""
from __future__ import annotations

import time
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QAbstractItemView, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
                               QVBoxLayout, QWidget)

from ...db import Banco
from ..theme import PALETA


def _data(ts: Optional[float]) -> str:
    if not ts:
        return "-"
    return time.strftime("%d/%m/%Y %H:%M", time.localtime(ts))


class HistoryPage(QWidget):
    mensagem = Signal(str)

    def __init__(self, banco: Banco, pai: Optional[QWidget] = None) -> None:
        super().__init__(pai)
        self.banco = banco

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(26, 22, 26, 16)
        raiz.setSpacing(12)

        topo = QHBoxLayout()
        col = QVBoxLayout()
        col.setSpacing(2)
        t = QLabel("Histórico")
        t.setObjectName("titulo")
        st = QLabel("Tudo que foi pesquisado e processado fica registrado no banco local.")
        st.setObjectName("subtitulo")
        col.addWidget(t)
        col.addWidget(st)
        topo.addLayout(col, 1)

        self.filtro = QLineEdit()
        self.filtro.setPlaceholderText("Filtrar…")
        self.filtro.setFixedWidth(240)
        self.filtro.textChanged.connect(self.carregar)
        topo.addWidget(self.filtro, 0, Qt.AlignBottom)

        self.btn_atualizar = QPushButton("Atualizar")
        self.btn_atualizar.setObjectName("fantasma")
        self.btn_atualizar.clicked.connect(self.carregar)
        topo.addWidget(self.btn_atualizar, 0, Qt.AlignBottom)

        self.btn_limpar = QPushButton("Limpar histórico")
        self.btn_limpar.setObjectName("perigo")
        self.btn_limpar.clicked.connect(self._limpar)
        topo.addWidget(self.btn_limpar, 0, Qt.AlignBottom)
        raiz.addLayout(topo)

        r1 = QLabel("PESQUISAS")
        r1.setObjectName("rotulo")
        raiz.addWidget(r1)
        self.tab_pesq = self._tabela(["Data", "Consulta", "Fontes", "Detalhe", "Nº"])
        raiz.addWidget(self.tab_pesq, 1)

        r2 = QLabel("PROCESSAMENTOS")
        r2.setObjectName("rotulo")
        raiz.addWidget(r2)
        self.tab_dl = self._tabela(["Data", "Música", "Fonte", "Codec", "Status", "Arquivo"])
        raiz.addWidget(self.tab_dl, 1)

        self.carregar()

    def _tabela(self, colunas) -> QTableWidget:
        tab = QTableWidget(0, len(colunas))
        tab.setHorizontalHeaderLabels(colunas)
        tab.verticalHeader().setVisible(False)
        tab.setAlternatingRowColors(True)
        tab.setSelectionBehavior(QAbstractItemView.SelectRows)
        tab.setEditTriggers(QAbstractItemView.NoEditTriggers)
        tab.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        tab.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        return tab

    # ------------------------------------------------------------------ dados
    def carregar(self) -> None:
        filtro = self.filtro.text().strip()
        hist = [h for h in self.banco.listar_historico(300)
                if h["tipo"] == "pesquisa"
                and (not filtro or filtro.lower() in (h["consulta"] or "").lower())]
        self.tab_pesq.setRowCount(len(hist))
        for r, h in enumerate(hist):
            valores = [_data(h.get("criado_em")), h.get("consulta") or "",
                       h.get("fonte") or "", h.get("detalhe") or "", str(h.get("n_itens") or 0)]
            for c, v in enumerate(valores):
                self.tab_pesq.setItem(r, c, QTableWidgetItem(v))

        downloads = [d for d in self.banco.listar_downloads(300)
                     if not filtro or filtro.lower() in f"{d.get('titulo')} {d.get('artista')}".lower()]
        self.tab_dl.setRowCount(len(downloads))
        for r, d in enumerate(downloads):
            valores = [_data(d.get("criado_em")),
                       f"{d.get('artista') or ''} - {d.get('titulo') or ''}".strip(" -"),
                       d.get("fonte") or "", (d.get("codec") or "").upper(),
                       d.get("status") or "", d.get("caminho") or d.get("erro") or ""]
            for c, v in enumerate(valores):
                item = QTableWidgetItem(str(v))
                if c == 4:
                    cor = {"finalizado": PALETA["lima"], "erro": PALETA["vermelho"]}.get(
                        str(v), PALETA["texto_dim"])
                    item.setForeground(Qt.GlobalColor.white if False else item.foreground())
                    item.setText(str(v))
                if c == 5:
                    item.setToolTip(str(v))
                self.tab_dl.setItem(r, c, item)

    def _limpar(self) -> None:
        self.banco.limpar_historico()
        self.banco.limpar_downloads()
        self.carregar()
        self.mensagem.emit("Histórico limpo.")

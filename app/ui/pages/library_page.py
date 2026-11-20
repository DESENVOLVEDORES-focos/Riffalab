"""Biblioteca: indexa as pastas do usuário e permite comparar o que já existe."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QAbstractItemView, QFileDialog, QHBoxLayout, QHeaderView,
                               QLabel, QLineEdit, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from ...config import Config, EXTENSOES_AUDIO
from ...audio_probe import analisar
from ...db import Banco
from ...models import hhmmss, bytes_legivel
from ...workers import EXECUTOR_GLOBAL
from ..theme import PALETA


class LibraryPage(QWidget):
    mensagem = Signal(str)

    def __init__(self, config: Config, banco: Banco, pai: Optional[QWidget] = None) -> None:
        super().__init__(pai)
        self.config = config
        self.banco = banco

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(26, 22, 26, 16)
        raiz.setSpacing(13)

        topo = QHBoxLayout()
        col = QVBoxLayout()
        col.setSpacing(2)
        t = QLabel("Biblioteca")
        t.setObjectName("titulo")
        st = QLabel("Seus arquivos indexados: codec, bitrate, taxa de amostragem e capa.")
        st.setObjectName("subtitulo")
        col.addWidget(t)
        col.addWidget(st)
        topo.addLayout(col, 1)

        self.btn_escolher = QPushButton("Escolher pasta")
        self.btn_escolher.clicked.connect(self._escolher_pasta)
        topo.addWidget(self.btn_escolher, 0, Qt.AlignBottom)

        self.btn_indexar = QPushButton("Indexar agora")
        self.btn_indexar.setObjectName("primario")
        self.btn_indexar.clicked.connect(self.indexar)
        topo.addWidget(self.btn_indexar, 0, Qt.AlignBottom)
        raiz.addLayout(topo)

        linha = QHBoxLayout()
        self.filtro = QLineEdit()
        self.filtro.setPlaceholderText("Filtrar por título, artista, álbum ou caminho…")
        self.filtro.textChanged.connect(self._carregar)
        linha.addWidget(self.filtro, 1)
        self.btn_abrir = QPushButton("Abrir arquivo")
        self.btn_abrir.setObjectName("fantasma")
        self.btn_abrir.clicked.connect(self._abrir_selecionado)
        linha.addWidget(self.btn_abrir)
        raiz.addLayout(linha)

        self.resumo = QLabel("Ainda não indexado.")
        self.resumo.setObjectName("dim")
        raiz.addWidget(self.resumo)

        self.tabela = QTableWidget(0, 8)
        self.tabela.setHorizontalHeaderLabels(
            ["Título", "Artista", "Álbum", "Codec", "kbps", "kHz", "Duração", "Capa"])
        self.tabela.verticalHeader().setVisible(False)
        self.tabela.setAlternatingRowColors(True)
        self.tabela.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabela.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabela.doubleClicked.connect(self._abrir_selecionado)
        cab = self.tabela.horizontalHeader()
        cab.setSectionResizeMode(0, QHeaderView.Stretch)
        cab.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        cab.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        for i in range(3, 8):
            cab.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        raiz.addWidget(self.tabela, 1)

        self._carregar()

    # ------------------------------------------------------------------ pasta
    def _escolher_pasta(self) -> None:
        inicial = self.config.get("biblioteca_local") or str(Path.home())
        pasta = QFileDialog.getExistingDirectory(self, "Pasta da sua biblioteca", inicial)
        if pasta:
            self.config.update(biblioteca_local=pasta)
            self.mensagem.emit(f"Biblioteca local: {pasta}")

    # --------------------------------------------------------------- indexar
    def indexar(self) -> None:
        pasta = self.config.pasta_biblioteca_local
        if not pasta:
            pasta_str = QFileDialog.getExistingDirectory(self, "Pasta para indexar", str(Path.home()))
            if not pasta_str:
                return
            self.config.update(biblioteca_local=pasta_str)
            pasta = Path(pasta_str)
        self.btn_indexar.setEnabled(False)
        self.btn_indexar.setText("indexando…")
        self.resumo.setText(f"Lendo {pasta} …")
        EXECUTOR_GLOBAL.rodar(self._varrer, pasta,
                              ao_resultado=self._indexado,
                              ao_erro=self._erro_indexacao)

    def _varrer(self, pasta: Path) -> List[Tuple[Path, object]]:
        arquivos = [p for p in pasta.rglob("*")
                    if p.is_file() and p.suffix.lower() in EXTENSOES_AUDIO]
        saida = []
        for arq in arquivos:
            try:
                saida.append((arq, analisar(arq)))
            except Exception:
                continue
        return saida

    def _indexado(self, itens) -> None:
        for arq, info in itens:
            try:
                st = Path(arq).stat()
            except OSError:
                continue
            tags = info.tags or {}
            self.banco.indexar(
                str(arq),
                titulo=tags.get("titulo") or Path(arq).stem,
                artista=tags.get("artista") or Path(arq).parent.name,
                album=tags.get("album") or "",
                ano=str(tags.get("ano") or ""),
                codec=info.codec, bitrate=info.bitrate_kbps, sample_rate=info.sample_rate,
                duracao=info.duracao_s, tamanho=info.tamanho or st.st_size,
                tem_capa=info.tem_capa, modificado=st.st_mtime,
            )
        self.btn_indexar.setEnabled(True)
        self.btn_indexar.setText("Indexar agora")
        self.mensagem.emit(f"{len(itens)} arquivo(s) indexado(s)")
        self._carregar()

    def _erro_indexacao(self, msg: str) -> None:
        self.btn_indexar.setEnabled(True)
        self.btn_indexar.setText("Indexar agora")
        self.resumo.setText(f"Erro ao indexar: {msg}")
        self.mensagem.emit(f"Erro ao indexar: {msg[:120]}")

    # ------------------------------------------------------------- visualizar
    def _carregar(self) -> None:
        linhas = self.banco.listar_biblioteca(self.filtro.text().strip())
        self.tabela.setRowCount(len(linhas))
        for r, dado in enumerate(linhas):
            valores = [
                dado.get("titulo") or Path(dado["caminho"]).stem,
                dado.get("artista") or "", dado.get("album") or "",
                (dado.get("codec") or "").upper(),
                str(dado.get("bitrate") or "-"),
                f"{(dado.get('sample_rate') or 0) / 1000:g}" if dado.get("sample_rate") else "-",
                hhmmss(dado.get("duracao")),
                "sim" if dado.get("tem_capa") else "não",
            ]
            for c, valor in enumerate(valores):
                item = QTableWidgetItem(str(valor))
                if c >= 3:
                    item.setTextAlignment(Qt.AlignCenter)
                if c == 7:
                    item.setForeground(Qt.green if dado.get("tem_capa") else Qt.gray)
                item.setToolTip(dado["caminho"])
                if c == 0:
                    item.setData(Qt.UserRole, dado["caminho"])
                self.tabela.setItem(r, c, item)

        stats = self.banco.estatisticas()
        if stats["arquivos"]:
            self.resumo.setText(
                f"{stats['arquivos']} arquivo(s)  ·  {bytes_legivel(stats['bytes'])}  ·  "
                f"{stats['com_capa']} com capa embutida  ·  pasta: "
                f"{self.config.get('biblioteca_local') or '-'}")
        else:
            self.resumo.setText("Nenhum arquivo indexado. Escolha uma pasta e clique em "
                                "“Indexar agora”.")

    def _abrir_selecionado(self) -> None:
        linha = self.tabela.currentRow()
        if linha < 0:
            return
        item = self.tabela.item(linha, 0)
        if not item:
            return
        caminho = item.data(Qt.UserRole)
        if not caminho or not os.path.exists(caminho):
            self.mensagem.emit("Arquivo não encontrado (pode ter sido movido).")
            return
        try:
            if os.name == "nt":
                os.startfile(caminho)                      # noqa: S606
            elif sys.platform == "darwin":
                subprocess.Popen(["open", caminho])
            else:
                subprocess.Popen(["xdg-open", caminho])
        except Exception as exc:                           # noqa: BLE001
            self.mensagem.emit(f"Não foi possível abrir: {exc}")

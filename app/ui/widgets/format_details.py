"""Comparação dos dados informados para cada formato, sem baixar áudio."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QDialogButtonBox,
                               QHeaderView, QLabel, QPlainTextEdit, QTableWidget, QTableWidgetItem,
                               QVBoxLayout)

from ...formatos_detalhes import campos
from ...models import AudioFormat, TrackResult


class DialogoFormatos(QDialog):
    def __init__(self, resultado: TrackResult, selecionado: AudioFormat | None = None, pai=None):
        super().__init__(pai)
        self.setWindowTitle('Comparar formatos de áudio')
        self.resize(1050, 600)
        self.formatos = resultado.formatos_ordenados()
        layout = QVBoxLayout(self)
        titulo = QLabel('Formatos encontrados para: ' + (resultado.titulo or 'música'))
        titulo.setTextFormat(Qt.PlainText)
        titulo.setWordWrap(True)
        layout.addWidget(titulo)
        aviso = QLabel('Selecione uma linha para ver mais detalhes. Valores são informados pela fonte; '
                       'bitrate pode ser estimado. A ordem prioriza codec sem perda e bitrate informado; não mede qualidade sonora nem compara codecs com certeza. '
                       'Bitrate total pode incluir vídeo. “Não informado” não significa zero.')
        aviso.setTextFormat(Qt.PlainText)
        aviso.setWordWrap(True)
        layout.addWidget(aviso)
        self.tabela = QTableWidget(len(self.formatos), 8)
        colunas = ('ID', 'Codec', 'Bitrate áudio', 'Amostragem', 'Canais', 'Contêiner', 'Tipo', 'Tamanho')
        self.tabela.setHorizontalHeaderLabels(list(colunas))
        self.tabela.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabela.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tabela.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabela.verticalHeader().setVisible(False)
        self.tabela.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        for linha, formato in enumerate(self.formatos):
            valores = campos(formato)
            for coluna, chave in enumerate(colunas):
                item = QTableWidgetItem(valores[chave])
                item.setToolTip(valores[chave])
                self.tabela.setItem(linha, coluna, item)
        layout.addWidget(self.tabela, 1)
        self.detalhes = QPlainTextEdit()
        self.detalhes.setReadOnly(True)
        self.detalhes.setMinimumHeight(110)
        self.detalhes.setMaximumHeight(180)
        layout.addWidget(self.detalhes)
        botoes = QDialogButtonBox(QDialogButtonBox.Cancel)
        self.usar = botoes.addButton('Usar formato selecionado', QDialogButtonBox.AcceptRole)
        self.usar.setEnabled(bool(self.formatos))
        botoes.accepted.connect(self.accept)
        botoes.rejected.connect(self.reject)
        layout.addWidget(botoes)
        self.tabela.itemSelectionChanged.connect(self._atualizar)
        self.tabela.cellDoubleClicked.connect(lambda *_: self.accept())
        if self.formatos:
            indice = next((i for i, f in enumerate(self.formatos)
                           if selecionado and f.format_id == selecionado.format_id), 0)
            self.tabela.selectRow(indice)
            self._atualizar()

    def formato_selecionado(self) -> AudioFormat | None:
        linha = self.tabela.currentRow()
        return self.formatos[linha] if 0 <= linha < len(self.formatos) else None

    def _atualizar(self) -> None:
        formato = self.formato_selecionado()
        if not formato:
            self.detalhes.setPlainText('Selecione um formato.')
            return
        info = campos(formato)
        self.detalhes.setPlainText('\n'.join(f'{k}: {info[k]}' for k in
            ('Bitrate total', 'Bits por amostra', 'Codec de vídeo', 'Proteção DRM', 'Idioma', 'Protocolo', 'Nota da fonte', 'Métodos', 'Divergências entre métodos')))

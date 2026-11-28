"""Editor explícito para as tags e a capa frontal de um MP3 existente."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PySide6.QtWidgets import QDialog, QMessageBox, QPushButton, QHBoxLayout

from ... import editar_mp3
from ...models import CoverResult, TrackResult
from ...texto import normalizar
from ..dialogos import DialogoCapas
from .downloads_page import DialogoEditarDados


class DialogoEditarMP3(DialogoEditarDados):
    def __init__(self, snapshot: dict, pai=None):
        campos = snapshot['campos']
        r = TrackResult(uid='mp3-local', fonte='biblioteca_local', titulo=campos['titulo'],
                        artista=campos['artista'], album=campos['album'],
                        extra={'titulo_original': campos['titulo']})
        meta = SimpleNamespace(**campos, artistas_participantes=[])
        linha = SimpleNamespace(pedido={'resultado': r, 'edicao': {}}, preparacao={'meta': meta})
        super().__init__(linha, pai)
        self.snapshot = snapshot
        self.capa_acao = 'manter'
        self.capa_dados = b''
        self.setWindowTitle('Editar dados e capa do MP3')
        self.layout().itemAt(0).widget().setText(
            'Edite só o que deseja alterar. O áudio não será baixado nem recodificado. '
            'Ao salvar, uma cópia de segurança do arquivo original será guardada na mesma pasta. '
            'Se trocar o álbum, confira ano e faixa. As sugestões da IA e dos catálogos podem estar erradas; confira antes de salvar.')
        formulario = self.layout().itemAt(1).layout()
        formulario.labelForField(self.campos['artista']).setText('Artista(s) no MP3')
        formulario.labelForField(self.campos['artistas_participantes']).setText('Acrescentar participações')
        self.campos['artistas_participantes'].setPlaceholderText('Opcional; artistas existentes ficam no campo acima')
        formulario.labelForField(self.campos['ano']).setText('Ano ou data (AAAA-MM-DD)')
        formulario.labelForField(self.campos['faixa']).setText('Faixa (número ou número/total)')
        linha_capa = QHBoxLayout()
        self.btn_capa_existente = QPushButton('Trocar ou remover capa frontal…')
        self.btn_capa_existente.clicked.connect(self._escolher_capa_existente)
        linha_capa.addWidget(self.btn_capa_existente)
        self.btn_manter_capa = QPushButton('Manter a capa original')
        self.btn_manter_capa.setEnabled(False)
        self.btn_manter_capa.clicked.connect(self._manter_capa)
        linha_capa.addWidget(self.btn_manter_capa)
        self.layout().insertLayout(self.layout().count() - 1, linha_capa)
        self.btn_rever_ia.setToolTip('Opcional. Envia título, artista, álbum e sua observação; o áudio e o caminho não são enviados.')

    def _manter_capa(self):
        self.capa_acao, self.capa_dados = 'manter', b''
        self.btn_capa_existente.setText('Trocar ou remover capa frontal…')
        self.btn_manter_capa.setEnabled(False)

    def _escolher_capa_existente(self):
        musica = {'titulo': self.campos['titulo'].text().strip(),
                  'artista': self.campos['artista'].text().strip()}
        capa = DialogoCapas(self, CoverResult(), musica)
        capa.btn_sem.setText('Remover capa frontal')
        capa.btn_sem.setToolTip('Remove somente as imagens frontais; outras imagens são mantidas.')
        botao = QPushButton('Escolher imagem do computador')
        botao.clicked.connect(capa._escolher_arquivo)
        capa.layout().addWidget(botao)
        if capa.exec() != QDialog.Accepted:
            return
        if capa.recusou:
            self.capa_acao, self.capa_dados = 'remover', b''
            self.btn_capa_existente.setText('Capa frontal será removida ao salvar')
        elif capa.escolhida and capa.escolhida.caminho:
            try:
                caminho = Path(capa.escolhida.caminho)
                if caminho.stat().st_size > 15 * 1024 * 1024:
                    raise ValueError('Imagem maior que 15 MB.')
                dados = caminho.read_bytes()
                editar_mp3._validar_capa(dados)
                from PySide6.QtGui import QImage
                if QImage.fromData(dados).isNull():
                    raise ValueError('Não foi possível ler a imagem selecionada.')
            except (OSError, ValueError) as exc:
                QMessageBox.warning(self, 'Imagem inválida', str(exc))
                return
            self.capa_acao, self.capa_dados = 'trocar', dados
            self.btn_capa_existente.setText('Nova capa selecionada; será aplicada ao salvar')
        else:
            return
        self.btn_manter_capa.setEnabled(True)

    def alteracoes(self):
        atuais = {k: c.text().strip() for k, c in self.campos.items()}
        mudancas = {k: atuais[k] for k in editar_mp3.CAMPOS
                    if atuais[k] != self._valores_iniciais[k]}
        participantes = atuais['artistas_participantes']
        if participantes != self._valores_iniciais['artistas_participantes'] and participantes:
            artista = mudancas.get('artista', atuais['artista'])
            novos = []
            existente = normalizar(artista)
            for nome in participantes.replace(';', ',').split(','):
                nome = nome.strip()
                chave = normalizar(nome)
                if chave and chave not in existente:
                    novos.append(nome)
                    existente += ' ' + chave
            if novos:
                mudancas['artista'] = (artista + ' feat. ' if artista else '') + ', '.join(novos)
        return mudancas

    def _validar(self):
        try:
            editar_mp3.validar_alteracoes(self.alteracoes())
        except ValueError as exc:
            QMessageBox.warning(self, 'Dados inválidos', str(exc))
            return
        self.accept()

"""Visualizador e edição explícita de tags e capas em MP3s locais."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QFileDialog, QFrame,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QDialog, QMessageBox)

from ... import visualizador_mp3, editar_mp3
from ...config import Config
from ...models import hhmmss
from ...workers import EXECUTOR_GLOBAL
from ..theme import PALETA
from .editar_mp3_dialog import DialogoEditarMP3


class MP3ViewerPage(QWidget):
    mensagem = Signal(str)

    def __init__(self, config: Config, pai=None) -> None:
        super().__init__(pai)
        self.config = config
        self._geracao = 0
        self._geracao_detalhe = 0
        self._encerrando = False
        self._iniciado = False
        self._abrindo_editor = False
        self._salvando = False
        self._selecionar_apos_atualizar = ''
        self._itens = []
        self._imagens = []
        self._caminho_atual = ''
        self._detalhe_valido = False
        self._modo = 'pasta'
        self._local = str(config.pasta_saida)

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(18, 14, 18, 14)
        raiz.setSpacing(8)
        titulo = QLabel('Visualizar MP3 e capas')
        titulo.setObjectName('titulo')
        raiz.addWidget(titulo)
        desc = QLabel('Veja e, quando quiser, corrija dados e capa dos seus MP3s sem baixar novamente.')
        desc.setObjectName('subtitulo')
        desc.setWordWrap(True)
        raiz.addWidget(desc)

        acoes = QHBoxLayout()
        self.btn_pasta = QPushButton('Escolher pasta de MP3s')
        self.btn_pasta.clicked.connect(self._escolher_pasta)
        self.btn_arquivo = QPushButton('Escolher um MP3')
        self.btn_arquivo.clicked.connect(self._escolher_arquivo)
        self.btn_atualizar = QPushButton('Atualizar lista')
        self.btn_atualizar.setObjectName('primario')
        self.btn_atualizar.clicked.connect(self.atualizar)
        for botao in (self.btn_pasta, self.btn_arquivo, self.btn_atualizar):
            acoes.addWidget(botao)
        acoes.addStretch(1)
        raiz.addLayout(acoes)
        self.lbl_pasta = QLabel('Pasta de saída: ' + self._local)
        self.lbl_pasta.setTextFormat(Qt.PlainText)
        self.lbl_pasta.setWordWrap(True)
        self.lbl_pasta.setTextInteractionFlags(Qt.TextSelectableByMouse)
        raiz.addWidget(self.lbl_pasta)
        self.filtro = QLineEdit()
        self.filtro.setPlaceholderText('Filtrar por título, artista, álbum ou caminho…')
        self.filtro.textChanged.connect(self._filtrar)
        raiz.addWidget(self.filtro)
        self.resumo = QLabel('Selecione uma pasta ou arquivo para visualizar.')
        self.resumo.setWordWrap(True)
        raiz.addWidget(self.resumo)

        corpo = QHBoxLayout()
        self.tabela = QTableWidget(0, 4)
        self.tabela.setHorizontalHeaderLabels(['Título', 'Artista', 'Álbum', 'Imagem ID3'])
        self.tabela.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabela.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tabela.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabela.verticalHeader().setVisible(False)
        self.tabela.setAlternatingRowColors(True)
        cab = self.tabela.horizontalHeader()
        cab.setSectionResizeMode(0, QHeaderView.Stretch)
        cab.setSectionResizeMode(1, QHeaderView.Stretch)
        cab.setSectionResizeMode(2, QHeaderView.Stretch)
        cab.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.tabela.itemSelectionChanged.connect(self._selecionou)
        corpo.addWidget(self.tabela, 2)

        painel = QFrame()
        painel.setObjectName('cartao')
        painel.setMinimumWidth(300)
        layout = QVBoxLayout(painel)
        self.lbl_titulo = QLabel('Selecione um MP3 na lista')
        self.lbl_titulo.setTextFormat(Qt.PlainText)
        self.lbl_titulo.setWordWrap(True)
        layout.addWidget(self.lbl_titulo)
        self.lbl_album = QLabel('')
        self.lbl_album.setTextFormat(Qt.PlainText)
        self.lbl_album.setWordWrap(True)
        layout.addWidget(self.lbl_album)
        self.lbl_capa = QLabel('Nenhuma imagem para mostrar')
        self.lbl_capa.setAlignment(Qt.AlignCenter)
        self.lbl_capa.setFixedSize(260, 260)
        self.lbl_capa.setStyleSheet(f"background: {PALETA['bg0']}; border: 1px solid {PALETA['border']};")
        layout.addWidget(self.lbl_capa, 0, Qt.AlignHCenter)
        self.seletor = QComboBox()
        self.seletor.currentIndexChanged.connect(self._mostrar_imagem)
        self.seletor.hide()
        layout.addWidget(self.seletor)
        self.lbl_estado = QLabel('A capa mostrada é lida do próprio MP3, não da internet.')
        self.lbl_estado.setWordWrap(True)
        self.lbl_estado.setTextFormat(Qt.PlainText)
        layout.addWidget(self.lbl_estado)
        self.lbl_caminho = QLabel('')
        self.lbl_caminho.setWordWrap(True)
        self.lbl_caminho.setTextFormat(Qt.PlainText)
        self.lbl_caminho.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.lbl_caminho)
        self.btn_editar = QPushButton('Editar dados e capa')
        self.btn_editar.setObjectName('primario')
        self.btn_editar.setEnabled(False)
        self.btn_editar.clicked.connect(self._editar_mp3)
        layout.addWidget(self.btn_editar)
        layout.addStretch(1)
        corpo.addWidget(painel, 1)
        raiz.addLayout(corpo, 1)
        nota = QLabel('“Sem imagem ID3” significa que não há imagem APIC nas tags. '
                      'Alguns aparelhos podem mostrar imagem de outra fonte, como arquivo da pasta ou cache.')
        nota.setWordWrap(True)
        nota.setObjectName('dim')
        raiz.addWidget(nota)

    def abrir_inicial(self) -> None:
        if not self._iniciado:
            self._iniciado = True
            self._local = str(self.config.pasta_saida)
            self.atualizar()

    def _escolher_pasta(self) -> None:
        pasta = QFileDialog.getExistingDirectory(self, 'Escolha a pasta com os MP3s', self._local)
        if pasta:
            self._modo, self._local = 'pasta', pasta
            self.atualizar()

    def _escolher_arquivo(self) -> None:
        arquivo, _ = QFileDialog.getOpenFileName(self, 'Escolha um MP3', self._local, 'Áudio MP3 (*.mp3 *.MP3)')
        if arquivo:
            self._modo, self._local = 'arquivo', arquivo
            self.atualizar()

    def atualizar(self) -> None:
        self._geracao += 1
        self._geracao_detalhe += 1
        geracao = self._geracao
        self.lbl_pasta.setText(('Pasta: ' if self._modo == 'pasta' else 'Arquivo: ') + self._local)
        self.resumo.setText('Lendo os MP3s, sem modificar arquivos…')
        self._itens = []
        self._preencher_tabela()
        local, modo = self._local, self._modo
        def ler():
            if modo == 'arquivo':
                if not Path(local).is_file() or Path(local).suffix.lower() != '.mp3':
                    raise ValueError('Arquivo MP3 indisponível.')
                return {'itens': [visualizador_mp3.ler_mp3(local)], 'erros': [], 'truncado': False}
            return visualizador_mp3.listar_mp3(local)
        EXECUTOR_GLOBAL.rodar(ler,
            ao_resultado=lambda dados: self._lista_pronta(geracao, dados),
            ao_erro=lambda erro: self._lista_falhou(geracao, erro))

    def _lista_pronta(self, geracao: int, dados: dict) -> None:
        if self._encerrando or geracao != self._geracao:
            return
        self._itens = dados['itens']
        erros_arquivos = sum(x['estado'] == 'Erro de leitura' for x in self._itens)
        resumo = f"{len(self._itens)} MP3(s) encontrado(s) · {sum(x['quantidade'] > 0 for x in self._itens)} com imagem ID3"
        if erros_arquivos or dados.get('erros'):
            resumo += f" · {erros_arquivos + len(dados.get('erros', []))} erro(s) de leitura"
        if dados.get('truncado'):
            resumo += f" · limite de {visualizador_mp3.MAX_ARQUIVOS}; escolha uma subpasta para ver os demais"
        self.resumo.setText(resumo)
        preferido, self._selecionar_apos_atualizar = self._selecionar_apos_atualizar, ''
        self._preencher_tabela(preferido)

    def _lista_falhou(self, geracao: int, erro: str) -> None:
        if not self._encerrando and geracao == self._geracao:
            self.resumo.setText('Não foi possível ler: ' + erro[:250])

    def _filtrar(self, *_args) -> None:
        self._preencher_tabela()

    def _preencher_tabela(self, preferido: str = '') -> None:
        preferido = preferido or self._caminho_atual
        texto = self.filtro.text().casefold().strip()
        visiveis = [i for i in self._itens if not texto or texto in ' '.join(
            str(i.get(k) or '') for k in ('titulo', 'artista', 'album', 'caminho')).casefold()]
        self.tabela.blockSignals(True)
        self.tabela.setRowCount(len(visiveis))
        for linha, dados in enumerate(visiveis):
            valores = (dados['titulo'], dados['artista'], dados['album'],
                       f"Sim ({dados['quantidade']})" if dados['quantidade'] else dados['estado'])
            for coluna, valor in enumerate(valores):
                celula = QTableWidgetItem(str(valor))
                celula.setToolTip(dados.get('erro') or dados['caminho'])
                if coluna == 0:
                    celula.setData(Qt.UserRole, dados['caminho'])
                self.tabela.setItem(linha, coluna, celula)
        self.tabela.blockSignals(False)
        self._limpar_detalhe()
        if visiveis:
            indice = next((n for n, x in enumerate(visiveis) if x['caminho'] == preferido), 0)
            self.tabela.selectRow(indice)
            self._selecionou()

    def _limpar_detalhe(self) -> None:
        self._geracao_detalhe += 1
        self._caminho_atual = ''
        self._detalhe_valido = False
        self._imagens = []
        self.btn_editar.setEnabled(False)
        self.seletor.hide()
        self.lbl_titulo.setText('Selecione um MP3 na lista')
        self.lbl_album.clear()
        self.lbl_capa.clear()
        self.lbl_capa.setText('Nenhuma imagem para mostrar')
        self.lbl_estado.setText('A capa mostrada é lida do próprio MP3, não da internet.')
        self.lbl_caminho.clear()

    def _selecionou(self) -> None:
        item = self.tabela.item(self.tabela.currentRow(), 0)
        if not item:
            self._limpar_detalhe()
            return
        caminho = item.data(Qt.UserRole)
        if caminho == self._caminho_atual:
            return
        self._geracao_detalhe += 1
        geracao = self._geracao_detalhe
        self._caminho_atual = caminho
        self._detalhe_valido = False
        self.btn_editar.setEnabled(False)
        self._imagens = []
        self.lbl_titulo.setText('Lendo tags…')
        self.lbl_album.clear()
        self.lbl_estado.setText('Lendo as tags e imagens embutidas…')
        self.lbl_capa.clear()
        self.lbl_capa.setText('Lendo imagem…')
        self.lbl_caminho.setText(caminho)
        self.seletor.hide()
        EXECUTOR_GLOBAL.rodar(visualizador_mp3.ler_mp3, caminho, incluir_imagens=True,
            ao_resultado=lambda dados: self._detalhe_pronto(geracao, dados),
            ao_erro=lambda erro: self._detalhe_falhou(geracao, erro))

    def _detalhe_pronto(self, geracao: int, dados: dict) -> None:
        if self._encerrando or geracao != self._geracao_detalhe:
            return
        self._detalhe_valido = not bool(dados.get('erro'))
        self.btn_editar.setEnabled(self._detalhe_valido and not self._salvando and not self._abrindo_editor)
        self.lbl_titulo.setText(' — '.join(filter(None, [dados['artista'], dados['titulo']])))
        self.lbl_album.setText('\n'.join([
            'Álbum: ' + (dados['album'] or 'não informado'),
            'Artista do álbum: ' + (dados.get('artista_album') or 'não informado'),
            'Gênero: ' + (dados.get('genero') or 'não informado'),
            'Ano: ' + (dados.get('ano') or 'não informado'),
            'Faixa: ' + (dados.get('faixa') or 'não informada'),
            'Duração: ' + (hhmmss(dados['duracao_s']) if dados.get('duracao_s') else 'não disponível'),
        ]))
        self.lbl_caminho.setText(dados['caminho'])
        self._imagens = dados['imagens']
        self.seletor.blockSignals(True)
        self.seletor.clear()
        for numero, imagem in enumerate(self._imagens, 1):
            tipo = 'capa frontal' if imagem['tipo'] == 3 else f"tipo ID3 {imagem['tipo']}"
            self.seletor.addItem(f"Imagem {numero}: {tipo}" + (f" · {imagem['descricao']}" if imagem['descricao'] else ''))
        self.seletor.blockSignals(False)
        self.seletor.setVisible(len(self._imagens) > 1)
        if self._imagens:
            self._mostrar_imagem(0)
        else:
            self.lbl_capa.clear()
            self.lbl_capa.setText('Não foi possível verificar' if dados.get('erro') else 'Nenhuma imagem ID3')
            self.lbl_estado.setText(dados.get('erro') or dados['estado'] + '. Nenhuma imagem APIC foi mostrada.')

    def _detalhe_falhou(self, geracao: int, erro: str) -> None:
        if not self._encerrando and geracao == self._geracao_detalhe:
            self.lbl_capa.setText('Não foi possível ler')
            self.lbl_estado.setText(erro[:250])

    def _editar_mp3(self) -> None:
        if not self._caminho_atual or self._abrindo_editor or self._salvando:
            return
        caminho = self._caminho_atual
        self._abrindo_editor = True
        self.btn_editar.setEnabled(False)
        self.resumo.setText('Preparando edição segura do MP3…')

        def pronto(snapshot):
            self._abrindo_editor = False
            if self._encerrando:
                return
            if caminho != self._caminho_atual:
                self.btn_editar.setEnabled(self._detalhe_valido and not self._salvando)
                return
            self.btn_editar.setEnabled(self._detalhe_valido)
            self.resumo.setText('Revise os dados e a capa; nada será alterado até salvar.')
            dialogo = DialogoEditarMP3(snapshot, self)
            if dialogo.exec() != QDialog.Accepted or self._encerrando:
                return
            alteracoes = dialogo.alteracoes()
            if not alteracoes and dialogo.capa_acao == 'manter':
                self.resumo.setText('Nenhuma alteração foi solicitada.')
                return
            resposta = QMessageBox.question(self, 'Confirmar edição do MP3',
                'Salvar as alterações neste arquivo?\n\n' + caminho +
                '\n\nUma cópia de segurança será criada na mesma pasta. O áudio não será recodificado.',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if resposta != QMessageBox.Yes:
                return
            self._salvar_edicao(snapshot, alteracoes, dialogo.capa_acao, dialogo.capa_dados)

        def falhou(erro):
            self._abrindo_editor = False
            if not self._encerrando:
                self.btn_editar.setEnabled(self._detalhe_valido and not self._salvando)
                self.resumo.setText('Não foi possível abrir o editor.')
                QMessageBox.warning(self, 'Não foi possível editar', erro[:500])
        try:
            EXECUTOR_GLOBAL.rodar(editar_mp3.abrir, caminho, ao_resultado=pronto, ao_erro=falhou)
        except Exception as exc:
            falhou(str(exc))

    def _salvar_edicao(self, snapshot, alteracoes, capa_acao, capa_dados):
        self._salvando = True
        for widget in (self.btn_editar, self.btn_pasta, self.btn_arquivo, self.btn_atualizar, self.tabela, self.filtro):
            widget.setEnabled(False)
        self.resumo.setText('Salvando tags e criando backup… Aguarde antes de fechar o aplicativo.')

        def terminar():
            self._salvando = False
            for widget in (self.btn_pasta, self.btn_arquivo, self.btn_atualizar, self.tabela, self.filtro):
                widget.setEnabled(True)
            self.btn_editar.setEnabled(self._detalhe_valido)

        def pronto(resultado):
            terminar()
            if self._encerrando:
                return
            self._selecionar_apos_atualizar = snapshot['caminho']
            self.atualizar()
            self.mensagem.emit('MP3 atualizado. Backup: ' + resultado['backup'])
            QMessageBox.information(self, 'MP3 atualizado',
                'Dados e capa salvos sem recodificar o áudio.\n\nBackup do original:\n' + resultado['backup'])

        def falhou(erro):
            terminar()
            if not self._encerrando:
                self.resumo.setText('Não foi possível salvar. O arquivo original não foi substituído.')
                QMessageBox.warning(self, 'Não foi possível salvar o MP3', erro[:700])
        try:
            EXECUTOR_GLOBAL.rodar(editar_mp3.salvar, snapshot, alteracoes, capa_acao, capa_dados,
                                  ao_resultado=pronto, ao_erro=falhou)
        except Exception as exc:
            falhou(str(exc))

    def _mostrar_imagem(self, indice: int) -> None:
        if indice < 0 or indice >= len(self._imagens):
            return
        imagem = self._imagens[indice]
        pixmap = QPixmap()
        if not imagem['dados'] or not pixmap.loadFromData(imagem['dados']):
            self.lbl_capa.clear()
            self.lbl_capa.setText('Imagem não exibível')
            self.lbl_estado.setText('Há uma imagem APIC, mas não foi possível exibi-la (formato, dados ou tamanho).')
            return
        self.lbl_capa.setPixmap(pixmap.scaled(258, 258, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.lbl_estado.setText(f"Imagem embutida no MP3 · {imagem['mime'] or 'tipo desconhecido'} · {imagem['tamanho']} bytes")

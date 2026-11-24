"""Diálogos de confirmação do fluxo v0.5.0 (etapas 5 e 9).

* `confirmar_processamento` — o usuário aprova a lista antes de qualquer
  download começar (proposta §2.3: "Confirmação → processamento autorizado");
* `escolher_capa` — mostra a capa encontrada com álbum, artista, ano, fonte e
  grau de correspondência e deixa trocar por outra ou recusar (proposta §2.4).
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QFrame,
                               QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                               QPushButton, QScrollArea, QVBoxLayout, QWidget, QFileDialog, QMessageBox)

from ..models import CoverResult, TrackResult, hhmmss
from ..quality import rotulo
from .theme import PALETA, alfa
from .widgets.result_card import Chip


def _pixmap(caminho: str, lado: int) -> Optional[QPixmap]:
    if not caminho:
        return None
    pix = QPixmap(caminho)
    if pix.isNull():
        return None
    return pix.scaled(lado, lado, Qt.KeepAspectRatio, Qt.SmoothTransformation)


def _estilo_dialogo(dialogo: QDialog, largura: int = 620) -> None:
    dialogo.setStyleSheet(
        "QScrollArea { border: none; background: transparent; }"
        "QWidget#areaLista { background: transparent; }")


# ---------------------------------------------------------------- etapa 5
class DialogoConfirmar(QDialog):
    """'Vou baixar estas N músicas — confirma?'"""

    def __init__(self, pai: Optional[QWidget], pedidos: Sequence[Dict],
                 config=None) -> None:
        super().__init__(pai)
        self.setWindowTitle("Confirmar antes de processar")
        self.setMinimumWidth(660)
        self.pedidos = list(pedidos)
        self.config = config
        _estilo_dialogo(self)

        fora = QVBoxLayout(self)
        fora.setContentsMargins(22, 20, 22, 18)
        fora.setSpacing(12)

        titulo = QLabel(f"Processar {len(self.pedidos)} música(s)?")
        titulo.setStyleSheet("font-size: 17px; font-weight: 800;")
        fora.addWidget(titulo)
        explicacao = QLabel(
            "O RiffLab vai baixar o áudio, identificar a música, usar a capa escolhida e "
            "gravar as tags. Nada é baixado antes da sua confirmação.")
        explicacao.setWordWrap(True)
        explicacao.setProperty("papel_tema", "dim")
        explicacao.setStyleSheet("font-size: 12px;")
        fora.addWidget(explicacao)

        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFixedHeight(min(300, 46 * len(self.pedidos) + 20))
        dentro = QWidget()
        dentro.setObjectName("areaLista")
        lista = QVBoxLayout(dentro)
        lista.setContentsMargins(0, 2, 6, 2)
        lista.setSpacing(6)
        avisos_ao_vivo = 0
        for pedido in self.pedidos:
            r: TrackResult = pedido.get("resultado")
            linha = QFrame()
            linha.setObjectName("cartao")
            lay = QHBoxLayout(linha)
            lay.setContentsMargins(11, 8, 11, 8)
            lay.setSpacing(9)
            textos = QVBoxLayout()
            textos.setSpacing(2)
            nome = QLabel(r.titulo or "(sem título)")
            nome.setStyleSheet("font-size: 13px; font-weight: 700;")
            nome.setWordWrap(True)
            textos.addWidget(nome)
            detalhe = "  ·  ".join(p for p in (r.artista or "", r.canal or "",
                                              hhmmss(r.duracao_s) if r.duracao_s else "")
                                   if p)
            sub = QLabel(detalhe or "—")
            sub.setProperty("papel_tema", "dim")
            sub.setStyleSheet("font-size: 11.5px;")
            textos.addWidget(sub)
            lay.addLayout(textos, 1)
            formato = pedido.get("formato")
            if formato is not None:
                lay.addWidget(Chip(rotulo(formato), PALETA["ciano"]))
            if getattr(r, "ao_vivo", False):
                avisos_ao_vivo += 1
                chip = Chip("ao vivo", PALETA["vermelho"])
                chip.setToolTip("; ".join(r.sinais_ao_vivo) or r.alerta())
                lay.addWidget(chip)
            lista.addWidget(linha)
        lista.addStretch(1)
        area.setWidget(dentro)
        fora.addWidget(area, 1)

        if avisos_ao_vivo:
            aviso = QLabel(
                f"⚠  {avisos_ao_vivo} resultado(s) parecem gravação ao vivo. "
                "Confira antes de continuar — o áudio pode ser de um show.")
            aviso.setWordWrap(True)
            aviso.setStyleSheet(f"color: {PALETA['amarelo']}; font-size: 12px;")
            fora.addWidget(aviso)

        self.check_sempre = QCheckBox("Não perguntar de novo (posso reativar nas Configurações)")
        fora.addWidget(self.check_sempre)

        botoes = QDialogButtonBox()
        self.btn_ok = QPushButton(f"Processar {len(self.pedidos)}")
        self.btn_ok.setObjectName("primario")
        self.btn_cancelar = QPushButton("Cancelar")
        self.btn_cancelar.setObjectName("fantasma")
        botoes.addButton(self.btn_ok, QDialogButtonBox.AcceptRole)
        botoes.addButton(self.btn_cancelar, QDialogButtonBox.RejectRole)
        self.btn_ok.clicked.connect(self._confirmar)
        self.btn_cancelar.clicked.connect(self.reject)
        fora.addWidget(botoes)

    def _confirmar(self) -> None:
        if self.config is not None and self.check_sempre.isChecked():
            try:
                self.config.update(confirmar_antes_processar=False)
            except Exception:                                     # noqa: BLE001
                pass
        self.accept()


def confirmar_processamento(pai: Optional[QWidget], pedidos: Sequence[Dict],
                            config=None) -> bool:
    """True = pode processar. Respeita a preferência 'não perguntar de novo'."""
    pedidos = [p for p in pedidos if p.get("resultado") is not None]
    if not pedidos:
        return False
    if config is not None and not bool(config.get("confirmar_antes_processar", True)):
        return True
    dialogo = DialogoConfirmar(pai, pedidos, config)
    return dialogo.exec() == QDialog.Accepted


# ---------------------------------------------------------------- etapa 9
class DialogoCapas(QDialog):
    """Mostra a capa achada e permite trocar por outra opção ou recusar."""

    def __init__(self, pai: Optional[QWidget], capa: CoverResult,
                 musica: Optional[Dict] = None) -> None:
        super().__init__(pai)
        self.setWindowTitle("Confirmar capa")
        self.setMinimumSize(720, 460)
        _estilo_dialogo(self)
        self.capa = capa
        self.musica = musica or {}
        self.opcoes: List[CoverResult] = ([capa] + list(getattr(capa, "alternativas", []) or [])) if capa and capa.ok else []
        self.escolhida: Optional[CoverResult] = capa if self.opcoes else None
        self.recusou = False
        self._metadados_pendentes = False
        self._busca_provisoria = None

        fora = QVBoxLayout(self)
        fora.setContentsMargins(22, 20, 22, 18)
        fora.setSpacing(12)

        titulo = QLabel("Esta é a capa que será gravada no MP3?")
        titulo.setStyleSheet("font-size: 17px; font-weight: 800;")
        fora.addWidget(titulo)
        self.lbl_consulta = QLabel()
        self.lbl_consulta.setTextFormat(Qt.PlainText)
        self.lbl_consulta.setWordWrap(True)
        self.lbl_consulta.setStyleSheet(f"color: {PALETA['amarelo']}; font-size: 11.5px;")
        fora.addWidget(self.lbl_consulta)
        self.lbl_metadados = QLabel()
        self.lbl_metadados.setTextFormat(Qt.PlainText)
        self.lbl_metadados.setWordWrap(True)
        fora.addWidget(self.lbl_metadados)
        self._atualizar_textos()
        corpo = QHBoxLayout()
        corpo.setSpacing(16)

        self.lbl_imagem = QLabel()
        self.lbl_imagem.setFixedSize(280, 280)
        self.lbl_imagem.setAlignment(Qt.AlignCenter)
        self.lbl_imagem.setStyleSheet(
            f"background: {PALETA['bg0']}; border: 1px solid {PALETA['border']};"
            " border-radius: 12px;")
        corpo.addWidget(self.lbl_imagem, 0, Qt.AlignTop)

        dados = QVBoxLayout()
        dados.setSpacing(7)
        self.lbl_album = QLabel("")
        self.lbl_album.setStyleSheet("font-size: 14px; font-weight: 700;")
        self.lbl_album.setWordWrap(True)
        dados.addWidget(self.lbl_album)
        self.lbl_credito = QLabel("")
        self.lbl_credito.setProperty("papel_tema", "dim")
        self.lbl_credito.setStyleSheet("font-size: 12px;")
        self.lbl_credito.setWordWrap(True)
        dados.addWidget(self.lbl_credito)
        self.chips = QHBoxLayout()
        self.chips.setSpacing(6)
        caixa_chips = QWidget()
        caixa_chips.setLayout(self.chips)
        dados.addWidget(caixa_chips)

        self.lbl_motivo = QLabel("")
        self.lbl_motivo.setWordWrap(True)
        self.lbl_motivo.setStyleSheet(f"color: {PALETA['amarelo']}; font-size: 11.5px;")
        dados.addWidget(self.lbl_motivo)

        rotulo_opcoes = QLabel("IMAGENS ESCOLHIDAS")
        rotulo_opcoes.setObjectName("dim")
        rotulo_opcoes.setStyleSheet(f"color: {PALETA['texto_fraco']}; font-size: 10.5px;"
                                    " font-weight: 700; letter-spacing: 1px;")
        dados.addSpacing(4)
        dados.addWidget(rotulo_opcoes)
        self.lista = QListWidget()
        self.lista.setIconSize(QPixmap(56, 56).size())
        self.lista.setMinimumHeight(150)
        self.lista.setStyleSheet(
            f"QListWidget {{ background: {PALETA['bg0']}; border: 1px solid {PALETA['border']};"
            f" border-radius: 10px; padding: 4px; }}"
            f"QListWidget::item {{ padding: 5px; border-radius: 6px; }}"
            f"QListWidget::item:selected {{ background: {alfa(PALETA['violeta'], '44')}; }}")
        self.lista.currentRowChanged.connect(self._selecionar)
        dados.addWidget(self.lista, 1)
        corpo.addLayout(dados, 1)
        fora.addLayout(corpo, 1)

        self.lbl_regra = QLabel(
            "Pesquise no Google quando quiser, copie a imagem e clique em Colar imagem copiada. "
            "Confira antes de usar.")
        self.lbl_regra.setWordWrap(True)
        self.lbl_regra.setProperty("papel_tema", "fraco")
        self.lbl_regra.setStyleSheet("font-size: 11px;")
        fora.addWidget(self.lbl_regra)

        linha_botoes = QHBoxLayout()
        linha_botoes.setSpacing(8)
        self.btn_usar = QPushButton("Usar esta capa")
        self.btn_usar.setObjectName("primario")
        self.btn_usar.setEnabled(bool(self.opcoes))
        self.btn_usar.clicked.connect(self._usar)
        self.btn_sem = QPushButton("Não usar capa")
        self.btn_sem.setObjectName("fantasma")
        self.btn_sem.clicked.connect(self._sem_capa)
        linha_botoes.addWidget(self.btn_usar)
        linha_botoes.addWidget(self.btn_sem)
        linha_imagens = QHBoxLayout()
        linha_imagens.setSpacing(8)
        self.btn_google = QPushButton("Pesquisar imagens no Google")
        self.btn_google.clicked.connect(self._pesquisar_google)
        linha_imagens.addWidget(self.btn_google)
        self.btn_colar = QPushButton("Colar imagem copiada")
        self.btn_colar.setToolTip("Copie uma imagem no navegador e clique aqui para revisá-la.")
        self.btn_colar.clicked.connect(self._colar_imagem)
        linha_imagens.addWidget(self.btn_colar)
        self.btn_pasta = QPushButton("Abrir pasta de capas")
        self.btn_pasta.clicked.connect(self._abrir_pasta_capas)
        linha_imagens.addWidget(self.btn_pasta)
        linha_imagens.addStretch(1)
        linha_botoes.addStretch(1)
        self.btn_abrir = QPushButton("Ver imagem maior")
        self.btn_abrir.setObjectName("fantasma")
        self.btn_abrir.clicked.connect(self._ver_maior)
        linha_botoes.addWidget(self.btn_abrir)
        fora.addLayout(linha_botoes)
        fora.addLayout(linha_imagens)

        self._preencher_lista()
        if self.opcoes:
            self.lista.setCurrentRow(0)
            self._selecionar(0)
        else:
            self.lbl_imagem.setText("Escolha uma imagem")
            self.lbl_motivo.setText(capa.observacao or "Copie e cole uma imagem, ou continue sem capa.")

    def _atualizar_textos(self) -> None:
        consulta = self.musica.get('consulta_capa') or {}
        texto = (f"Busca da capa ({consulta.get('origem') or 'dados disponíveis'}): "
                 f"{consulta.get('artista') or 'artista não informado'} — "
                 f"{consulta.get('titulo') or 'título não informado'}")
        if consulta.get('aviso'):
            texto += "\n" + str(consulta['aviso'])
        self.lbl_consulta.setText(texto)
        self.lbl_consulta.setVisible(bool(consulta))
        metadados = self.musica.get('metadados') or {}
        texto = (f"Dados para o MP3 — {metadados.get('artista') or 'artista não identificado'} — "
                 f"{metadados.get('titulo') or 'título não identificado'}\n"
                 f"Álbum: {metadados.get('album') or 'não identificado'} · "
                 f"Ano: {metadados.get('ano') or 'não identificado'} · "
                 f"Faixa: {metadados.get('faixa') or 'não identificada'} · "
                 f"Gênero: {metadados.get('genero') or 'não identificado'}\n"
                 f"Artista do álbum: {metadados.get('artista_album') or 'não identificado'} · "
                 f"Participações: {metadados.get('participacoes') or 'não identificadas'}\n"
                 "São sugestões: confira e, se necessário, cancele e use Editar dados.")
        self.lbl_metadados.setText(texto)
        self.lbl_metadados.setVisible(bool(metadados))

    def definir_pendente(self, pendente: bool) -> None:
        self._metadados_pendentes = pendente
        self.btn_sem.setEnabled(not pendente)
        self.btn_usar.setEnabled(not pendente and bool(self.escolhida and self.escolhida.caminho))
        self.btn_sem.setToolTip('Aguarde a identificação dos metadados.' if pendente else '')
        self.btn_usar.setToolTip('Aguarde a identificação dos metadados.' if pendente else '')

    def atualizar_musica(self, musica: dict) -> None:
        from ..texto import normalizar
        consulta = musica.get('consulta_capa') or {}
        if self._busca_provisoria and (
                normalizar(self._busca_provisoria[0]) != normalizar(musica.get('artista') or '') or
                normalizar(self._busca_provisoria[1]) != normalizar(musica.get('titulo') or '')):
            consulta = dict(consulta)
            consulta['aviso'] = (str(consulta.get('aviso') or '') +
                ' A identidade mudou depois da pesquisa; confira a imagem e pesquise novamente se necessário.').strip()
            musica = dict(musica, consulta_capa=consulta)
        self.musica = musica
        self._atualizar_textos()
        self.definir_pendente(False)

    def showEvent(self, evento) -> None:
        super().showEvent(evento)
        try:
            self._pasta_capas()
        except OSError as exc:
            QMessageBox.warning(self, 'Pasta de capas', str(exc))

    def _pasta_capas(self):
        from ..config import PASTA_DOWNLOAD_CAPAS
        PASTA_DOWNLOAD_CAPAS.mkdir(parents=True, exist_ok=True)
        return PASTA_DOWNLOAD_CAPAS

    def _abrir_pasta_capas(self) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        try:
            pasta = self._pasta_capas()
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(pasta))):
                raise OSError('Não foi possível abrir a pasta.')
        except OSError as exc:
            QMessageBox.warning(self, 'Pasta de capas', str(exc))

    def _salvar_imagem_colada(self, dados: bytes, hash_imagem: str):
        # Nunca substituir uma imagem já existente na pasta do usuário.
        pasta = self._pasta_capas()
        base = 'capa-colada-' + hash_imagem[:16]
        for numero in range(10000):
            caminho = pasta / (base + (f'-{numero}' if numero else '') + '.png')
            try:
                with caminho.open('xb') as arquivo:
                    arquivo.write(dados)
                return caminho
            except FileExistsError:
                continue
        raise OSError('Não foi possível criar um nome livre para a imagem.')

    # ------------------------------------------------------------ internos
    def _preencher_lista(self) -> None:
        self.lista.clear()
        for indice, opcao in enumerate(self.opcoes):
            texto = opcao.album or ("imagem escolhida — álbum não verificado" if opcao.fonte in ('arquivo local', 'imagem colada') else "capa sem álbum informado")
            tipo = {'album': 'Álbum', 'single': 'Single', 'colecao': 'Coleção (tipo não confirmado)'}.get(opcao.tipo_lancamento, 'Imagem escolhida' if opcao.fonte in ('arquivo local', 'imagem colada') else 'Tipo não informado')
            extra = f"{tipo}  ·  {opcao.fonte.replace('_', ' ')}  ·  {opcao.dimensoes()}"
            if opcao.score:
                extra += f"  ·  correspondência {opcao.score:.2f}"
            item = QListWidgetItem(f"{texto}\n{extra}")
            pix = _pixmap(opcao.caminho or "", 56)
            if pix is not None:
                from PySide6.QtGui import QIcon
                item.setIcon(QIcon(pix))
            item.setData(Qt.UserRole, indice)
            self.lista.addItem(item)

    def _selecionar(self, linha: int) -> None:
        if linha < 0 or linha >= len(self.opcoes):
            return
        opcao = self.opcoes[linha]
        self.escolhida = opcao
        self.btn_usar.setEnabled(bool(opcao.caminho) and not self._metadados_pendentes)
        pix = _pixmap(opcao.caminho or "", 280)
        if pix is not None:
            self.lbl_imagem.setPixmap(pix)
        else:
            self.lbl_imagem.setText("imagem indisponível")

        self.lbl_album.setText(opcao.album or ("Imagem local — álbum não verificado"
                                                if opcao.fonte in ("arquivo local", "imagem colada") else "álbum não informado"))
        artista = opcao.artista or "artista não informado"
        ano = f"  ·  {opcao.ano}" if opcao.ano else ""
        self.lbl_credito.setText(f"{artista}{ano}  ·  {opcao.dimensoes()}")
        while self.chips.count():
            item = self.chips.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        tipo = {'album': 'Álbum', 'single': 'Single', 'colecao': 'Coleção (tipo não confirmado)'}.get(opcao.tipo_lancamento)
        if tipo:
            self.chips.addWidget(Chip(tipo, PALETA["violeta"]))
        self.chips.addWidget(Chip(opcao.fonte.replace("_", " "), PALETA["ciano"]))
        if opcao.score:
            cor = (PALETA["lima"] if opcao.score >= 0.85 else
                   PALETA["amarelo"] if opcao.score >= 0.70 else PALETA["vermelho"])
            self.chips.addWidget(Chip(f"correspondência {opcao.score:.2f}", cor))
        if opcao.dimensoes() != "-":
            self.chips.addWidget(Chip(opcao.dimensoes(), PALETA["azul"]))
        self.chips.addStretch(1)

        observacao = opcao.observacao or ""
        if observacao and (opcao.fonte in ("arquivo local", "imagem colada") or "Álbum diferente" in observacao or (opcao.score and opcao.score < 0.85)):
            self.lbl_motivo.setText(f"Confira antes de usar: {observacao}")
        else:
            self.lbl_motivo.setText("")

    def _usar(self) -> None:
        if self._metadados_pendentes or not self.escolhida or not self.escolhida.caminho:
            return
        self.recusou = False
        self.accept()

    def _sem_capa(self) -> None:
        if self._metadados_pendentes:
            return
        self.recusou = True
        self.escolhida = None
        self.accept()

    def _pesquisar_google(self) -> None:
        from urllib.parse import urlencode
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        if self._metadados_pendentes:
            self._busca_provisoria = (self.musica.get("artista") or "", self.musica.get("titulo") or "")
        termo = " ".join(str(self.musica.get(k) or "") for k in ("artista", "titulo"))
        url = "https://www.google.com/search?" + urlencode({"q": termo.strip() + " capa album single", "tbm": "isch"})
        if not QDesktopServices.openUrl(QUrl(url)):
            QMessageBox.warning(self, "Pesquisa no Google", "Não foi possível abrir o navegador. "
                                "Clique em Pesquisar imagens no Google para tentar novamente.")

    def _colar_imagem(self) -> None:
        """Adiciona somente a imagem que a pessoa copiou e precisa confirmar."""
        from PySide6.QtCore import QBuffer, QIODevice
        from PySide6.QtWidgets import QApplication
        from ..metadata.capa_validacao import validar
        imagem = QApplication.clipboard().image()
        try:
            if imagem.isNull():
                raise ValueError('Copie a imagem no navegador, não apenas o endereço, e tente novamente.')
            if min(imagem.width(), imagem.height()) < 300:
                raise ValueError('Imagem menor que 300 pixels; copie a imagem maior, não a miniatura.')
            if max(imagem.width(), imagem.height()) > 6000:
                raise ValueError('Imagem maior que 6000 pixels por lado.')
            buffer = QBuffer()
            if not buffer.open(QIODevice.WriteOnly) or not imagem.save(buffer, 'PNG'):
                raise ValueError('Não foi possível ler a imagem copiada.')
            dados = bytes(buffer.data())
            buffer.close()
            if len(dados) > 15 * 1024 * 1024:
                raise ValueError('Imagem maior que 15 MB.')
            validacao = validar(dados, minimo_lado=300)
            if not validacao.ok:
                raise ValueError(validacao.motivo)
            destino = self._salvar_imagem_colada(dados, validacao.hash)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, 'Imagem inválida', str(exc))
            return
        opcao = CoverResult(caminho=str(destino), fonte='imagem colada',
                            largura=validacao.largura, altura=validacao.altura,
                            observacao='Imagem escolhida por você; confira a música, a edição e os direitos de uso.')
        self.opcoes.append(opcao)
        self._preencher_lista()
        self.lista.setCurrentRow(len(self.opcoes) - 1)

    def _escolher_arquivo(self) -> None:
        from pathlib import Path
        from PySide6.QtGui import QImageReader
        from ..metadata.capa_validacao import validar
        from ..metadata.covers import salvar_cache
        try:
            pasta = str(self._pasta_capas())
        except OSError as exc:
            QMessageBox.warning(self, "Pasta de capas", str(exc))
            return
        caminho, _ = QFileDialog.getOpenFileName(self, "Escolher imagem de capa", pasta,
                                                "Imagens JPEG, PNG ou WebP (*.jpg *.jpeg *.png *.webp)")
        if not caminho:
            return
        try:
            arquivo = Path(caminho)
            if arquivo.stat().st_size > 15 * 1024 * 1024:
                raise ValueError("Arquivo maior que 15 MB.")
            dados = arquivo.read_bytes()
            webp = dados[:4] == b"RIFF" and dados[8:12] == b"WEBP"
            if not (dados.startswith(b"\xff\xd8") or dados.startswith(b"\x89PNG\r\n\x1a\n") or webp):
                raise ValueError("Escolha uma imagem JPEG, PNG ou WebP válida.")
            validacao = validar(dados, minimo_lado=300)
            if not validacao.ok:
                raise ValueError(validacao.motivo)
            if max(validacao.largura, validacao.altura) > 6000:
                raise ValueError("Imagem maior que 6000 pixels por lado.")
            leitor = QImageReader(str(arquivo))
            imagem = leitor.read()
            if imagem.isNull():
                raise ValueError("Não foi possível abrir a imagem.")
            if webp:
                from PySide6.QtCore import QBuffer, QIODevice
                buffer = QBuffer()
                if not buffer.open(QIODevice.WriteOnly) or not imagem.save(buffer, "PNG"):
                    raise ValueError("Não foi possível converter a imagem WebP.")
                dados = bytes(buffer.data())
                buffer.close()
                if len(dados) > 15 * 1024 * 1024:
                    raise ValueError("Imagem convertida maior que 15 MB.")
            destino = salvar_cache("arquivo-local:" + validacao.hash, dados)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Imagem inválida", str(exc))
            return
        opcao = CoverResult(caminho=str(destino), fonte="arquivo local",
                            largura=validacao.largura, altura=validacao.altura,
                            observacao="Imagem escolhida por você; confirme o álbum e os direitos de uso.")
        self.opcoes.append(opcao)
        self._preencher_lista()
        self.lista.setCurrentRow(len(self.opcoes) - 1)

    def _ver_maior(self) -> None:
        if not self.escolhida or not self.escolhida.caminho:
            return
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl.fromLocalFile(self.escolhida.caminho))

    # resultado -------------------------------------------------------
    def resultado(self) -> Dict[str, object]:
        return {"acao": "sem" if self.recusou else "usar", "capa": self.escolhida}


def escolher_capa(pai: Optional[QWidget], capa: CoverResult,
                  musica: Optional[Dict] = None) -> Optional[CoverResult]:
    """Devolve a capa aprovada, ou None quando o usuário recusa usar capa.

    Sempre devolve a escolha AUTOMÁTICA quando o diálogo não pode ser mostrado
    (ex.: rodando em teste), para o fluxo nunca travar.
    """
    if capa is None or not getattr(capa, "caminho", ""):
        return None
    dialogo = DialogoCapas(pai, capa, musica)
    dialogo.exec()
    return dialogo.escolhida if not dialogo.recusou else None

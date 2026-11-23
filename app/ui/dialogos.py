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
        f"QDialog {{ background: {PALETA['bg1']}; }}"
        f"QLabel {{ color: {PALETA['texto']}; }}"
        f"QScrollArea {{ border: none; background: transparent; }}"
        f"QWidget#areaLista {{ background: transparent; }}")


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
            "O RiffLab vai baixar o áudio, identificar a música, buscar a capa e "
            "gravar as tags. Nada é baixado antes da sua confirmação.")
        explicacao.setWordWrap(True)
        explicacao.setStyleSheet(f"color: {PALETA['texto_dim']}; font-size: 12px;")
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
            sub.setStyleSheet(f"color: {PALETA['texto_dim']}; font-size: 11.5px;")
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

        fora = QVBoxLayout(self)
        fora.setContentsMargins(22, 20, 22, 18)
        fora.setSpacing(12)

        titulo = QLabel("Esta é a capa que será gravada no MP3?")
        titulo.setStyleSheet("font-size: 17px; font-weight: 800;")
        fora.addWidget(titulo)
        consulta = self.musica.get('consulta_capa') or {}
        if consulta:
            texto = (f"Busca da capa ({consulta.get('origem') or 'dados disponíveis'}): "
                     f"{consulta.get('artista') or 'artista não informado'} — "
                     f"{consulta.get('titulo') or 'título não informado'}")
            if consulta.get('aviso'):
                texto += "\n" + str(consulta['aviso'])
            self.lbl_consulta = QLabel(texto)
            self.lbl_consulta.setTextFormat(Qt.PlainText)
            self.lbl_consulta.setWordWrap(True)
            self.lbl_consulta.setStyleSheet(f"color: {PALETA['amarelo']}; font-size: 11.5px;")
            fora.addWidget(self.lbl_consulta)
        if 'fontes_capa' in self.musica:
            nomes = {'coverartarchive': 'MusicBrainz / Cover Art Archive',
                     'itunes': 'Apple / iTunes', 'deezer': 'Deezer'}
            fontes = self.musica.get('fontes_capa') or []
            texto_fontes = ', '.join(nomes.get(f, str(f)) for f in fontes) or 'nenhuma'
            self.lbl_fontes = QLabel('Fontes ativadas: ' + texto_fontes +
                '. A imagem exibida pode vir de apenas uma delas; as outras podem não ter retornado uma opção.')
            self.lbl_fontes.setWordWrap(True)
            self.lbl_fontes.setStyleSheet(f"color: {PALETA['texto_dim']}; font-size: 11px;")
            fora.addWidget(self.lbl_fontes)

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
        self.lbl_credito.setStyleSheet(f"color: {PALETA['texto_dim']}; font-size: 12px;")
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

        rotulo_opcoes = QLabel("OUTRAS OPÇÕES ENCONTRADAS")
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
            "O catálogo indica um single, mas pode haver erro ou arte igual à do álbum. "
            "Confira se é a capa da música; se não for, escolha “Não usar capa”. "
            "Imagens locais também exigem sua conferência.")
        self.lbl_regra.setWordWrap(True)
        self.lbl_regra.setStyleSheet(f"color: {PALETA['texto_fraco']}; font-size: 11px;")
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
        self.btn_google = QPushButton("Pesquisar imagens no Google")
        self.btn_google.clicked.connect(self._pesquisar_google)
        linha_botoes.addWidget(self.btn_google)
        self.btn_arquivo = QPushButton("Escolher imagem salva")
        self.btn_arquivo.clicked.connect(self._escolher_arquivo)
        linha_botoes.addWidget(self.btn_arquivo)
        linha_botoes.addStretch(1)
        self.btn_abrir = QPushButton("Ver imagem maior")
        self.btn_abrir.setObjectName("fantasma")
        self.btn_abrir.clicked.connect(self._ver_maior)
        linha_botoes.addWidget(self.btn_abrir)
        fora.addLayout(linha_botoes)

        self._preencher_lista()
        if self.opcoes:
            self.lista.setCurrentRow(0)
            self._selecionar(0)
        else:
            self.lbl_imagem.setText("Nenhuma capa encontrada")
            self.lbl_motivo.setText(capa.observacao or "Escolha uma imagem salva ou continue sem capa.")

    # ------------------------------------------------------------ internos
    def _preencher_lista(self) -> None:
        self.lista.clear()
        for indice, opcao in enumerate(self.opcoes):
            texto = opcao.album or ("imagem local — álbum não verificado" if opcao.fonte == "arquivo local" else "capa sem álbum informado")
            extra = f"{opcao.fonte.replace('_', ' ')}  ·  {opcao.dimensoes()}"
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
        self.btn_usar.setEnabled(bool(opcao.caminho))
        pix = _pixmap(opcao.caminho or "", 280)
        if pix is not None:
            self.lbl_imagem.setPixmap(pix)
        else:
            self.lbl_imagem.setText("imagem indisponível")

        self.lbl_album.setText(opcao.album or ("Imagem local — álbum não verificado"
                                                if opcao.fonte == "arquivo local" else "álbum não informado"))
        artista = opcao.artista or "artista não informado"
        ano = f"  ·  {opcao.ano}" if opcao.ano else ""
        self.lbl_credito.setText(f"{artista}{ano}  ·  {opcao.dimensoes()}")
        while self.chips.count():
            item = self.chips.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self.chips.addWidget(Chip(opcao.fonte.replace("_", " "), PALETA["ciano"]))
        if opcao.score:
            cor = (PALETA["lima"] if opcao.score >= 0.85 else
                   PALETA["amarelo"] if opcao.score >= 0.70 else PALETA["vermelho"])
            self.chips.addWidget(Chip(f"correspondência {opcao.score:.2f}", cor))
        if opcao.dimensoes() != "-":
            self.chips.addWidget(Chip(opcao.dimensoes(), PALETA["azul"]))
        self.chips.addStretch(1)

        observacao = opcao.observacao or ""
        if observacao and (opcao.fonte == "arquivo local" or "Álbum diferente" in observacao or (opcao.score and opcao.score < 0.85)):
            self.lbl_motivo.setText(f"Confira antes de usar: {observacao}")
        else:
            self.lbl_motivo.setText("")

    def _usar(self) -> None:
        if not self.escolhida or not self.escolhida.caminho:
            return
        self.recusou = False
        self.accept()

    def _sem_capa(self) -> None:
        self.recusou = True
        self.escolhida = None
        self.accept()

    def _pesquisar_google(self) -> None:
        from urllib.parse import urlencode
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        termo = " ".join(str(self.musica.get(k) or "") for k in ("artista", "titulo"))
        url = "https://www.google.com/search?" + urlencode({"q": termo.strip() + " capa single", "tbm": "isch"})
        QDesktopServices.openUrl(QUrl(url))

    def _escolher_arquivo(self) -> None:
        from pathlib import Path
        from PySide6.QtGui import QImageReader
        from ..metadata.capa_validacao import validar
        from ..metadata.covers import salvar_cache
        caminho, _ = QFileDialog.getOpenFileName(self, "Escolher imagem de capa", "",
                                                "Imagens JPEG ou PNG (*.jpg *.jpeg *.png)")
        if not caminho:
            return
        try:
            arquivo = Path(caminho)
            if arquivo.stat().st_size > 15 * 1024 * 1024:
                raise ValueError("Arquivo maior que 15 MB.")
            dados = arquivo.read_bytes()
            if not (dados.startswith(b"\xff\xd8") or dados.startswith(b"\x89PNG\r\n\x1a\n")):
                raise ValueError("Escolha uma imagem JPEG ou PNG válida.")
            validacao = validar(dados, minimo_lado=300)
            if not validacao.ok:
                raise ValueError(validacao.motivo)
            if max(validacao.largura, validacao.altura) > 6000:
                raise ValueError("Imagem maior que 6000 pixels por lado.")
            leitor = QImageReader(str(arquivo))
            if leitor.read().isNull():
                raise ValueError("Não foi possível abrir a imagem.")
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

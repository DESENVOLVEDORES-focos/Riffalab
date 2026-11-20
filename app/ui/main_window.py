"""Janela principal: barra lateral neon + páginas + fila de processamento."""
from __future__ import annotations

from typing import Dict, Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QButtonGroup, QFrame, QHBoxLayout, QLabel, QMainWindow,
                               QMessageBox, QPushButton, QStackedWidget, QVBoxLayout, QWidget)

from .. import cookies as cookies_mod
from ..config import APP_NOME, APP_SUB, APP_VERSAO, Config
from ..db import Banco
from ..downloader import GerenciadorFila
from ..tools import status_ferramentas
from ..workers import EXECUTOR_GLOBAL
from .pages.downloads_page import DownloadsPage
from .pages.search_page import SearchPage
from .pages.settings_page import SettingsPage
from .theme import PALETA
from .widgets.images import CarregadorImagens
from .widgets.toast import Toast

PAGINAS = [
    ("buscar", "Pesquisar", "1"),
    ("downloads", "Downloads", "2"),
    ("config", "Configurações", "3"),
]


class MainWindow(QMainWindow):
    def __init__(self, config: Config, banco: Banco) -> None:
        super().__init__()
        self.config = config
        self.banco = banco
        self.setWindowTitle(f"{APP_NOME} — {APP_SUB}")
        self.resize(1360, 880)
        self.setMinimumSize(1080, 680)

        central = QWidget()
        central.setObjectName("fundoApp")
        self.setCentralWidget(central)
        fora = QHBoxLayout(central)
        fora.setContentsMargins(0, 0, 0, 0)
        fora.setSpacing(0)

        # ------------------------------------------------------- barra lateral
        lateral = QFrame()
        lateral.setObjectName("barraLateral")
        lateral.setFixedWidth(228)
        col = QVBoxLayout(lateral)
        col.setContentsMargins(0, 22, 0, 16)
        col.setSpacing(0)

        marca = QVBoxLayout()
        marca.setContentsMargins(20, 0, 20, 18)
        marca.setSpacing(1)
        logo = QLabel(APP_NOME.upper())
        logo.setObjectName("logo")
        logo.setStyleSheet(
            f"color: #fff; font-size: 26px; font-weight: 800; letter-spacing: 2px;"
        )
        sub = QLabel(APP_SUB.upper())
        sub.setObjectName("logoSub")
        marca.addWidget(logo)
        marca.addWidget(sub)
        col.addLayout(marca)

        self.grupo = QButtonGroup(self)
        self.grupo.setExclusive(True)
        self.botoes: Dict[str, QPushButton] = {}
        for chave, nome, icone in PAGINAS:
            btn = QPushButton(f"     {nome}")
            btn.setObjectName("nav")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _=False, k=chave: self.ir_para(k))
            self.grupo.addButton(btn)
            self.botoes[chave] = btn
            col.addWidget(btn)

        col.addStretch(1)

        self.lbl_rodape = QLabel()
        self.lbl_rodape.setWordWrap(True)
        self.lbl_rodape.setStyleSheet(
            f"color: {PALETA['texto_fraco']}; font-size: 10.5px; padding: 0 20px 14px;")
        col.addWidget(self.lbl_rodape)
        fora.addWidget(lateral)

        # ----------------------------------------------------------- páginas
        self.pilha = QStackedWidget()
        fora.addWidget(self.pilha, 1)

        self.carregador = CarregadorImagens(self)
        self.fila = GerenciadorFila(config, banco, self)

        self.pagina_busca = SearchPage(config, banco, self.carregador)
        self.pagina_downloads = DownloadsPage(config, self.fila)
        self.pagina_config = SettingsPage(config)

        self.paginas = {
            "buscar": self.pagina_busca,
            "downloads": self.pagina_downloads,
            "config": self.pagina_config,
        }
        for pagina in self.paginas.values():
            self.pilha.addWidget(pagina)

        self.toast = Toast(central)

        # --------------------------------------------------------- ligações
        self.pagina_busca.transferir_pedido = self.enfileirar
        self.pagina_busca.abrir_downloads.connect(lambda: self.ir_para('downloads'))
        self.pagina_busca.mensagem.connect(self.toast.mostrar)
        self.pagina_downloads.mensagem.connect(self.toast.mostrar)
        self.pagina_config.mensagem.connect(self.toast.mostrar)
        self.pagina_config.config_alterada.connect(self._config_mudou)
        self.pagina_config.ferramentas_verificadas.connect(self.pagina_busca.atualizar_ferramentas)
        self.fila.mensagem.connect(self._ao_processar)
        self.fila.job_adicionado.connect(lambda _j: self._sincronizar_contador())
        self.fila.job_atualizado.connect(lambda _j: self._sincronizar_contador())
        self.fila.terminou_tudo.connect(self._sincronizar_contador)

        self.statusBar().showMessage("Pronto.")
        self.ir_para("buscar")
        self._atualizar_rodape()
        QTimer.singleShot(200, self._atualizar_rodape_completo)
        QTimer.singleShot(350, self._avisar_pasta_saida_inicial)

    def _avisar_pasta_saida_inicial(self) -> None:
        if self.pagina_config.aviso_pasta_saida.text():
            texto = ("Pasta de saída indisponível. Conecte a unidade ou escolha outra "
                     "em Configurações → Áudio e destino antes de baixar.")
            self.statusBar().showMessage(texto)
            self.toast.mostrar(texto)

    # ------------------------------------------------------------------ navegação
    def ir_para(self, chave: str) -> None:
        pagina = self.paginas.get(chave)
        if not pagina:
            return
        self.pilha.setCurrentWidget(pagina)
        if chave in self.botoes:
            self.botoes[chave].setChecked(True)

    # ------------------------------------------------------------------ ações
    def enfileirar(self, dados: dict) -> bool:
        resultado = dados.get("resultado")
        if resultado is None:
            return False
        ja_existe = any(x.pedido['resultado'].fonte == resultado.fonte and
                        x.pedido['resultado'].uid == resultado.uid
                        for x in self.pagina_downloads.selecoes)
        adicionada = self.pagina_downloads.adicionar_selecao(dados)
        if adicionada and not dados.get("lote"):
            mensagem = f"Adicionada a Downloads: {resultado.artista} — {resultado.titulo}"
            self.statusBar().showMessage(mensagem)
            self.toast.mostrar(mensagem)
        self._sincronizar_contador()
        return adicionada or ja_existe

    def _ao_processar(self, msg: str) -> None:
        self.toast.mostrar(msg)
        self.statusBar().showMessage(msg)

    def _config_mudou(self) -> None:
        self._atualizar_rodape()
        self.pagina_busca._atualizar_aviso()
        self.toast.mostrar("Configurações aplicadas.")

    def _sincronizar_contador(self, *_args) -> None:
        pendentes = self.fila.pendentes
        texto = "Downloads" + (f"  ({pendentes})" if pendentes else "")
        if "downloads" in self.botoes:
            self.botoes["downloads"].setText(f"     {texto.strip()}")

    # ------------------------------------------------------------------ rodapé
    def _ajustar_altura_rodape(self) -> None:
        """QLabel com wordWrap dentro de um layout vertical calcula altura curta
        e corta as linhas do rodapé (visto nas capturas de tela)."""
        largura = self.lbl_rodape.width() or 170
        altura = self.lbl_rodape.heightForWidth(largura)
        if altura > 0:
            self.lbl_rodape.setMinimumHeight(altura + 6)

    def _atualizar_rodape(self) -> None:
        st = cookies_mod.verificar(self.config.caminho_cookies)
        self.lbl_rodape.setText(f"cookies: {st.estado}\nsaída: "
                                f"{self.config.pasta_saida.name or str(self.config.pasta_saida)}\nv{APP_VERSAO}")
        self._ajustar_altura_rodape()

    def _atualizar_rodape_completo(self) -> None:
        def pronto(dados) -> None:
            ff = dados.get("ffmpeg")
            yt = dados.get("yt-dlp")
            partes = [f"ffmpeg {'ok' if ff and ff.ok else 'ausente'}",
                      f"yt-dlp {'ok' if yt and yt.ok else 'ausente'}"]
            st = cookies_mod.verificar(self.config.caminho_cookies)
            self.lbl_rodape.setText(" · ".join(partes) + "\n"
                                    f"cookies: {st.estado}\n"
                                    f"saída: {self.config.pasta_saida.name or str(self.config.pasta_saida)}\n"
                                    f"v{APP_VERSAO}")
            self._ajustar_altura_rodape()
        EXECUTOR_GLOBAL.rodar(status_ferramentas, True, ao_resultado=pronto)

    # ------------------------------------------------------------------ resize
    def resizeEvent(self, evento) -> None:            # noqa: N802
        super().resizeEvent(evento)
        if hasattr(self, "toast") and self.toast.isVisible():
            self.toast._posicionar()

    def closeEvent(self, evento) -> None:             # noqa: N802
        if self.fila.pendentes or self.pagina_downloads._preparando:
            resposta = QMessageBox.warning(
                self, 'Processamento em andamento',
                'Há músicas na fila ou capas sendo pesquisadas. Fechar agora pode interromper '
                'o processamento. Downloads em andamento ou aguardando não serão retomados automaticamente. Deseja fechar mesmo assim?',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if resposta != QMessageBox.Yes:
                evento.ignore()
                return
        # Ignora respostas de pesquisas que acabem depois da janela fechar.
        self.pagina_busca._geracao_busca += 1
        self.pagina_busca._buscando = False
        self.pagina_downloads._a_preparar.clear()
        self.pagina_downloads._preparando = False
        try:
            self.config.salvar()
            self.banco.fechar()
        except Exception:
            pass
        super().closeEvent(evento)

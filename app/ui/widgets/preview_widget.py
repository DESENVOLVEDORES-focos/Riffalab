"""Pré-visualização de um resultado sem baixar o arquivo (proposta §2.2).

Como funciona:

* o vídeo é aberto no **player oficial** da plataforma dentro de um
  `QWebEngineView` (`youtube-nocookie.com/embed/<id>`), com `enablejsapi=1`;
* os botões Tocar/Pausar falam com o player por `postMessage` (API oficial do
  iframe) — nenhum download parcial, nenhum arquivo temporário;
* se o dono do vídeo não permite incorporação, ou se o QtWebEngine não estiver
  instalado, a camada explica o motivo e oferece **abrir a página original** no
  navegador padrão. Nunca finge que está tocando.

O widget é uma sobreposição (overlay) porque a tela de pesquisa precisa
continuar existindo por baixo, com a seleção do usuário preservada.
"""
from __future__ import annotations

from html import escape
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton,
                               QSizePolicy, QVBoxLayout, QWidget)

from ...models import TrackResult, hhmmss
from ...pesquisa import preview as previa
from ..theme import PALETA, alfa

_TENTAR_WEBENGINE = True


def webengine_disponivel() -> bool:
    """O QtWebEngine está instalado nesta máquina?"""
    global _TENTAR_WEBENGINE
    if not _TENTAR_WEBENGINE:
        return False
    try:
        from PySide6 import QtWebEngineWidgets  # noqa: F401
        return True
    except Exception:                                             # noqa: BLE001
        _TENTAR_WEBENGINE = False
        return False


def _html_player(url: str, titulo: str) -> str:
    """Página mínima com o iframe oficial (o player do YouTube)."""
    return f"""<!doctype html><html><head><meta charset="utf-8">
<style>
  html,body{{margin:0;padding:0;background:#07010F;height:100%;overflow:hidden}}
  .caixa{{position:absolute;inset:0;display:flex;align-items:center;justify-content:center}}
  iframe{{width:100%;height:100%;border:0;background:#000}}
</style></head><body>
<div class="caixa">
  <iframe id="player" src="{escape(url)}"
          title="{escape(titulo)}"
          allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; fullscreen"
          allowfullscreen referrerpolicy="strict-origin-when-cross-origin"></iframe>
</div>
<script>
function comando(func) {{
  var f = document.getElementById('player');
  if (!f || !f.contentWindow) return;
  f.contentWindow.postMessage(JSON.stringify({{event:'command', func:func, args:[]}}), '*');
}}
</script></body></html>"""


class PreviewOverlay(QFrame):
    """Camada de pré-visualização sobreposta à página de pesquisa."""

    fechado = Signal()

    def __init__(self, pai: Optional[QWidget] = None) -> None:
        super().__init__(pai)
        self.setObjectName("previewOverlay")
        self.setStyleSheet(
            f"#previewOverlay {{ background: {PALETA['bg0']};"
            f" border: 1px solid {PALETA['border_hi']}; border-radius: 16px; }}")
        self.setVisible(False)
        self.resultado: Optional[TrackResult] = None
        self._view = None

        fora = QVBoxLayout(self)
        fora.setContentsMargins(18, 16, 18, 16)
        fora.setSpacing(10)

        # ------------------------------------------------------- cabeçalho
        topo = QHBoxLayout()
        topo.setSpacing(10)
        textos = QVBoxLayout()
        textos.setSpacing(2)
        self.lbl_titulo = QLabel("")
        self.lbl_titulo.setStyleSheet(
            f"font-size: 16px; font-weight: 800; color: {PALETA['texto']};")
        self.lbl_titulo.setWordWrap(True)
        self.lbl_detalhe = QLabel("")
        self.lbl_detalhe.setProperty("papel_tema", "dim")
        self.lbl_detalhe.setStyleSheet("font-size: 12px;")
        self.lbl_detalhe.setWordWrap(True)
        textos.addWidget(self.lbl_titulo)
        textos.addWidget(self.lbl_detalhe)
        topo.addLayout(textos, 1)

        self.btn_fechar = QPushButton("Fechar ✕")
        self.btn_fechar.setObjectName("fantasma")
        self.btn_fechar.clicked.connect(self.fechar)
        topo.addWidget(self.btn_fechar, 0, Qt.AlignTop)
        fora.addLayout(topo)

        # --------------------------------------------------------- player
        self.caixa = QFrame()
        self.caixa.setStyleSheet(
            f"background: #000; border: 1px solid {PALETA['border']}; border-radius: 12px;")
        self.caixa.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        dentro = QVBoxLayout(self.caixa)
        dentro.setContentsMargins(0, 0, 0, 0)
        self._layout_player = dentro
        self.lbl_estado = QLabel("")
        self.lbl_estado.setAlignment(Qt.AlignCenter)
        self.lbl_estado.setWordWrap(True)
        self.lbl_estado.setProperty("papel_tema", "dim")
        self.lbl_estado.setStyleSheet("font-size: 13px;")
        dentro.addWidget(self.lbl_estado)
        fora.addWidget(self.caixa, 1)

        # --------------------------------------------------------- rodapé
        rodape = QHBoxLayout()
        rodape.setSpacing(8)
        self.btn_tocar = QPushButton("▶  Tocar")
        self.btn_tocar.setObjectName("primario")
        self.btn_tocar.clicked.connect(self._tocar)
        self.btn_pausar = QPushButton("⏸  Pausar")
        self.btn_pausar.setObjectName("fantasma")
        self.btn_pausar.clicked.connect(self._pausar)
        self.btn_original = QPushButton("Abrir página original")
        self.btn_original.setObjectName("fantasma")
        self.btn_original.clicked.connect(self._abrir_original)
        for botao in (self.btn_tocar, self.btn_pausar, self.btn_original):
            rodape.addWidget(botao)
        rodape.addStretch(1)
        self.lbl_aviso = QLabel("")
        self.lbl_aviso.setStyleSheet(f"color: {PALETA['amarelo']}; font-size: 11.5px;")
        self.lbl_aviso.setWordWrap(True)
        rodape.addWidget(self.lbl_aviso, 2)
        fora.addLayout(rodape)

    # ------------------------------------------------------------------ API
    def mostrar(self, resultado: TrackResult) -> None:
        """Abre a prévia de um resultado (chamado pela tela de pesquisa)."""
        self.resultado = resultado
        self.lbl_titulo.setText(resultado.titulo or "(sem título)")
        partes = [p for p in (resultado.artista or "", resultado.canal or "") if p]
        detalhe = "  ·  ".join(dict.fromkeys(partes))
        if resultado.duracao_s:
            detalhe += f"  ·  {hhmmss(resultado.duracao_s)}"
        resumo = resultado.resumo_publico()
        if resumo:
            detalhe += f"  ·  {resumo}"
        self.lbl_detalhe.setText(detalhe)
        self.setGeometry(self.parentWidget().rect() if self.parentWidget() else self.rect())
        self.setVisible(True)
        self.raise_()
        self._carregar(resultado)

    def fechar(self) -> None:
        self._destruir_view()
        self.setVisible(False)
        self.resultado = None
        self.fechado.emit()

    def resizeEvent(self, evento) -> None:                       # noqa: N802
        super().resizeEvent(evento)

    # -------------------------------------------------------------- interno
    def _destruir_view(self) -> None:
        if self._view is not None:
            try:
                self._layout_player.removeWidget(self._view)
                # libera a página antes da view (evita o aviso de perfil do
                # QtWebEngine ao fechar a prévia)
                try:
                    pagina = self._view.page()
                    if pagina is not None:
                        pagina.deleteLater()
                except RuntimeError:
                    pass
                self._view.setParent(None)
                self._view.deleteLater()
            except RuntimeError:
                pass
            self._view = None
        self.btn_tocar.setEnabled(False)
        self.btn_pausar.setEnabled(False)

    def _carregar(self, resultado: TrackResult) -> None:
        self._destruir_view()
        self.lbl_estado.setVisible(True)
        pode, motivo = previa.pode_incorporar(resultado)
        if not pode:
            self.lbl_estado.setText(
                f"<b>Prévia incorporada indisponível</b><br>{escape(motivo)}<br><br>"
                "<span style='font-size:11px'>Use “Abrir página original” para "
                "assistir na plataforma.</span>")
            self.lbl_aviso.setText(
                "A prévia nunca baixa o arquivo: ela só abre o player oficial.")
            self.btn_original.setEnabled(bool(previa.url_externa(resultado)))
            return

        if not webengine_disponivel():
            self.lbl_estado.setText(
                "<b>Player embutido não disponível</b><br>"
                "O componente de navegação do Qt (QtWebEngine) não está instalado.<br><br>"
                "<span style='font-size:11px'>Instale com: pip install PySide6-Addons — "
                "ou use “Abrir página original”.</span>")
            self.btn_original.setEnabled(True)
            self.lbl_aviso.setText(
                "Sem o player embutido nada é baixado: a prévia apenas abre a página "
                "original no navegador.")
            return

        from PySide6.QtWebEngineWidgets import QWebEngineView

        self._view = QWebEngineView(self.caixa)
        # entra no layout da moldura (antes o player cobria o cabeçalho quando o
        # layout ainda não tinha sido calculado)
        self._layout_player.addWidget(self._view)
        self._view.setHtml(_html_player(previa.url_incorporada(resultado),
                                        resultado.titulo or "prévia"),
                           QUrl("https://www.youtube-nocookie.com/"))
        self._view.show()
        self.lbl_estado.setVisible(False)
        self.btn_tocar.setEnabled(True)
        self.btn_pausar.setEnabled(True)
        self.btn_original.setEnabled(True)
        self.lbl_aviso.setText("Prévia no player oficial — nada é baixado para o computador.")

    def _js(self, codigo: str) -> None:
        if self._view is None:
            return
        try:
            self._view.page().runJavaScript(codigo)
        except Exception:                                         # noqa: BLE001
            pass

    def _tocar(self) -> None:
        self._js("comando('playVideo');")

    def _pausar(self) -> None:
        self._js("comando('pauseVideo');")

    def _abrir_original(self) -> None:
        if not self.resultado:
            return
        url = previa.url_externa(self.resultado)
        if url:
            QDesktopServices.openUrl(QUrl(url))

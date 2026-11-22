"""Cartão de resultado: capa, dados, selos de qualidade e ação de processar."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFrame, QHBoxLayout, QLabel,
                               QMessageBox, QPushButton, QSizePolicy, QVBoxLayout, QWidget)

from ...formatos_detalhes import campos
from ...models import AudioFormat, TrackResult, hhmmss
from ...pesquisa import preview as previa
from ...quality import cor_rotulo, pontuar, rotulo
from ..theme import PALETA, pixmap_placeholder, alfa
from .images import CarregadorImagens, cortar_quadrado

LADO_CAPA = 72


class Chip(QLabel):
    """Selozinho colorido (codec, bitrate, qualidade...)."""

    def __init__(self, texto: str, cor: str, fundo: Optional[str] = None, pai=None) -> None:
        super().__init__(texto, pai)
        fundo = fundo or "rgba(255,255,255,0.05)"
        self.setStyleSheet(
            f"color: {cor}; background: {fundo}; border: 1px solid {alfa(cor, '55')};"
            f"border-radius: 8px; padding: 2px 8px; font-size: 11px; font-weight: 700;"
        )


class ResultCard(QFrame):
    processar = Signal(dict)          # {"resultado", "formato"}
    selecionado = Signal(bool)
    prever = Signal(dict)             # {"resultado"} — abre a pré-visualização

    def __init__(self, resultado: TrackResult, carregador: CarregadorImagens,
                 ao_detalhar=None, pai: Optional[QWidget] = None) -> None:
        super().__init__(pai)
        self.resultado = resultado
        self.carregador = carregador
        self.ao_detalhar = ao_detalhar
        self.setObjectName("cartaoResultado")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        fora = QHBoxLayout(self)
        fora.setContentsMargins(9, 8, 10, 8)
        fora.setSpacing(10)

        # ---------------------------------------------------------- capa
        self.capa = QLabel()
        self.capa.setFixedSize(LADO_CAPA, LADO_CAPA)
        self.capa.setPixmap(pixmap_placeholder(LADO_CAPA))
        self.capa.setScaledContents(True)
        self.capa.setStyleSheet(f"border-radius: 11px; border: 1px solid {PALETA['border']};")
        fora.addWidget(self.capa, 0, Qt.AlignTop)
        self.capa.setToolTip(
            "Miniatura do vídeo na plataforma de origem — não é a capa do MP3.\n"
            "A capa final (iTunes / Cover Art Archive) é aplicada ao arquivo e "
            "aparece em Biblioteca.")
        if resultado.thumb_url:
            self.carregador.pedir(resultado.thumb_url, self._capa_pronta)

        # ------------------------------------------------------- textos
        meio = QVBoxLayout()
        meio.setSpacing(3)
        meio.setContentsMargins(0, 0, 0, 0)

        titulo = QLabel(resultado.titulo or "(sem título)")
        titulo.setStyleSheet("font-size: 15px; font-weight: 700;")
        # permite encolher: sem isso o cartão força a largura da tela e o
        # combo de formatos acaba cortado
        titulo.setWordWrap(True)
        titulo.setMinimumWidth(120)
        titulo.setTextInteractionFlags(Qt.TextSelectableByMouse)
        meio.addWidget(titulo)

        sub = QLabel(self._linha_secundaria())
        sub.setObjectName("dim")
        sub.setStyleSheet(f"color: {PALETA['texto_dim']}; font-size: 12px;")
        sub.setWordWrap(True)
        sub.setMinimumWidth(120)
        meio.addWidget(sub)

        # os selos e a barra são reconstruídos quando a qualidade é verificada
        self._caixa_selos = QWidget()
        self._selos = QHBoxLayout(self._caixa_selos)
        self._selos.setContentsMargins(0, 0, 0, 0)
        self._selos.setSpacing(6)
        meio.addWidget(self._caixa_selos)

        self.lbl_erro_qualidade = QLabel("")
        self.lbl_erro_qualidade.setWordWrap(True)
        self.lbl_erro_qualidade.setStyleSheet(f"color: {PALETA['amarelo']}; font-size: 11px;")
        self.lbl_erro_qualidade.setVisible(False)
        meio.addWidget(self.lbl_erro_qualidade)

        self.lbl_metodos_qualidade = QLabel("")
        self.lbl_metodos_qualidade.setWordWrap(False)
        self.lbl_metodos_qualidade.setStyleSheet(f"color: {PALETA['texto_dim']}; font-size: 11px;")
        self.lbl_metodos_qualidade.linkActivated.connect(self._mostrar_metodos)
        self._detalhes_metodos = ""
        self.lbl_metodos_qualidade.setVisible(False)
        meio.addWidget(self.lbl_metodos_qualidade)

        self.lbl_origem_formato = QLabel("")
        self.lbl_origem_formato.setWordWrap(False)
        self.lbl_origem_formato.setStyleSheet(f"color: {PALETA['texto_dim']}; font-size: 11px;")
        self.lbl_origem_formato.setVisible(False)
        meio.addWidget(self.lbl_origem_formato)

        self.lbl_baixado = QLabel("")
        self.lbl_baixado.setWordWrap(True)
        self.lbl_baixado.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.lbl_baixado.setStyleSheet(f"color: {PALETA['lima']}; font-size: 11px;")
        meio.addWidget(self.lbl_baixado)

        self.lbl_video = QLabel("")
        self.lbl_video.setStyleSheet(f"color: {PALETA['texto_fraco']}; font-size: 11px;")
        self.lbl_video.setWordWrap(True)
        self.lbl_video.setMinimumWidth(120)
        self.lbl_video.setVisible(False)
        meio.addWidget(self.lbl_video)

        self._barra = QFrame()
        self._barra.setFixedHeight(4)
        self._barra.setStyleSheet("background: #1A0526; border-radius: 2px;")
        self._dentro_barra = QHBoxLayout(self._barra)
        self._dentro_barra.setContentsMargins(0, 0, 0, 0)
        meio.addWidget(self._barra)
        fora.addLayout(meio, 1)

        # Ações compactas mantêm o seletor e a comparação legíveis sem
        # transformar cada resultado num cartão excessivamente alto.
        direita = QVBoxLayout()
        direita.setSpacing(4)
        direita.setAlignment(Qt.AlignTop)
        self.combo = QComboBox()
        self.combo.setObjectName("seletorFormatos")
        self.combo.setMinimumWidth(235)
        self.combo.setMaximumWidth(280)
        self.combo.currentIndexChanged.connect(self._atualizar_origem_formato)
        self.combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.combo.setMinimumContentsLength(12)
        self.combo.view().setMinimumWidth(410)
        direita.addWidget(self.combo)
        linha_formatos = QHBoxLayout()
        linha_formatos.setSpacing(4)
        self.btn_formatos = QPushButton("Comparar formatos")
        self.btn_formatos.setObjectName("fantasma")
        self.btn_formatos.setStyleSheet("padding: 5px 7px;")
        self.btn_formatos.setToolTip("Ver os detalhes técnicos de todos os formatos deste vídeo")
        self.btn_formatos.clicked.connect(self._comparar_formatos)
        linha_formatos.addWidget(self.btn_formatos, 1)
        self.btn_verificar = QPushButton("Verificar")
        self.btn_verificar.setObjectName("fantasma")
        self.btn_verificar.setStyleSheet("padding: 5px 7px;")
        self.btn_verificar.clicked.connect(self._verificar)
        self.btn_verificar.setVisible(not bool(resultado.formatos))
        linha_formatos.addWidget(self.btn_verificar)
        direita.addLayout(linha_formatos)

        linha = QHBoxLayout()
        linha.setSpacing(5)
        self.btn_processar = QPushButton("Adicionar")
        self.btn_processar.setObjectName("primario")
        self.btn_processar.setStyleSheet("padding: 6px 9px;")
        self.btn_processar.clicked.connect(self._emitir_processar)
        linha.addWidget(self.btn_processar)
        self.check = QCheckBox("incluir")
        self.check.setToolTip("Marcar esta música para adicionar à lista de Downloads")
        self.check.toggled.connect(self.selecionado.emit)
        linha.addWidget(self.check)
        self.btn_previa = QPushButton("▶ Prévia")
        self.btn_previa.setObjectName("fantasma")
        self.btn_previa.setStyleSheet("padding: 5px 7px;")
        self.btn_previa.clicked.connect(lambda: self.prever.emit({"resultado": self.resultado}))
        if resultado.fonte == "ytdlp":
            pode, motivo = previa.pode_incorporar(resultado)
            self.btn_previa.setToolTip(motivo or "Reproduzir no player oficial, sem baixar o arquivo")
            if not pode:
                self.btn_previa.setText("Prévia ↗")
        else:
            self.btn_previa.setToolTip("A prévia embutida existe para vídeos")
        linha.addWidget(self.btn_previa)
        linha.addStretch(1)
        direita.addLayout(linha)
        fora.addLayout(direita, 0)

        self._preencher_baixado()
        self._preencher_video()
        self._preencher_selos()
        self._preencher_barra()
        self._preencher_formatos()          # já com btn_processar criado

    # ------------------------------------------------------------------ dados
    def _preencher_baixado(self) -> None:
        dados = self.resultado.extra.get("arquivo_baixado") or {}
        caminho = dados.get("caminho", "")
        if not caminho:
            self.lbl_baixado.setText("")
            self.lbl_baixado.setVisible(False)
            return
        if dados.get("tipo") == "id":
            aviso = "Já baixado (mesma origem)"
            dica = "O identificador da fonte coincide com o MP3 encontrado."
        else:
            aviso = "Possivelmente já baixada — confira a versão"
            dica = "Título e artista coincidem, mas podem existir gravações diferentes."
        self.lbl_baixado.setText(f"{aviso} · {caminho}")
        self.lbl_baixado.setToolTip(dica)
        self.lbl_baixado.setVisible(True)

    def _linha_secundaria(self) -> str:
        r = self.resultado
        pedacos = [r.artista or "—"]
        if r.canal and r.canal.strip().lower() != (r.artista or "").strip().lower():
            pedacos.append(f"canal: {r.canal}")
        if r.album:
            pedacos.append(r.album)
        if r.duracao_s:
            pedacos.append(hhmmss(r.duracao_s))
        if r.ano:
            pedacos.append(str(r.ano))
        resumo = r.resumo_publico()          # visualizações + data de publicação
        if resumo:
            pedacos.append(resumo)
        return "  ·  ".join(pedacos)

    def _preencher_video(self) -> None:
        """§11: mostra o que o yt-dlp encontrou, sem termos técnicos demais.

        Também é aqui que aparecem a fonte e a licença (antes eram chips e,
        somados, empurravam o cartão para fora da tela).
        """
        pedacos = []
        resumo = self.resultado.resumo_video()
        if resumo:
            pedacos.append(f"Melhor vídeo: {resumo}")
        fonte = self.resultado.fonte.replace("_", " ")
        extras = [fonte] if fonte else []
        if self.resultado.licenca:
            extras.append(self.resultado.licenca[:40])
        if extras:
            pedacos.append("  ·  ".join(extras))
        if resumo:
            pedacos.append("o MP3 é gerado da faixa de áudio escolhida")
        texto = "   ·   ".join(pedacos)
        self.lbl_video.setText(texto)
        self.lbl_video.setVisible(bool(texto))

    def _preencher_selos(self) -> None:
        while self._selos.count():
            item = self._selos.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        melhor = self.resultado.melhor
        if melhor:
            rot = rotulo(melhor)
            self._selos.addWidget(Chip(melhor.codec.upper() or "?", PALETA["ciano"]))
            if melhor.bitrate_kbps:
                self._selos.addWidget(Chip(f"{melhor.bitrate_kbps} kbps", PALETA["amarelo"]))
            elif melhor.lossless:
                self._selos.addWidget(Chip("lossless", PALETA["ciano"]))
            if melhor.sample_rate:
                self._selos.addWidget(Chip(f"{melhor.sample_rate / 1000:g} kHz", PALETA["azul"]))
            self._selos.addWidget(Chip(rot, cor_rotulo(melhor), f"{alfa(cor_rotulo(melhor), '1A')}"))
            if melhor.estimado:
                self._selos.addWidget(Chip("estimado", PALETA["texto_fraco"]))
        else:
            erro = self.resultado.extra.get("erro_detalhe")
            if erro:
                chip = Chip("qualidade não detectada", PALETA["vermelho"])
                chip.setToolTip(erro)
                self._selos.addWidget(chip)
            else:
                self._selos.addWidget(Chip("verificando qualidade…", PALETA["amarelo"]))
        # ---- sinais de "ao vivo" (proposta §2.3): aviso, nunca silêncio ----
        if self.resultado.ao_vivo:
            confirmado = self.resultado.ao_vivo_certeza == "confirmado"
            chip_ao_vivo = Chip("AO VIVO" if confirmado else "possível ao vivo",
                                PALETA["vermelho"] if confirmado else PALETA["amarelo"],
                                alfa(PALETA["vermelho"] if confirmado else PALETA["amarelo"], "22"))
            chip_ao_vivo.setToolTip(
                (self.resultado.alerta() or "Possível gravação ao vivo") +
                ("\n\nSinais: " + "; ".join(self.resultado.sinais_ao_vivo[:4])
                 if self.resultado.sinais_ao_vivo else ""))
            self._selos.addWidget(chip_ao_vivo)
        if self.resultado.filtrado:
            chip_filtrado = Chip("fora do filtro", PALETA["texto_fraco"])
            chip_filtrado.setToolTip("Este resultado ficou oculto pelo filtro de "
                                     "shows/ao vivo. Você pediu para mostrá-lo.")
            self._selos.addWidget(chip_filtrado)
        self._selos.addStretch(1)

    def _preencher_barra(self) -> None:
        while self._dentro_barra.count():
            item = self._dentro_barra.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        melhor = self.resultado.melhor
        if not melhor:
            self._barra.setVisible(False)
            return
        self._barra.setVisible(True)
        preenchido = QFrame()
        preenchido.setStyleSheet(
            f"background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            f"stop:0 {cor_rotulo(melhor)}, stop:1 {PALETA['violeta']}); border-radius: 2px;")
        preenchido.setFixedHeight(4)
        preenchido.setFixedWidth(int(LADO_CAPA * 4 * max(0.06, pontuar(melhor) / 1000)))
        self._dentro_barra.addWidget(preenchido)
        self._dentro_barra.addStretch(1)

    def _formato_padrao(self) -> AudioFormat:
        """Opção usada enquanto (ou caso) os formatos reais não são detectados."""
        return AudioFormat(codec="?", container="", url=self.resultado.pagina_url or "",
                           estimado=True, format_id="bestaudio",
                           extra={"nota": "melhor áudio"})

    def _preencher_formatos(self) -> None:
        selecionado = self.combo.currentData()
        erro_visivel = self.resultado.extra.get("erro_detalhe") or ""
        titulo_erro = "Consulta incompleta" if self.resultado.formatos else "Qualidade não detectada"
        self.lbl_erro_qualidade.setText(f"{titulo_erro}: {erro_visivel}" if erro_visivel else "")
        self.lbl_erro_qualidade.setVisible(bool(erro_visivel))
        metodos = self.resultado.extra.get("metodos_consulta") or []
        if metodos:
            linhas = []
            for metodo in metodos:
                nome, estado = metodo.get("nome", ""), metodo.get("estado", "")
                detalhe = f"{metodo.get('quantidade', 0)} formato(s)" if estado == "ok" else estado
                aviso = metodo.get("motivo") or metodo.get("aviso")
                if aviso:
                    detalhe += f" ({aviso})"
                if metodo.get("versao"):
                    detalhe += f" · v{metodo['versao']}"
                linhas.append(f"{nome}: {detalhe}")
            self._detalhes_metodos = "\n".join(linhas)
            self.lbl_metodos_qualidade.setToolTip(self._detalhes_metodos)
            concluidos = sum(m.get('estado') not in ('consultando', 'aguardando') for m in metodos)
            total = len(metodos)
            texto = f"{len(self.resultado.formatos)} formato(s) · {concluidos}/{total} métodos"
            self.lbl_metodos_qualidade.setText(
                f"{texto} · <a style='color:{PALETA['ciano']}' href='metodos'>ver detalhes</a>")
            self.lbl_metodos_qualidade.setVisible(True)
        else:
            self.lbl_metodos_qualidade.setText("")
            self.lbl_metodos_qualidade.setVisible(False)
        self.combo.clear()
        ordenados = self.resultado.formatos_ordenados()
        self.btn_formatos.setEnabled(bool(ordenados))
        if not ordenados:
            erro = self.resultado.extra.get("erro_detalhe")
            if erro:
                texto = "melhor áudio disponível (qualidade não detectada)"
                dica = f"{erro}\n\nVocê pode tentar baixar, mas a falha de acesso " \
                       f"também pode impedir o download."
            else:
                texto = "melhor áudio disponível (verificando…)"
                dica = ("O RiffLab está consultando os formatos reais. Você já pode "
                        "processar: sem a lista, o yt-dlp baixa o melhor áudio.")
            self.combo.addItem(texto, self._formato_padrao())
            self.combo.setEnabled(False)
            self.combo.setToolTip(dica)
            self.combo.setStyleSheet(f"color: {PALETA['texto_fraco']};")
            # o botão NUNCA fica travado esperando a detecção
            self.btn_processar.setEnabled(True)
            self.btn_processar.setToolTip(dica)
            return
        self.combo.setEnabled(True)
        self.combo.setToolTip("")
        self.combo.setStyleSheet("")
        self.btn_processar.setEnabled(True)
        self.btn_processar.setToolTip("")
        for i, fmt in enumerate(ordenados):
            texto = fmt.descricao_curta()
            if not fmt.bitrate_kbps:
                texto += " · bitrate não informado"
            if 'áudio não confirmado' in campos(fmt)['Tipo']:
                texto += " · áudio não confirmado"
            if fmt.format_id:
                texto = f"{texto} · id {fmt.format_id}"      # ex.: id 251 (opus 160k)
            if i == 0 and (fmt.bitrate_kbps or fmt.lossless):
                texto = f"★ {texto}"
            self.combo.addItem(texto, fmt)
        if selecionado is not None and getattr(selecionado, 'format_id', '') not in ('', 'bestaudio'):
            for i, fmt in enumerate(ordenados):
                if fmt.format_id == selecionado.format_id:
                    self.combo.setCurrentIndex(i)
                    break

    def _atualizar_origem_formato(self, *_args) -> None:
        formato = self.combo.currentData()
        metodos = getattr(formato, "extra", {}).get("metodos") or [] if formato else []
        texto = "Formato selecionado encontrado por: " + ", ".join(metodos) if metodos else ""
        self.lbl_origem_formato.setText(texto)
        self.lbl_origem_formato.setToolTip(texto)
        # Os métodos ficam acessíveis na comparação e em "ver detalhes"; não
        # aumentam a altura de todos os cartões de uma lista grande.
        self.lbl_origem_formato.setVisible(False)

    def _mostrar_metodos(self, _link: str) -> None:
        QMessageBox.information(self, "Consulta de formatos", self._detalhes_metodos)

    def _comparar_formatos(self) -> None:
        from .format_details import DialogoFormatos
        dialogo = DialogoFormatos(self.resultado, self.combo.currentData(), self)
        if dialogo.exec() != QDialog.Accepted:
            return
        formato = dialogo.formato_selecionado()
        if formato is None:
            return
        for i in range(self.combo.count()):
            item = self.combo.itemData(i)
            if item is formato or (item and item.format_id == formato.format_id):
                self.combo.setCurrentIndex(i)
                break

    def _capa_pronta(self, dados: bytes) -> None:
        if not dados:
            return
        pm = QPixmap()
        if pm.loadFromData(dados):
            self.capa.setPixmap(cortar_quadrado(pm, LADO_CAPA))

    # ------------------------------------------------------------------ ações
    def _emitir_processar(self) -> None:
        formato = self.combo.currentData()
        self.processar.emit({"resultado": self.resultado, "formato": formato})

    def _verificar(self) -> None:
        if not self.ao_detalhar:
            return
        self.btn_verificar.setEnabled(False)
        self.btn_verificar.setText("verificando…")
        self.ao_detalhar(self)

    def aplicar_detalhes(self, resultado: TrackResult) -> None:
        if "arquivo_baixado" in self.resultado.extra:
            resultado.extra["arquivo_baixado"] = self.resultado.extra["arquivo_baixado"]
        self.resultado = resultado
        self._preencher_baixado()
        self._preencher_video()
        self._preencher_selos()
        self._preencher_barra()
        self._preencher_formatos()
        if hasattr(self, "btn_verificar"):
            if resultado.formatos and not resultado.extra.get('erro_detalhe'):
                self.btn_verificar.setVisible(False)
            else:
                # falhou de novo: deixa o usuário tentar outra vez, com o motivo
                self.btn_verificar.setVisible(True)
                self.btn_verificar.setEnabled(True)
                self.btn_verificar.setText("tentar de novo")
                self.btn_verificar.setToolTip(
                    resultado.extra.get("erro_detalhe") or "consultar os formatos outra vez")

    def marcar(self, marcado: bool) -> None:
        self.check.setChecked(marcado)

    def atualizar_resumo(self) -> None:
        """Redesenha os textos que dependem dos dados enriquecidos."""
        try:
            self._preencher_video()
            self._preencher_selos()
            self._preencher_formatos()
        except RuntimeError:
            pass

"""Página de pesquisa: barra, filtros de fonte, resultados e seleção."""
from __future__ import annotations

from typing import Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel,
                               QInputDialog, QMessageBox, QLineEdit, QProgressBar, QPushButton, QScrollArea,
                               QSizePolicy, QSpinBox, QVBoxLayout, QWidget)

from ... import arquivos_baixados, estado_musicas
from ...config import Config
from ...db import Banco
from ...models import TrackResult
from ...search_service import pesquisar, pesquisar_varias
from ...sources import todas_as_fontes
from ...workers import EXECUTOR_GLOBAL
from .. import dialogos
from ..theme import PALETA
from ..widgets.images import CarregadorImagens
from ..widgets.preview_widget import PreviewOverlay
from ..widgets.result_card import ResultCard

EXEMPLOS = ["November Rain", "Bohemian Rhapsody", "Guns N' Roses", "Queen",
            "Rock", "Led Zeppelin"]

# Limita cartões consultados simultaneamente; o comparador limita subprocessos.
PARALELAS = 3


class SearchPage(QWidget):
    processar_pedido = Signal(dict)          # {"resultado", "formato"}
    abrir_downloads = Signal()
    mensagem = Signal(str)
    parcial_pronto = Signal(int, int, object)

    def __init__(self, config: Config, banco: Banco, carregador: CarregadorImagens,
                 pai: Optional[QWidget] = None) -> None:
        super().__init__(pai)
        self.config = config
        self.banco = banco
        self.carregador = carregador
        self.cards: List[ResultCard] = []
        # Seleções vivem na sessão, não nos cartões de uma única pesquisa.
        self._marcados: dict[tuple[str, str], dict] = {}
        self._erro_estado_inicial = ""
        self.transferir_pedido = None
        self._buscando = False
        self._geracao_busca = 0
        self.parcial_pronto.connect(self._receber_parcial)
        self._geracao_baixados = 0
        self._fila_verif: List[ResultCard] = []
        self._verif_ativas = 0
        self._falhas_verif: List[str] = []
        self._falhas_total = 0
        self._avisou_falha = False
        self._aplicando_qtd = False
        self._escolha_manual = False
        self.filtrados: List[TrackResult] = []
        self._cards_filtrados: List[ResultCard] = []
        self._mostrando_filtrados = False
        self._grupos_busca: list[dict] = []
        self.campos_extras: list[tuple[QWidget, QLineEdit]] = []

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(26, 22, 26, 16)
        raiz.setSpacing(12)

        # ------------------------------------------------------- cabeçalho
        topo = QHBoxLayout()
        titulos = QVBoxLayout()
        titulos.setSpacing(2)
        t = QLabel("Pesquisar música")
        t.setObjectName("titulo")
        st = QLabel("Compare as opções, escolha a melhor qualidade e receba o MP3 com capa e tags.")
        st.setObjectName("subtitulo")
        titulos.addWidget(t)
        titulos.addWidget(st)
        topo.addLayout(titulos, 1)
        raiz.addLayout(topo)

        # ---------------------------------------------------------- busca
        linha = QHBoxLayout()
        linha.setSpacing(10)
        self.campo = QLineEdit()
        self.campo.setObjectName("busca")
        self.campo.setPlaceholderText("Música, artista, banda ou link de vídeo do YouTube…")
        self.campo.returnPressed.connect(self.pesquisar)
        linha.addWidget(self.campo, 1)

        self.btn_buscar = QPushButton("Pesquisar")
        self.btn_buscar.setObjectName("primario")
        self.btn_buscar.setMinimumWidth(130)
        self.btn_buscar.clicked.connect(self.pesquisar)
        linha.addWidget(self.btn_buscar)

        rotulo_qtd = QLabel("QUANTIDADE")
        rotulo_qtd.setObjectName("rotulo")
        linha.addWidget(rotulo_qtd)
        self.qtd = QSpinBox()
        self.qtd.setRange(1, 20)
        self.qtd.setValue(int(self.config.get("quantidade_padrao") or 5))
        self.qtd.setFixedWidth(92)
        self.qtd.setToolTip("Quantas músicas o botão “Selecionar os melhores” marca")
        self.qtd.valueChanged.connect(self._quantidade_mudou)
        linha.addWidget(self.qtd)
        raiz.addLayout(linha)

        self.chk_varias = QCheckBox("Pesquisar várias músicas ou artistas de uma vez")
        self.chk_varias.setToolTip("Use o primeiro campo acima e adicione quantos campos precisar.")
        raiz.addWidget(self.chk_varias)
        self.painel_varias = QWidget()
        painel_layout = QVBoxLayout(self.painel_varias)
        painel_layout.setContentsMargins(0, 0, 0, 0)
        painel_layout.setSpacing(5)
        dica_varias = QLabel("Cada campo gera uma seção separada nos resultados. Campos vazios são ignorados.")
        dica_varias.setWordWrap(True)
        painel_layout.addWidget(dica_varias)
        area_campos = QScrollArea()
        area_campos.setWidgetResizable(True)
        area_campos.setMaximumHeight(150)
        area_campos.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        campos_widget = QWidget()
        self.lista_campos = QVBoxLayout(campos_widget)
        self.lista_campos.setContentsMargins(0, 0, 0, 0)
        self.lista_campos.setSpacing(5)
        area_campos.setWidget(campos_widget)
        painel_layout.addWidget(area_campos)
        self.btn_mais_campo = QPushButton("+ Adicionar pesquisa")
        self.btn_mais_campo.setObjectName("fantasma")
        self.btn_mais_campo.clicked.connect(self._adicionar_campo)
        painel_layout.addWidget(self.btn_mais_campo, alignment=Qt.AlignLeft)
        raiz.addWidget(self.painel_varias)
        self.painel_varias.hide()
        self.chk_varias.toggled.connect(self._modo_varias_mudou)

        # ------------------------------------------------- aviso do yt-dlp
        self.aviso_ytdlp = QFrame()
        self.aviso_ytdlp.setObjectName("cartao")
        av = QHBoxLayout(self.aviso_ytdlp)
        av.setContentsMargins(14, 10, 14, 10)
        texto = QLabel("O yt-dlp está ativo: use apenas com conteúdo que você pode baixar "
                       "(Creative Commons, domínio público ou próprio material).")
        texto.setWordWrap(True)
        texto.setStyleSheet(f"color: {PALETA['amarelo']}; font-size: 11.5px;")
        av.addWidget(texto, 1)
        btn_ok = QPushButton("Entendi")
        btn_ok.setObjectName("fantasma")
        btn_ok.clicked.connect(self._aceitar_aviso)
        av.addWidget(btn_ok)
        raiz.addWidget(self.aviso_ytdlp)
        self._atualizar_aviso()

        # -------------------------------------------------------- filtros
        filtros = QHBoxLayout()
        filtros.setSpacing(14)
        rotulo = QLabel("FONTES")
        rotulo.setObjectName("rotulo")
        filtros.addWidget(rotulo)
        self.checks: Dict[str, QCheckBox] = {}
        ativas = set(self.config.get("fontes_ativas") or [])
        self._fontes_obj = todas_as_fontes(self.config)
        for fid, fonte in self._fontes_obj.items():
            check = QCheckBox(fonte.nome)
            check.setChecked(fid in ativas)
            ok, motivo = fonte.disponivel()
            check.setToolTip(motivo or fonte.descricao)
            if motivo:
                check.setStyleSheet(f"color: {PALETA['texto_fraco']};")
                check.setText(f"{fonte.nome} (indisponível)")
            self.checks[fid] = check
            filtros.addWidget(check)
        filtros.addStretch(1)

        rotulo2 = QLabel("ORDENAR")
        rotulo2.setObjectName("rotulo")
        filtros.addWidget(rotulo2)
        self.ordem = QComboBox()
        self.ordem.addItem("Relevância", "relevancia")
        self.ordem.addItem("Melhor qualidade", "qualidade")
        self.ordem.setFixedWidth(180)
        filtros.addWidget(self.ordem)
        raiz.addLayout(filtros)

        # ---- filtro de shows/ao vivo: nada é escondido em silêncio (§3.3) ----
        filtros2 = QHBoxLayout()
        filtros2.setSpacing(12)
        self.chk_filtro = QCheckBox("Ocultar shows / ao vivo")
        self.chk_filtro.setChecked(bool(self.config.get("evitar_ao_vivo", True)))
        self.chk_filtro.setToolTip(
            "Prioriza versões de estúdio e esconde (sem apagar) gravações ao vivo, "
            "shows, festivais e bootlegs. Use o botão ao lado para vê-las.")
        self.chk_filtro.toggled.connect(self._filtro_mudou)
        filtros2.addWidget(self.chk_filtro)

        self.btn_filtrados = QPushButton("Mostrar resultados filtrados (0)")
        self.btn_filtrados.setObjectName("fantasma")
        self.btn_filtrados.setEnabled(False)
        self.btn_filtrados.setToolTip("Os resultados ocultos pelo filtro de ao vivo "
                                      "continuam disponíveis aqui")
        self.btn_filtrados.clicked.connect(self._alternar_filtrados)
        filtros2.addWidget(self.btn_filtrados)
        filtros2.addStretch(1)
        raiz.addLayout(filtros2)

        # --------------------------------------------------------- status
        self.status = QLabel("Digite e pressione Enter para começar.")
        self.status.setObjectName("dim")
        raiz.addWidget(self.status)
        self.status_baixados = QLabel("")
        self.status_baixados.setObjectName("dim")
        self.status_baixados.setWordWrap(True)
        self.status_baixados.hide()
        raiz.addWidget(self.status_baixados)
        self.barra = QProgressBar()
        self.barra.setRange(0, 100)
        self.barra.setValue(0)
        self.barra.setTextVisible(False)
        self.barra.setVisible(False)
        raiz.addWidget(self.barra)

        # ------------------------------------------------------ resultados
        self.area = QScrollArea()
        self.area.setWidgetResizable(True)
        self.area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        conteudo = QWidget()
        self.lista = QVBoxLayout(conteudo)
        self.lista.setContentsMargins(0, 2, 6, 8)
        self.lista.setSpacing(10)
        self.lista.addStretch(1)
        self.area.setWidget(conteudo)
        raiz.addWidget(self.area, 1)

        self.vazio = QLabel(self._texto_vazio())
        self.vazio.setAlignment(Qt.AlignCenter)
        self.vazio.setStyleSheet(f"color: {PALETA['texto_fraco']}; font-size: 13px;")
        self.lista.insertWidget(0, self.vazio)

        # ------------------------------------------------------- rodapé (§10)
        rodape = QHBoxLayout()
        rodape.setSpacing(12)
        self.lbl_selecao = QLabel("nenhuma música marcada")
        self.lbl_selecao.setObjectName("dim")
        self.lbl_selecao.setWordWrap(True)
        raiz.addWidget(self.lbl_selecao)
        # a seleção é MANUAL (proposta §2.3); este botão só marca os melhores
        # quando o usuário pede — nada é marcado sozinho depois da pesquisa
        self.btn_melhores = QPushButton("Selecionar os melhores")
        self.btn_melhores.setObjectName("fantasma")
        self.btn_melhores.setToolTip("Marca os N primeiros de melhor nota "
                                     "(o campo QUANTIDADE). Você pode desmarcar.")
        self.btn_melhores.setEnabled(False)
        self.btn_melhores.clicked.connect(self._selecionar_melhores)
        rodape.addWidget(self.btn_melhores)
        self.btn_listas = QPushButton("Listas salvas")
        self.btn_listas.setObjectName("fantasma")
        self.btn_listas.setToolTip("Salvar as marcações em uma lista ou recuperar uma lista existente.")
        self.btn_listas.clicked.connect(self._menu_listas)
        rodape.addWidget(self.btn_listas)
        self.btn_limpar_marcados = QPushButton("Limpar marcações")
        self.btn_limpar_marcados.setObjectName("fantasma")
        self.btn_limpar_marcados.setToolTip("Desmarca os itens acumulados, sem apagar downloads.")
        self.btn_limpar_marcados.setEnabled(False)
        self.btn_limpar_marcados.clicked.connect(self._limpar_marcados)
        rodape.addWidget(self.btn_limpar_marcados)
        self.btn_lote = QPushButton("ADICIONAR A DOWNLOADS (0)")
        self.btn_lote.setObjectName("primario")
        self.btn_lote.setMinimumHeight(42)
        self.btn_lote.setMinimumWidth(260)
        self.btn_lote.setEnabled(False)
        self.btn_lote.clicked.connect(self._processar_lote)
        rodape.addWidget(self.btn_lote)
        raiz.addLayout(rodape)

        # sobreposição de pré-visualização (cobre a página enquanto aberta)
        self.previa = PreviewOverlay(self)
        self.previa.setVisible(False)
        self._recuperar_marcacoes()

    # ------------------------------------------------------------------ avisos
    def _atualizar_aviso(self) -> None:
        ativo = "ytdlp" in (self.config.get("fontes_ativas") or [])
        mostrar = ativo and not self.config.get("ytdlp_consentido")
        self.aviso_ytdlp.setVisible(bool(mostrar))

    def _aceitar_aviso(self) -> None:
        self.config.update(ytdlp_consentido=True)
        self.aviso_ytdlp.setVisible(False)

    # ------------------------------------------------------------------ textos
    def _texto_vazio(self) -> str:
        exemplos = "   ·   ".join(EXEMPLOS[:4])
        return (f"<div style='line-height:1.9'><b style='font-size:15px'>Nenhum resultado ainda</b><br>"
                f"Experimente: <span style='color:{PALETA['ciano']}'>{exemplos}</span><br>"
                f"<span style='font-size:11px'>A pesquisa usa as fontes marcadas acima. "
                f"Os formatos de cada resultado são verificados automaticamente.</span></div>")

    # ------------------------------------------------------------------ busca
    def _modo_varias_mudou(self, ativo: bool) -> None:
        self.painel_varias.setVisible(ativo)
        if ativo and not self.campos_extras:
            self._adicionar_campo()

    def _adicionar_campo(self) -> None:
        linha = QWidget()
        layout = QHBoxLayout(linha)
        layout.setContentsMargins(0, 0, 0, 0)
        campo = QLineEdit()
        campo.setPlaceholderText("Outra música, artista, banda ou link…")
        campo.returnPressed.connect(self.pesquisar)
        remover = QPushButton("Remover")
        remover.setObjectName("fantasma")
        remover.clicked.connect(lambda: self._remover_campo(linha))
        layout.addWidget(campo, 1)
        layout.addWidget(remover)
        self.lista_campos.addWidget(linha)
        self.campos_extras.append((linha, campo))
        campo.setFocus()

    def _remover_campo(self, linha: QWidget) -> None:
        self.campos_extras = [(w, c) for w, c in self.campos_extras if w is not linha]
        self.lista_campos.removeWidget(linha)
        linha.setParent(None)
        linha.deleteLater()

    def pesquisar(self) -> None:
        consultas = [self.campo.text().strip()]
        if self.chk_varias.isChecked():
            consultas.extend(campo.text().strip() for _, campo in self.campos_extras)
        consultas = [consulta for consulta in consultas if consulta]
        if not consultas or self._buscando:
            return
        consulta = consultas[0]
        self._buscando = True
        self.btn_buscar.setEnabled(False)
        self.btn_buscar.setText("pesquisando…")
        self.barra.setVisible(True)
        self.barra.setValue(2)
        self.status.setText(f"Pesquisando {len(consultas)} termos…" if len(consultas) > 1
                            else f"Pesquisando “{consulta}”…")
        self._limpar()

        fontes = [fid for fid, c in self.checks.items() if c.isChecked()]
        if not fontes:
            self._erro("nenhuma fonte marcada — escolha ao menos uma (ou as Configurações).")
            return
        estados = {fid: self._fontes_obj[fid].disponivel() for fid in fontes
                   if fid in self._fontes_obj}
        if not any(ok for ok, _ in estados.values()):
            motivos = '; '.join(f'{fid}: {motivo}' for fid, (_, motivo) in estados.items())
            self._erro((motivos or 'as fontes marcadas não estão prontas') +
                       ' — confira Configurações → Ferramentas externas e procure novamente.')
            return
        limite = int(self.config.get("limite_resultados") or 20)

        multiplas = len(consultas) > 1
        self._geracao_busca += 1
        geracao = self._geracao_busca
        if multiplas:
            self._iniciar_grupos_parciais(consultas)
            kwargs = {"ao_parcial": lambda indice, dados: self.parcial_pronto.emit(geracao, indice, dados)}
        else:
            kwargs = {"enriquecer_automatico": False}
        EXECUTOR_GLOBAL.rodar(
            pesquisar_varias if multiplas else pesquisar,
            consultas if multiplas else consulta, self.config, limite, fontes,
            ordenar_por=self.ordem.currentData(), com_progresso=True, **kwargs,
            ao_resultado=(lambda respostas: self._terminar_varias(geracao, respostas)) if multiplas
                         else (lambda dados: self._mostrar(dados) if geracao == self._geracao_busca else None),
            ao_erro=lambda msg: self._erro(msg) if geracao == self._geracao_busca else None,
            ao_progresso=lambda pct, msg: (self.barra.setValue(max(2, int(pct * 0.9))),
                                           self.status.setText(msg)) if geracao == self._geracao_busca else None,
        )

    def _erro(self, msg: str) -> None:
        self._buscando = False
        self.barra.setVisible(False)
        self.btn_buscar.setEnabled(True)
        self.btn_buscar.setText("Pesquisar")
        self.status.setText(f"Não foi possível pesquisar: {msg}")
        self.mensagem.emit(f"Falha na pesquisa: {msg[:120]}")

    def _mostrar(self, dados: dict) -> None:
        self._buscando = False
        self.btn_buscar.setEnabled(True)
        self.btn_buscar.setText("Pesquisar")
        self.barra.setVisible(False)
        self._limpar()

        resultados: List[TrackResult] = list(dados.get("resultados") or [])
        self.filtrados = list(dados.get("filtrados") or [])
        self._cards_filtrados = []
        self._mostrando_filtrados = False
        self.btn_filtrados.setText(f"Mostrar resultados filtrados ({len(self.filtrados)})")
        self.btn_filtrados.setEnabled(bool(self.filtrados))
        self.banco.registrar_historico(
            "pesquisa", dados.get("consulta", ""),
            ", ".join(dados.get("fontes") or []),
            f"{len(resultados)} resultado(s)", len(resultados))

        partes = [f"{len(resultados)} resultado(s)", f"{dados.get('segundos')}s"]
        if dados.get("fontes"):
            partes.append("fontes: " + ", ".join(dados["fontes"]))
        if dados.get("erros"):
            partes.append("erros: " + ", ".join(dados["erros"].keys()))
        self._status_base = "  ·  ".join(partes)
        self.status.setText(self._status_base)

        if not resultados:
            motivos = "; ".join(f"{k}: {v}" for k, v in (dados.get("erros") or {}).items())
            self.vazio.setText(
                f"<div style='line-height:1.9'><b style='font-size:15px'>Nada encontrado</b><br>"
                f"Tente outro termo ou confira a fonte nas Configurações.<br>"
                f"<span style='font-size:11px'>{motivos}</span></div>")
            self.vazio.setVisible(True)
            if dados.get("erros"):
                principal = list(dados["erros"].values())[0]
                self.status.setText(f"{self._status_base}  ·  {principal[:170]}")
                self.mensagem.emit(f"A pesquisa falhou: {principal[:150]}")
            return

        self.vazio.setVisible(False)
        for r in resultados:
            card = self._criar_card(r)
            self.cards.append(card)
            self.lista.insertWidget(self.lista.count() - 1, card)
        # NADA é marcado automaticamente (proposta §2.3): o usuário escolhe.
        self._escolha_manual = False
        self.btn_melhores.setEnabled(bool(self.cards))
        self._atualizar_lote()
        self._avisar_filtrados()
        self._agendar_verificacoes()
        self._conferir_baixados(resultados + self.filtrados)

    def _iniciar_grupos_parciais(self, consultas: list[str]) -> None:
        self.vazio.hide()
        self._status_base = f"0/{len(consultas)} pesquisas concluídas"
        for consulta in consultas:
            caixa = QFrame()
            caixa.setObjectName("cartao")
            layout = QVBoxLayout(caixa)
            layout.setContentsMargins(12, 12, 12, 12)
            titulo = QLabel(f"Pesquisa: {consulta}  ·  pesquisando…")
            titulo.setTextFormat(Qt.PlainText)
            titulo.setWordWrap(True)
            titulo.setStyleSheet("font-size: 15px; font-weight: 700;")
            layout.addWidget(titulo)
            self.lista.insertWidget(self.lista.count() - 1, caixa)
            self._grupos_busca.append({'consulta': consulta, 'widget': caixa, 'layout': layout,
                'titulo': titulo, 'cards': [], 'filtrados': [], 'cards_filtrados': [], 'concluido': False})

    def _receber_parcial(self, geracao: int, indice: int, dados: dict) -> None:
        if geracao != self._geracao_busca or not self._buscando or not (0 <= indice < len(self._grupos_busca)):
            return
        grupo = self._grupos_busca[indice]
        if grupo.get('concluido'):
            return
        grupo['concluido'] = True
        resultados = list(dados.get('resultados') or [])
        filtrados = list(dados.get('filtrados') or [])
        grupo['filtrados'] = filtrados
        grupo['resultados'] = resultados
        grupo['titulo'].setText(f"Pesquisa: {grupo['consulta']}  ·  {len(resultados)} resultado(s)")
        erros = dados.get('erros') or {}
        if erros:
            aviso = QLabel("Erro em fonte(s): " + "; ".join(f"{k}: {v}" for k, v in erros.items()))
            aviso.setTextFormat(Qt.PlainText)
            aviso.setWordWrap(True)
            grupo['layout'].addWidget(aviso)
        if not resultados:
            grupo['layout'].addWidget(QLabel("Nenhum resultado visível para esta pesquisa."))
        if filtrados:
            texto = QLabel(f"{len(filtrados)} resultado(s) filtrado(s); use o botão acima para mostrar.")
            texto.setWordWrap(True)
            grupo['layout'].addWidget(texto)
        novos = []
        for resultado in resultados:
            card = self._criar_card(resultado)
            self.cards.append(card)
            grupo['cards'].append(card)
            grupo['layout'].addWidget(card)
            novos.append(card)
        self.filtrados.extend(filtrados)
        if self._mostrando_filtrados:
            for resultado in filtrados:
                resultado.filtrado = True
                card = self._criar_card(resultado)
                self.cards.append(card)
                self._cards_filtrados.append(card)
                grupo['cards_filtrados'].append(card)
                grupo['layout'].addWidget(card)
                novos.append(card)
        self.banco.registrar_historico('pesquisa', grupo['consulta'], ', '.join(dados.get('fontes') or []),
                                       f"{len(resultados)} resultado(s)", len(resultados))
        quantidade = len(self.filtrados)
        acao = 'Ocultar' if self._mostrando_filtrados else 'Mostrar'
        self.btn_filtrados.setText(f"{acao} resultados filtrados ({quantidade})")
        self.btn_filtrados.setEnabled(bool(quantidade))
        self.btn_melhores.setEnabled(bool(self.cards))
        feitos = sum(bool(g.get('concluido')) for g in self._grupos_busca)
        self._status_base = f"{feitos}/{len(self._grupos_busca)} pesquisas concluídas · {len(self.cards)} resultado(s)"
        self.status.setText(self._status_base)
        self._atualizar_lote()
        self._fila_verif.extend(c for c in novos if (not c.resultado.formatos or
            (c.resultado.fonte == 'ytdlp' and not c.resultado.extra.get('metodos_consulta')))
            and not c.resultado.extra.get('erro_detalhe'))
        self._verificar_proximo()

    def _terminar_varias(self, geracao: int, respostas: list[dict]) -> None:
        if geracao != self._geracao_busca or not self._buscando:
            return
        for i, dados in enumerate(respostas):
            self._receber_parcial(geracao, i, dados)
        self._buscando = False
        self.btn_buscar.setEnabled(True)
        self.btn_buscar.setText("Pesquisar")
        self.barra.setVisible(False)
        self._status_base = f"{len(respostas)} pesquisa(s) · {len(self.cards)} resultado(s)"
        self.status.setText(self._status_base)
        todos = [r for g in self._grupos_busca for r in g.get('resultados', []) + g['filtrados']]
        if self.filtrados:
            self._avisar_filtrados()
        if todos:
            self._conferir_baixados(todos)

    def _mostrar_varias(self, respostas: list[dict]) -> None:
        """Apresenta uma seção por termo, inclusive quando um deles falha."""
        self._buscando = False
        self.btn_buscar.setEnabled(True)
        self.btn_buscar.setText("Pesquisar")
        self.barra.setVisible(False)
        self._limpar()
        todos = []
        total_filtrados = 0
        for dados in respostas:
            resultados = list(dados.get("resultados") or [])
            filtrados = list(dados.get("filtrados") or [])
            consulta = str(dados.get("consulta") or "")
            erros = dados.get("erros") or {}
            grupo_widget = QFrame()
            grupo_widget.setObjectName("cartao")
            layout = QVBoxLayout(grupo_widget)
            layout.setContentsMargins(12, 12, 12, 12)
            layout.setSpacing(8)
            titulo = QLabel(f"Pesquisa: {consulta}  ·  {len(resultados)} resultado(s)")
            titulo.setTextFormat(Qt.PlainText)
            titulo.setWordWrap(True)
            titulo.setStyleSheet("font-size: 15px; font-weight: 700;")
            layout.addWidget(titulo)
            if erros:
                aviso = QLabel("Erro em fonte(s): " + "; ".join(f"{k}: {v}" for k, v in erros.items()))
                aviso.setTextFormat(Qt.PlainText)
                aviso.setWordWrap(True)
                layout.addWidget(aviso)
            if not resultados:
                layout.addWidget(QLabel("Nenhum resultado visível para esta pesquisa."))
            if filtrados:
                info = QLabel(f"{len(filtrados)} resultado(s) filtrado(s); use o botão acima para mostrar.")
                info.setWordWrap(True)
                layout.addWidget(info)
            grupo = {"consulta": consulta, "widget": grupo_widget, "layout": layout,
                     "cards": [], "filtrados": filtrados, "cards_filtrados": []}
            self._grupos_busca.append(grupo)
            self.lista.insertWidget(self.lista.count() - 1, grupo_widget)
            for r in resultados:
                card = self._criar_card(r)
                self.cards.append(card)
                grupo["cards"].append(card)
                layout.addWidget(card)
            self.banco.registrar_historico("pesquisa", consulta,
                ", ".join(dados.get("fontes") or []),
                f"{len(resultados)} resultado(s)", len(resultados))
            self.filtrados.extend(filtrados)
            total_filtrados += len(filtrados)
            todos.extend(resultados + filtrados)
        self.vazio.setVisible(not respostas)
        self.btn_filtrados.setText(f"Mostrar resultados filtrados ({total_filtrados})")
        self.btn_filtrados.setEnabled(bool(total_filtrados))
        self.btn_melhores.setEnabled(bool(self.cards))
        self._status_base = f"{len(respostas)} pesquisa(s) · {len(self.cards)} resultado(s)"
        self.status.setText(self._status_base)
        self._escolha_manual = False
        self._atualizar_lote()
        self._avisar_filtrados()
        self._agendar_verificacoes()
        if todos:
            self._conferir_baixados(todos)

    def _conferir_baixados(self, resultados: List[TrackResult]) -> None:
        # Cópia evita que o detalhamento de formatos altere os dados da busca
        # enquanto a leitura de disco está em outra thread.
        from copy import copy
        consulta = []
        for resultado in resultados:
            copia = copy(resultado)
            copia.extra = dict(resultado.extra)
            consulta.append(copia)
        geracao = self._geracao_baixados
        pastas = [str(self.config.get("pasta_saida") or ""),
                  str(self.config.get("pasta_verificar_baixados") or "")]
        self.status_baixados.setText("Verificando MP3s nas pastas escolhidas e subpastas…")
        self.status_baixados.show()
        EXECUTOR_GLOBAL.rodar(
            arquivos_baixados.conferir, consulta, pastas,
            ao_resultado=lambda dados: self._baixados_prontos(geracao, resultados, dados),
            ao_erro=lambda msg: self._baixados_falharam(geracao, msg))

    def _baixados_prontos(self, geracao: int, resultados: List[TrackResult], dados: dict) -> None:
        if geracao != self._geracao_baixados:
            return
        matches = dados.get("correspondencias") or []
        for resultado, achado in zip(resultados, matches):
            resultado.extra["arquivo_baixado"] = achado
            for card in self.cards:
                if getattr(card, "_resultado_inicial_baixados", None) is resultado:
                    card.resultado.extra["arquivo_baixado"] = achado
                    card._preencher_baixado()
        quantidade = sum(bool(x) for x in matches)
        texto = f"Verificação local: {quantidade} possível(is) resultado(s) já salvo(s)."
        erros = dados.get("erros") or []
        if erros:
            texto += f" Verificação incompleta: {len(erros)} erro(s); confira as pastas."
            self.status_baixados.setToolTip("\n".join(erros[:10]))
        else:
            self.status_baixados.setToolTip("Pasta de saída e pasta adicional, incluindo subpastas.")
        self.status_baixados.setText(texto)

    def _baixados_falharam(self, geracao: int, mensagem: str) -> None:
        if geracao != self._geracao_baixados:
            return
        self.status_baixados.setText("Não foi possível verificar os MP3s locais.")
        self.status_baixados.setToolTip(mensagem)

    # --------------------------------------------------- filtro de ao vivo
    def _filtro_mudou(self, ligado: bool) -> None:
        """Liga/desliga o filtro de shows (a próxima pesquisa já usa)."""
        self.config.update(evitar_ao_vivo=bool(ligado))
        if not ligado and self._mostrando_filtrados:
            self._alternar_filtrados()

    def _avisar_filtrados(self) -> None:
        if not self.filtrados:
            return
        total = len(self.filtrados)
        self.status.setText(
            f"{self._status_base}  ·  {total} resultado(s) de show/ao vivo "
            f"fora da lista — use “Mostrar resultados filtrados”")
        self.mensagem.emit(
            f"{total} resultado(s) parecem gravação ao vivo e ficaram ocultos. "
            f"Eles não foram descartados: veja em “Mostrar resultados filtrados”.")

    def _alternar_filtrados(self) -> None:
        """Mostra/esconde os resultados filtrados — nunca os apaga."""
        if not self.filtrados:
            return
        if self._mostrando_filtrados:
            for card in self._cards_filtrados:
                if card in self.cards:
                    self.cards.remove(card)
                card.setParent(None)
                card.deleteLater()
            self._cards_filtrados = []
            for grupo in self._grupos_busca:
                grupo["cards_filtrados"] = []
            self._mostrando_filtrados = False
            self.btn_filtrados.setText(f"Mostrar resultados filtrados ({len(self.filtrados)})")
            self.btn_melhores.setEnabled(bool(self.cards))
            self.vazio.setVisible(not self.cards and not self._grupos_busca)
            self._atualizar_lote()
            return
        self.vazio.setVisible(False)
        grupos = self._grupos_busca or [{"filtrados": self.filtrados, "layout": self.lista}]
        for grupo in grupos:
            grupo["cards_filtrados"] = []
            for r in grupo["filtrados"]:
                r.filtrado = True
                card = self._criar_card(r)
                self.cards.append(card)
                self._cards_filtrados.append(card)
                grupo["cards_filtrados"].append(card)
                if self._grupos_busca:
                    grupo["layout"].addWidget(card)
                else:
                    self.lista.insertWidget(self.lista.count() - 1, card)
        self._mostrando_filtrados = True
        self.btn_melhores.setEnabled(bool(self.cards))
        self.btn_filtrados.setText(f"Ocultar resultados filtrados ({len(self.filtrados)})")
        self.mensagem.emit("Resultados filtrados exibidos — confira o aviso de ao vivo "
                           "antes de marcar qualquer um deles.")
        self._atualizar_lote()
        # Os resultados filtrados também recebem as quatro consultas quando exibidos.
        self._fila_verif.extend(c for c in self._cards_filtrados
                                if not c.resultado.extra.get("metodos_consulta")
                                and not c.resultado.extra.get("erro_detalhe"))
        self._verificar_proximo()

    # ---------------------------------------------------------- pré-visualização
    def _abrir_previa(self, dados: dict) -> None:
        resultado = dados.get("resultado")
        if resultado is None:
            return
        self.previa.setGeometry(self.rect())
        self.previa.mostrar(resultado)

    def resizeEvent(self, evento) -> None:                       # noqa: N802
        super().resizeEvent(evento)
        if self.previa.isVisible():
            self.previa.setGeometry(self.rect())

    def _limpar(self) -> None:
        self._geracao_baixados += 1
        self.status_baixados.clear()
        self.status_baixados.hide()
        self._fila_verif.clear()
        self._falhas_verif = []
        self._falhas_total = 0
        self._avisou_falha = False
        self._aplicando_qtd = False
        self._escolha_manual = False
        self.filtrados = []
        self._cards_filtrados = []
        self._mostrando_filtrados = False
        try:
            self.btn_filtrados.setText("Mostrar resultados filtrados (0)")
            self.btn_filtrados.setEnabled(False)
            self.btn_melhores.setEnabled(False)
            self.previa.fechar()
        except (RuntimeError, AttributeError):
            pass
        for card in self.cards:
            card.setParent(None)
            card.deleteLater()
        self.cards.clear()
        for grupo in self._grupos_busca:
            grupo["widget"].setParent(None)
            grupo["widget"].deleteLater()
        self._grupos_busca.clear()
        self.vazio.setVisible(True)
        self._atualizar_lote()

    # ------------------------------------------- verificação de qualidade
    def _agendar_verificacoes(self) -> None:
        """Consulta os formatos dos resultados exibidos, em segundo plano."""
        pendentes = [c for c in self.cards
                     if (not c.resultado.formatos or
                         (c.resultado.fonte == "ytdlp" and not c.resultado.extra.get("metodos_consulta")))
                     and not c.resultado.extra.get("erro_detalhe")]
        self._fila_verif = pendentes
        self._verif_total = len(self._fila_verif)
        if self._fila_verif:
            self.status.setText(
                f"{self._status_base}  ·  consultando 4 métodos de qualidade para "
                f"{len(self._fila_verif)} de {len(self.cards)}…")
        self._verificar_proximo()

    def _verificar_proximo(self) -> None:
        while self._fila_verif and self._verif_ativas < PARALELAS:
            card = self._fila_verif.pop(0)
            fonte = self._fonte_de(card.resultado.fonte)
            if not fonte:
                continue
            self._verif_ativas += 1
            EXECUTOR_GLOBAL.rodar(
                fonte.detalhar, card.resultado,
                ao_resultado=lambda r, c=card: self._detalhe_pronto(c, r),
                ao_erro=lambda m, c=card: self._detalhe_falhou(c, m),
            )
        self._status_verificacao()

    def _status_verificacao(self) -> None:
        if self._fila_verif or self._verif_ativas:
            return
        base = getattr(self, "_status_base", None)
        if not base:
            return
        if self.ordem.currentData() == "qualidade":
            from ...quality import pontuar
            # A pesquisa aparece imediatamente; reorganizar só quando as
            # consultas terminam, sem recriar cartões nem perder a seleção.
            normais = [c for c in self.cards if c not in self._cards_filtrados]
            filtrados = [c for c in self.cards if c in self._cards_filtrados]
            chave = lambda c: (pontuar(c.resultado.melhor) if c.resultado.melhor else -1,
                               c.resultado.nota_musica)
            if self._grupos_busca:
                self.cards[:] = []
                for grupo in self._grupos_busca:
                    normais_grupo = sorted(grupo["cards"], key=chave, reverse=True)
                    filtrados_grupo = sorted(grupo["cards_filtrados"], key=chave, reverse=True)
                    grupo["cards"] = normais_grupo
                    grupo["cards_filtrados"] = filtrados_grupo
                    for card in normais_grupo + filtrados_grupo:
                        grupo["layout"].removeWidget(card)
                        grupo["layout"].addWidget(card)
                        self.cards.append(card)
            else:
                self.cards[:] = sorted(normais, key=chave, reverse=True) + sorted(filtrados, key=chave, reverse=True)
                for card in self.cards:
                    self.lista.removeWidget(card)
                    self.lista.insertWidget(self.lista.count() - 1, card)
        verificados = sum(1 for c in self.cards if c.resultado.formatos)
        partes = [base]
        if verificados:
            partes.append(f"qualidade verificada em {verificados}")
        if self._falhas_verif:
            partes.append(f"não detectada em {self._falhas_total}")
            partes.append(self._falhas_verif[0].split(" — ")[0][:90])
        self.status.setText("  ·  ".join(partes))
        if self._falhas_verif and not self._avisou_falha:
            self._avisou_falha = True
            self.mensagem.emit(
                "A qualidade não pôde ser lida: " + self._falhas_verif[0][:160] +
                " — o download também pode falhar; confira os métodos no cartão.")

    def _fonte_de(self, fid: str):
        from ...sources import por_id
        return por_id(fid, self.config)

    def _detalhe_pronto(self, card: ResultCard, resultado: TrackResult) -> None:
        self._verif_ativas = max(0, self._verif_ativas - 1)
        if card not in self.cards:
            self._verificar_proximo()
            return
        # A consulta em segundo plano pode descobrir sinais de ao vivo depois
        # que a lista já foi exibida. Avisar no cartão sem movê-lo de surpresa.
        from ...pesquisa import filtros
        analise = filtros.analisar(resultado)
        resultado.ao_vivo = analise.ao_vivo
        resultado.ao_vivo_certeza = analise.certeza
        resultado.sinais_ao_vivo = analise.sinais
        try:
            pedido = self._marcados.get(self._chave_resultado(card.resultado))
            formato = pedido.get('formato') if pedido else card.combo.currentData()
            card.combo.blockSignals(True)
            try:
                card.aplicar_detalhes(resultado)
                self._restaurar_formato(card, formato)
                card._atualizar_origem_formato()
            finally:
                card.combo.blockSignals(False)
            self._formato_mudou(card)
        except RuntimeError:
            pass                                   # card já foi removido
        if not resultado.formatos:
            self._falhas_total += 1
            motivo = resultado.extra.get("erro_detalhe")
            if motivo and motivo not in self._falhas_verif:
                self._falhas_verif.append(motivo)
        self._verificar_proximo()

    def _detalhe_falhou(self, card: ResultCard, msg: str) -> None:
        self._verif_ativas = max(0, self._verif_ativas - 1)
        if card not in self.cards:
            self._verificar_proximo()
            return
        try:
            if hasattr(card, "btn_verificar"):
                card.btn_verificar.setText("verificar de novo")
                card.btn_verificar.setEnabled(True)
        except RuntimeError:
            pass
        self.mensagem.emit(f"Não foi possível verificar a qualidade: {msg[:100]}")
        self._verificar_proximo()

    # --------------------------------------------------------------- detalhar
    def _detalhar(self, card: ResultCard) -> None:
        """Verificação manual (botão do cartão ou "tentar de novo")."""
        card.resultado.extra.pop("erro_detalhe", None)
        card.resultado.aviso = "qualidade a verificar"
        try:
            card._preencher_selos()
            formato = card.combo.currentData()
            card.combo.blockSignals(True)
            try:
                card._preencher_formatos()
                self._restaurar_formato(card, formato)
                card._atualizar_origem_formato()
            finally:
                card.combo.blockSignals(False)
            card.btn_verificar.setEnabled(False)
            card.btn_verificar.setText("verificando…")
        except RuntimeError:
            return
        if card not in self._fila_verif:
            self._fila_verif.insert(0, card)
        self._verificar_proximo()

    @staticmethod
    def _chave_resultado(resultado: TrackResult) -> tuple[str, str]:
        return str(resultado.fonte), str(resultado.uid)

    @staticmethod
    def _restaurar_formato(card: ResultCard, formato) -> None:
        """Conserva a escolha explícita mesmo que uma nova consulta não a confirme."""
        if formato is None or getattr(formato, 'format_id', '') in ('', 'bestaudio'):
            return
        for i in range(card.combo.count()):
            item = card.combo.itemData(i)
            if item and item.format_id == formato.format_id:
                card.combo.setCurrentIndex(i)
                card._atualizar_origem_formato()
                return
        texto = f"{formato.descricao_curta()} · id {formato.format_id} · não confirmado nesta consulta"
        card.combo.addItem(texto, formato)
        indice = card.combo.count() - 1
        card.combo.setItemData(indice, "Escolha anterior: a última consulta não confirmou este formato. "
                               "Se ele estiver indisponível, o download apresentará erro.", Qt.ToolTipRole)
        card.combo.setEnabled(True)
        card.combo.setCurrentIndex(indice)
        card._atualizar_origem_formato()

    def _criar_card(self, resultado: TrackResult) -> ResultCard:
        chave = self._chave_resultado(resultado)
        pedido = self._marcados.get(chave)
        r = pedido['resultado'] if pedido else resultado
        card = ResultCard(r, self.carregador, ao_detalhar=self._detalhar)
        card._resultado_inicial_baixados = resultado
        card.processar.connect(self._processar_um)
        card.selecionado.connect(lambda marcado, c=card: self._selecao_mudou(c, marcado))
        card.combo.currentIndexChanged.connect(lambda _idx, c=card: self._formato_mudou(c))
        card.prever.connect(self._abrir_previa)
        if pedido:
            card.combo.blockSignals(True)
            try:
                self._restaurar_formato(card, pedido.get('formato'))
            finally:
                card.combo.blockSignals(False)
            card.check.blockSignals(True)
            card.check.setChecked(True)
            card.check.blockSignals(False)
        return card

    def _selecao_mudou(self, card: ResultCard, marcado: bool) -> None:
        chave = self._chave_resultado(card.resultado)
        if marcado:
            self._marcados[chave] = {'resultado': card.resultado, 'formato': card.combo.currentData()}
        else:
            self._marcados.pop(chave, None)
        for outro in self.cards:
            if outro is not card and self._chave_resultado(outro.resultado) == chave:
                outro.check.blockSignals(True)
                outro.check.setChecked(marcado)
                outro.check.blockSignals(False)
        self._atualizar_lote()
        if marcado:
            self._formato_mudou(card)
        else:
            self._gravar_marcacoes()

    def _formato_mudou(self, card: ResultCard) -> None:
        chave = self._chave_resultado(card.resultado)
        formato = card.combo.currentData()
        if chave in self._marcados and formato is not None:
            edicao = self._marcados[chave].get('edicao')
            self._marcados[chave] = {'resultado': card.resultado, 'formato': formato, 'edicao': edicao or {}}
            for outro in self.cards:
                if outro is card or self._chave_resultado(outro.resultado) != chave:
                    continue
                outro.combo.blockSignals(True)
                try:
                    self._restaurar_formato(outro, formato)
                finally:
                    outro.combo.blockSignals(False)
            self._gravar_marcacoes()

    def _limpar_marcados(self) -> None:
        self._marcados.clear()
        self._gravar_marcacoes()
        for card in self.cards:
            card.check.blockSignals(True)
            card.check.setChecked(False)
            card.check.blockSignals(False)
        self._atualizar_lote()

    def _gravar_marcacoes(self) -> bool:
        if self._erro_estado_inicial:
            self.mensagem.emit("Não é possível salvar: houve falha ao recuperar as marcações anteriores.")
            return False
        try:
            self.banco.salvar_estado('marcacoes', [estado_musicas.serializar_pedido(p)
                                                    for p in self._marcados.values()])
            return True
        except Exception as exc:
            self.mensagem.emit(f"Não foi possível salvar as marcações: {exc}")
            self.status.setText("Não foi possível salvar as marcações no computador. Confira o banco de dados.")
            return False

    def _recuperar_marcacoes(self) -> None:
        try:
            registros = self.banco.ler_estado('marcacoes', []) or []
            pedidos = [estado_musicas.desserializar_pedido(dados) for dados in registros]
            for pedido in pedidos:
                self._marcados[self._chave_resultado(pedido['resultado'])] = pedido
            self._atualizar_lote()
        except Exception as exc:
            # Não sobrescreve o conteúdo original se ele não puder ser lido.
            self._erro_estado_inicial = str(exc)
            self.status.setText("Não foi possível recuperar as marcações salvas; confira o banco de dados.")

    def _guardar_lista(self, nome: str, substituir: bool = False) -> None:
        nome = nome.strip()
        if not nome or not self._marcados:
            raise ValueError("Digite um nome e marque pelo menos uma música.")
        if not substituir and nome.casefold() in {n.casefold() for n in self.banco.nomes_listas()}:
            raise ValueError("Já existe uma lista com esse nome.")
        existente = next((n for n in self.banco.nomes_listas() if n.casefold() == nome.casefold()), None)
        if existente:
            nome = existente
        self.banco.salvar_lista(nome, [estado_musicas.serializar_pedido(p)
                                      for p in self._marcados.values()])

    def _carregar_lista(self, nome: str) -> int:
        # Converte tudo antes de alterar as marcações, para não carregar parcialmente.
        pedidos = [estado_musicas.desserializar_pedido(d) for d in self.banco.ler_lista(nome)]
        for pedido in pedidos:
            self._marcados[self._chave_resultado(pedido['resultado'])] = pedido
        for card in self.cards:
            pedido = self._marcados.get(self._chave_resultado(card.resultado))
            if pedido:
                fmt = pedido.get('formato')
                card.check.blockSignals(True)
                card.check.setChecked(True)
                card.check.blockSignals(False)
                if fmt:
                    card.combo.blockSignals(True)
                    try:
                        self._restaurar_formato(card, fmt)
                    finally:
                        card.combo.blockSignals(False)
        self._atualizar_lote()
        self._gravar_marcacoes()
        return len(pedidos)

    def _menu_listas(self) -> None:
        acao, ok = QInputDialog.getItem(self, "Listas de músicas", "O que deseja fazer?",
            ["Salvar marcações em uma lista", "Carregar uma lista", "Excluir uma lista"], 0, False)
        if not ok:
            return
        try:
            if acao.startswith("Salvar"):
                if not self._marcados:
                    self.mensagem.emit("Marque músicas antes de salvar uma lista.")
                    return
                nome, ok = QInputDialog.getText(self, "Salvar lista", "Nome da lista:")
                if not ok or not nome.strip():
                    return
                substituir = nome.strip().casefold() in {n.casefold() for n in self.banco.nomes_listas()}
                if substituir and QMessageBox.question(self, "Substituir lista?",
                    f"A lista ‘{nome.strip()}’ já existe. Substituir seu conteúdo?",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                    return
                self._guardar_lista(nome, substituir)
                self.mensagem.emit(f"Lista ‘{nome.strip()}’ salva.")
            else:
                nomes = self.banco.nomes_listas()
                if not nomes:
                    self.mensagem.emit("Você ainda não tem listas salvas.")
                    return
                nome, ok = QInputDialog.getItem(self, "Listas de músicas", "Escolha a lista:", nomes, 0, False)
                if not ok:
                    return
                if acao.startswith("Carregar"):
                    n = self._carregar_lista(nome)
                    self.mensagem.emit(f"Lista ‘{nome}’ carregada: {n} música(s).")
                elif QMessageBox.question(self, "Excluir lista?", f"Excluir a lista ‘{nome}’? Suas músicas não serão apagadas.",
                                           QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
                    self.banco.apagar_lista(nome)
                    self.mensagem.emit(f"Lista ‘{nome}’ excluída.")
        except Exception as exc:
            QMessageBox.warning(self, "Listas de músicas", str(exc)[:500])

    # ---------------------------------------------------------------- processar
    def _transferir(self, pedido: dict) -> bool:
        if self.transferir_pedido is not None:
            return bool(self.transferir_pedido(pedido))
        self.processar_pedido.emit(pedido)
        return True

    def _processar_um(self, dados: dict) -> None:
        """Adiciona um resultado sem sair da pesquisa nem baixar o áudio."""
        resultado = dados.get("resultado")
        if resultado is None:
            return
        if not self._transferir(dados):
            return
        chave = self._chave_resultado(resultado)
        self._marcados.pop(chave, None)
        self._gravar_marcacoes()
        for card in self.cards:
            if self._chave_resultado(card.resultado) == chave and card.check.isChecked():
                card.check.setChecked(False)
        self._atualizar_lote()

    def _selecionar_melhores(self) -> None:
        """Marca, a pedido do usuário, os N resultados de maior nota (§9/§10).

        Antes isso acontecia sozinho depois da pesquisa; na v0.5.0 a escolha é
        sempre do usuário (proposta §2.3) — este atalho só existe para quem
        quiser marcar vários de uma vez.
        """
        if not self.cards:
            return
        n = int(self.qtd.value())
        ordenados = sorted(self.cards, key=lambda c: c.resultado.nota_musica,
                           reverse=True)
        self._aplicando_qtd = True
        for card in self.cards:
            card.check.setChecked(False)
        for card in ordenados[:n]:
            card.check.setChecked(True)
        self._aplicando_qtd = False
        self._escolha_manual = True
        self._atualizar_lote()

    def _quantidade_mudou(self, _valor: int) -> None:
        """A quantidade só vale para o atalho “Selecionar os melhores”."""
        self._escolha_manual = True

    def _atualizar_lote(self, *_args) -> None:
        total = len(self._marcados)
        visiveis = sum(1 for c in self.cards if c.check.isChecked())
        if not self._aplicando_qtd:
            self._escolha_manual = True
        self.btn_lote.setEnabled(bool(total))
        self.btn_limpar_marcados.setEnabled(bool(total))
        self.btn_lote.setText(f"ADICIONAR A DOWNLOADS ({total})")
        if total:
            self.lbl_selecao.setText(
                f"{total} marcada(s), {visiveis} nesta pesquisa — "
                f"revise as capas em Downloads antes de baixar.")
        else:
            self.lbl_selecao.setText("nenhuma música marcada")

    def _processar_lote(self) -> None:
        """Transfere todas as marcações da sessão sem iniciar o download."""
        pedidos = [dict(pedido, lote=True) for pedido in self._marcados.values()]
        if not pedidos:
            return
        transferidas = []
        for pedido in pedidos:
            if self._transferir(pedido):
                transferidas.append(self._chave_resultado(pedido['resultado']))
        for chave in transferidas:
            self._marcados.pop(chave, None)
        self._gravar_marcacoes()
        for card in self.cards:
            if self._chave_resultado(card.resultado) in transferidas:
                card.check.blockSignals(True)
                card.check.setChecked(False)
                card.check.blockSignals(False)
        self._atualizar_lote()
        if transferidas:
            self.abrir_downloads.emit()

    def atualizar_ferramentas(self, dados: dict) -> None:
        ferramenta = dados.get('yt-dlp')
        check = self.checks.get('ytdlp')
        fonte = self._fontes_obj.get('ytdlp')
        if ferramenta and check and fonte:
            check.setText(fonte.nome if ferramenta.ok else f'{fonte.nome} (indisponível)')
            check.setToolTip(fonte.descricao if ferramenta.ok else ferramenta.erro)
            check.setStyleSheet('' if ferramenta.ok else f"color: {PALETA['texto_fraco']};")

    def recarregar_fontes(self) -> None:
        """Chamado quando as Configurações mudam."""
        ativas = set(self.config.get("fontes_ativas") or [])
        for fid, chk in self.checks.items():
            chk.setChecked(fid in ativas)
            fonte = self._fontes_obj.get(fid)
            if fonte:
                ok, motivo = fonte.disponivel()
                chk.setText(fonte.nome if ok else f'{fonte.nome} (indisponível)')
                chk.setToolTip(motivo or fonte.descricao)
                chk.setStyleSheet('' if ok else f"color: {PALETA['texto_fraco']};")
        self._atualizar_aviso()

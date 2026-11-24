"""Configurações: cookies, ferramentas, saída, metadados e fontes."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, Optional

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout,
                               QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
                               QScrollArea, QSpinBox, QVBoxLayout, QWidget)

from ... import cookies as cookies_mod, seguranca
from ...config import Config, RAIZ
from ...sources import todas_as_fontes
from ...ia import cliente_groq
from ...tools import status_ferramentas
from ...workers import EXECUTOR_GLOBAL
from ..theme import PALETA, alfa
from ..widgets.result_card import Chip

MODELOS_ORGANIZACAO = [
    ("{artista}/{titulo}.mp3", "Artista/Título.mp3"),
    ("{artista}/{artista} - {titulo}.mp3", "Artista/Artista - Título.mp3"),
    ("{artista}/{album}/{faixa} {titulo}.mp3", "Artista/Álbum/01 Título.mp3"),
    ("{artista}/{album}/{artista} - {titulo}.mp3", "Artista/Álbum/Artista - Título.mp3"),
    ("{genero}/{artista} - {titulo}.mp3", "Gênero/Artista - Título.mp3"),
    ("{titulo}.mp3", "Tudo solto na pasta"),
]

MODOS_MP3 = [
    ("automatica", "Automática — copia MP3 ou converte conforme a origem"),
    ("alta", "Alta — MP3 CBR 320 kbps"),
    ("personalizada", "Personalizada — escolher o bitrate"),
]


class Cartao(QFrame):
    """Cartão de seção com título."""

    def __init__(self, titulo: str, pai: Optional[QWidget] = None) -> None:
        super().__init__(pai)
        self.setObjectName("cartao")
        self.layout_ = QVBoxLayout(self)
        self.layout_.setContentsMargins(16, 14, 16, 14)
        self.layout_.setSpacing(9)
        rotulo = QLabel(titulo.upper())
        rotulo.setObjectName("rotulo")
        self.layout_.addWidget(rotulo)

    def adicionar(self, widget: QWidget) -> QWidget:
        self.layout_.addWidget(widget)
        return widget

    def adicionar_linha(self, *widgets: QWidget) -> QHBoxLayout:
        linha = QHBoxLayout()
        linha.setSpacing(9)
        for w in widgets:
            linha.addWidget(w)
        linha.addStretch(1)
        self.layout_.addLayout(linha)
        return linha


class SettingsPage(QWidget):
    config_alterada = Signal()
    ferramentas_verificadas = Signal(object)
    mensagem = Signal(str)

    def __init__(self, config: Config, pai: Optional[QWidget] = None) -> None:
        super().__init__(pai)
        self.config = config
        self.status_cookies = cookies_mod.verificar(self.config.caminho_cookies)
        self.status_ferr: Dict[str, object] = {}
        self._verificando_ferramentas = False

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(26, 22, 26, 12)
        raiz.setSpacing(12)

        topo = QHBoxLayout()
        col = QVBoxLayout()
        col.setSpacing(2)
        t = QLabel("Configurações")
        t.setObjectName("titulo")
        st = QLabel("Tudo fica salvo em config.json, ao lado do main.py.")
        st.setObjectName("subtitulo")
        col.addWidget(t)
        col.addWidget(st)
        topo.addLayout(col, 1)
        self.btn_restaurar = QPushButton("Restaurar padrões")
        self.btn_restaurar.setObjectName("fantasma")
        self.btn_restaurar.clicked.connect(self._restaurar)
        self.btn_restaurar.hide()
        self.btn_salvar = QPushButton("Salvar configurações")
        self.btn_salvar.setObjectName("primario")
        self.btn_salvar.clicked.connect(self.salvar)
        topo.addWidget(self.btn_salvar, 0, Qt.AlignBottom)
        raiz.addLayout(topo)

        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        dentro = QWidget()
        self.col = QVBoxLayout(dentro)
        self.col.setContentsMargins(0, 0, 6, 12)
        self.col.setSpacing(11)
        area.setWidget(dentro)
        raiz.addWidget(area, 1)

        # Só as opções essenciais são exibidas. Controles antigos são mantidos
        # ocultos para preservar preferências existentes ao salvar.
        self._cartao_saida()
        self._cartao_verificar_baixados()
        self._cartao_cookies()
        self._cartao_ia()
        self._cartao_ferramentas()
        self._cartao_fontes_capas_visivel()
        inicio_avancado = self.col.count()
        self._cartao_download()
        self._cartao_metadados()
        self._cartao_pesquisa()
        self._cartao_fontes()
        self._avancadas = [self.col.itemAt(i).widget() for i in range(inicio_avancado, self.col.count())]
        for widget in self._avancadas:
            if widget is not None:
                widget.hide()
        self.saida_extra.hide()
        self.col.addStretch(1)

        self._atualizar_cookies()
        self._verificar_ferramentas()

    def _cartao_verificar_baixados(self) -> None:
        c = Cartao("Músicas já baixadas")
        self.col.addWidget(c)
        texto = QLabel("A pesquisa verifica automaticamente a pasta de saída e suas subpastas. "
                       "Opcionalmente, escolha outra pasta para verificar também.")
        texto.setWordWrap(True)
        c.layout_.addWidget(texto)
        linha = QHBoxLayout()
        self.campo_pasta_baixados = QLineEdit(str(self.config.get("pasta_verificar_baixados") or ""))
        self.campo_pasta_baixados.setReadOnly(True)
        self.campo_pasta_baixados.setPlaceholderText("Nenhuma pasta adicional")
        linha.addWidget(self.campo_pasta_baixados, 1)
        btn = QPushButton("Escolher pasta")
        btn.clicked.connect(self._escolher_pasta_baixados)
        linha.addWidget(btn)
        limpar = QPushButton("Limpar")
        limpar.clicked.connect(self.campo_pasta_baixados.clear)
        linha.addWidget(limpar)
        c.layout_.addLayout(linha)
        dica = QLabel("As pastas escolhidas são lidas localmente; os arquivos existentes não são alterados.")
        dica.setWordWrap(True)
        c.layout_.addWidget(dica)

    def _escolher_pasta_baixados(self) -> None:
        pasta = QFileDialog.getExistingDirectory(self, "Pasta adicional para verificar MP3s",
                                                 self.campo_pasta_baixados.text() or str(Path.home()))
        if pasta:
            self.campo_pasta_baixados.setText(pasta)

    def _cartao_fontes_capas_visivel(self) -> None:
        c = Cartao("Capas escolhidas no Google")
        self.col.addWidget(c)
        texto = QLabel("O RiffLab não consulta mais APIs de capas. Pesquise no Google e escolha "
                       "uma imagem ou cole a imagem copiada. A pasta Download de Capas fica na raiz do programa.")
        texto.setWordWrap(True)
        c.layout_.addWidget(texto)
        self.fontes_capas_visiveis = {}  # conserva as preferências antigas sem usá-las

    # ============================================================== cookies
    def _cartao_cookies(self) -> None:
        c = Cartao("cookies.txt")
        self.col.addWidget(c)

        linha = QHBoxLayout()
        self.chip_cookies = Chip("verificando…", PALETA["texto_dim"])
        linha.addWidget(self.chip_cookies)
        self.lbl_cookies = QLabel()
        self.lbl_cookies.setWordWrap(True)
        self.lbl_cookies.setStyleSheet(f"color: {PALETA['texto_dim']};")
        linha.addWidget(self.lbl_cookies, 1)
        c.layout_.addLayout(linha)

        self.lbl_cookies_detalhe = QLabel()
        self.lbl_cookies_detalhe.setObjectName("fraco")
        self.lbl_cookies_detalhe.setStyleSheet(f"color: {PALETA['texto_fraco']}; font-size: 11px;")
        self.lbl_cookies_detalhe.setWordWrap(True)
        c.layout_.addWidget(self.lbl_cookies_detalhe)

        botoes = QHBoxLayout()
        self.btn_escolher_cookies = QPushButton("Escolher cookies.txt")
        self.btn_escolher_cookies.setObjectName("fantasma")
        self.btn_escolher_cookies.clicked.connect(self._escolher_cookies)
        botoes.addWidget(self.btn_escolher_cookies)
        self.btn_testar_cookies = QPushButton("Testar sessão no YouTube")
        self.btn_testar_cookies.setObjectName("fantasma")
        self.btn_testar_cookies.clicked.connect(self._testar_cookies_youtube)
        botoes.addWidget(self.btn_testar_cookies)
        self.btn_rever_cookies = QPushButton("Verificar novamente")
        self.btn_rever_cookies.setObjectName("fantasma")
        self.btn_rever_cookies.clicked.connect(self._atualizar_cookies)
        botoes.addWidget(self.btn_rever_cookies)
        self.btn_pasta_cookies = QPushButton("Abrir pasta do aplicativo")
        self.btn_pasta_cookies.setObjectName("fantasma")
        self.btn_pasta_cookies.clicked.connect(lambda: self._abrir_pasta(RAIZ))
        botoes.addWidget(self.btn_pasta_cookies)
        botoes.addStretch(1)
        c.layout_.addLayout(botoes)

        self.lbl_teste_cookies = QLabel("O estado acima verifica apenas o formato do arquivo; não confirma o login.")
        self.lbl_teste_cookies.setTextFormat(Qt.PlainText)
        self.lbl_teste_cookies.setWordWrap(True)
        c.layout_.addWidget(self.lbl_teste_cookies)
        dica = QLabel("O teste de sessão consulta até um item da sua lista pessoal Assistir mais tarde, "
                      "sem mostrar títulos nem baixar vídeos. Se ela estiver vazia, o resultado pode ser inconclusivo. "
                      "Ele envia uma cópia temporária dos cookies ao YouTube e não altera o arquivo original.")
        dica.setWordWrap(True)
        dica.setStyleSheet(f"color: {PALETA['texto_fraco']}; font-size: 11px;")
        c.layout_.addWidget(dica)

        aviso = QLabel("Segurança — o conteúdo do cookies.txt é tratado como informação sensível: "
                       "não aparece na interface e não deve ser compartilhado. "
                       "O yt-dlp pode usá-lo ao acessar os serviços de origem, inclusive na pesquisa.")
        aviso.setWordWrap(True)
        aviso.setStyleSheet(f"color: {PALETA['texto_fraco']}; font-size: 11px;")
        c.layout_.addWidget(aviso)

    def _escolher_cookies(self) -> None:
        caminho, _ = QFileDialog.getOpenFileName(
            self, "Escolher arquivo de cookies", str(self.config.caminho_cookies.parent),
            "Arquivos de texto (*.txt);;Todos os arquivos (*)")
        if not caminho:
            return
        # Guarda somente o caminho; não copia o conteúdo para o projeto.
        self.config.update(caminho_cookies=caminho, usar_cookies=True)
        self._atualizar_cookies()
        self.lbl_teste_cookies.setText("Arquivo alterado: faça novamente o teste de sessão.")
        self.config_alterada.emit()
        self.mensagem.emit("Arquivo de cookies selecionado.")

    def _atualizar_cookies(self) -> None:
        st = cookies_mod.verificar(self.config.caminho_cookies)
        self.status_cookies = st
        cores = {"pronto": PALETA["lima"], "ausente": PALETA["amarelo"],
                 "vazio": PALETA["laranja"], "formato inválido": PALETA["vermelho"],
                 "sem permissão de leitura": PALETA["vermelho"]}
        cor = cores.get(st.estado, PALETA["texto_dim"])
        self.chip_cookies.setText(st.estado)
        self.chip_cookies.setStyleSheet(
            f"color: {cor}; background: {alfa(cor, '1A')}; border: 1px solid {alfa(cor, '55')};"
            f"border-radius: 8px; padding: 2px 9px; font-size: 11px; font-weight: 700;")
        self.lbl_cookies.setText(st.mensagem)
        self.lbl_cookies_detalhe.setText(
            f"Caminho: {st.caminho}   ·   {st.tamanho} bytes   ·   "
            f"{st.cookies_validos} cookie(s) em {st.dominios} domínio(s)   ·   "
            f"modificado em {st.modificado_texto()}")

    def _testar_cookies_youtube(self) -> None:
        from ...teste_cookies_youtube import testar
        caminho = str(self.config.caminho_cookies)
        self.btn_testar_cookies.setEnabled(False)
        self.lbl_teste_cookies.setText("Consultando o YouTube… isso pode levar até 90 segundos.")

        def pronto(resultado):
            self.btn_testar_cookies.setEnabled(True)
            if str(self.config.caminho_cookies) != caminho:
                self.lbl_teste_cookies.setText("O arquivo selecionado mudou. Faça novamente o teste.")
                return
            mensagem = resultado['mensagem']
            if not self.config.get('usar_cookies'):
                mensagem += ' Atenção: o uso de cookies está desativado nos downloads.'
            self.lbl_teste_cookies.setText(mensagem)

        def falhou(_msg):
            self.btn_testar_cookies.setEnabled(True)
            self.lbl_teste_cookies.setText("Não foi possível concluir o teste de sessão.")

        EXECUTOR_GLOBAL.rodar(testar, caminho, ao_resultado=pronto, ao_erro=falhou)

    # ===================================================== identificação com IA
    def _cartao_ia(self) -> None:
        c = Cartao("Identificação com IA (Groq)")
        self.col.addWidget(c)

        self.chk_ia = QCheckBox("Identificar cada música com IA antes de definir capa e metadados")
        self.chk_ia.setChecked(bool(self.config.get("ia_ativa")))
        self.chk_ia.setToolTip(
            "A IA recebe apenas: título do vídeo, canal, URL, duração e sugestões da busca.\n"
            "Cookies, credenciais do YouTube e arquivos NUNCA são enviados.")
        c.layout_.addWidget(self.chk_ia)

        linha = QHBoxLayout()
        rot = QLabel("Chave da API")
        rot.setStyleSheet("font-weight: 600;")
        linha.addWidget(rot)
        self.campo_chave = QLineEdit()
        self.campo_chave.setEchoMode(QLineEdit.Password)
        self.campo_chave.setPlaceholderText(
            "cole a chave da Groq — ou escreva no api.txt da raiz do projeto")
        linha.addWidget(self.campo_chave, 1)
        self.btn_salvar_chave = QPushButton("Salvar chave")
        self.btn_salvar_chave.setObjectName("fantasma")
        self.btn_salvar_chave.clicked.connect(self._salvar_chave)
        linha.addWidget(self.btn_salvar_chave)
        self.btn_apagar_chave = QPushButton("Apagar")
        self.btn_apagar_chave.setObjectName("fantasma")
        self.btn_apagar_chave.clicked.connect(self._apagar_chave)
        linha.addWidget(self.btn_apagar_chave)
        c.layout_.addLayout(linha)

        linha_api = QHBoxLayout()
        self.btn_api_txt = QPushButton("Criar/abrir api.txt")
        self.btn_api_txt.setObjectName("fantasma")
        self.btn_api_txt.setToolTip(
            "Cria (se não existir) o arquivo api.txt na pasta do app e abre no\n"
            "editor de texto. Depois de colar a chave e salvar, o app lê sozinho.")
        self.btn_api_txt.clicked.connect(self._abrir_api_txt)
        linha_api.addWidget(self.btn_api_txt)
        self.lbl_chave_onde = QLabel(seguranca.caminho_legivel())
        self.lbl_chave_onde.setWordWrap(True)
        self.lbl_chave_onde.setStyleSheet(f"color: {PALETA['texto_fraco']}; font-size: 11px;")
        linha_api.addWidget(self.lbl_chave_onde, 1)
        c.layout_.addLayout(linha_api)

        linha2 = QHBoxLayout()
        rot2 = QLabel("Modelo")
        rot2.setStyleSheet("font-weight: 600;")
        linha2.addWidget(rot2)
        self.combo_modelo_ia = QComboBox()
        self.combo_modelo_ia.setEditable(True)
        self.combo_modelo_ia.addItem(str(self.config.get("ia_modelo") or cliente_groq.MODELO_PADRAO))
        self.combo_modelo_ia.setMinimumWidth(260)
        linha2.addWidget(self.combo_modelo_ia)
        self.btn_testar_ia = QPushButton("Testar conexão")
        self.btn_testar_ia.setObjectName("fantasma")
        self.btn_testar_ia.clicked.connect(self._testar_ia)
        linha2.addWidget(self.btn_testar_ia)
        self.chip_ia = Chip("-", PALETA["texto_dim"])
        linha2.addWidget(self.chip_ia)
        linha2.addStretch(1)
        c.layout_.addLayout(linha2)

        self.lbl_ia = QLabel("-")
        self.lbl_ia.setWordWrap(True)
        self.lbl_ia.setStyleSheet(f"color: {PALETA['texto_fraco']}; font-size: 11px;")
        c.layout_.addWidget(self.lbl_ia)

        nota = QLabel("Privacidade — vão para a Groq apenas título do vídeo, canal, URL, "
                      "duração e o termo pesquisado. Cookies, credenciais do YouTube e "
                      "qualquer arquivo do seu computador ficam de fora. A chave é "
                      "guardada fora do config.json e nunca aparece na tela nem no log. "
                      "Modo mais simples: crie o arquivo api.txt nesta pasta com a chave "
                      "dentro (só a chave, uma linha) — o app lê automaticamente.")
        nota.setWordWrap(True)
        nota.setStyleSheet(f"color: {PALETA['texto_fraco']}; font-size: 11px;")
        c.layout_.addWidget(nota)

        self._atualizar_ia()

    def _atualizar_ia(self) -> None:
        if hasattr(self, "lbl_chave_onde"):
            self.lbl_chave_onde.setText(seguranca.caminho_legivel())
        origem = seguranca.origem()
        if origem:
            self.chip_ia.setText("chave ok")
            self.chip_ia.setStyleSheet(
                f"color: {PALETA['lima']}; background: {alfa(PALETA['lima'], '1A')};"
                f"border: 1px solid {alfa(PALETA['lima'], '55')}; border-radius: 8px;"
                f"padding: 2px 9px; font-size: 11px; font-weight: 700;")
            self.lbl_ia.setText(
                f"Chave configurada ({seguranca.mascarar()}) — origem: {origem}. "
                f"A identificação está {'ligada' if self.config.get('ia_ativa') else 'desligada'}.")
        else:
            self.chip_ia.setText("sem chave")
            self.chip_ia.setStyleSheet(
                f"color: {PALETA['amarelo']}; background: {alfa(PALETA['amarelo'], '1A')};"
                f"border: 1px solid {alfa(PALETA['amarelo'], '55')}; border-radius: 8px;"
                f"padding: 2px 9px; font-size: 11px; font-weight: 700;")
            self.lbl_ia.setText(
                "Nenhuma chave configurada. Sem ela o app continua funcionando com "
                "iTunes + MusicBrainz, mas sem a identificação por IA. "
                "Cole a chave acima ou crie api.txt na pasta do app.")

    def _salvar_chave(self) -> None:
        chave = self.campo_chave.text().strip()
        if not chave:
            self.mensagem.emit("Cole a chave antes de salvar.")
            return
        ok, msg = seguranca.guardar(chave)
        self.campo_chave.clear()
        self.mensagem.emit(("Chave salva: " if ok else "") + msg)
        self._atualizar_ia()

    def _apagar_chave(self) -> None:
        seguranca.apagar()
        self.campo_chave.clear()
        self.mensagem.emit("Chave apagada do disco (api.txt e credenciais/groq.dat).")
        self._atualizar_ia()

    def _abrir_api_txt(self) -> None:
        """Cria o api.txt (se preciso) e abre no editor padrão do sistema."""
        caminho = seguranca.ARQ_API
        try:
            if not caminho.is_file():
                caminho.write_text(
                    seguranca.CABECALHO_API
                    + "# Cole a chave da Groq na linha abaixo (so a chave) e salve.\n"
                    + "# Ex.: gsk_xxxxxxxxxxxxxxxxxxxxxxxxxxxx\n"
                    + "\n", encoding="utf-8", newline="\n")
                self.mensagem.emit(f"{caminho.name} criado — cole a chave e salve.")
            else:
                self.mensagem.emit(f"Abrindo {caminho.name}…")
        except OSError as exc:
            self.mensagem.emit(f"Não foi possível criar {caminho.name}: {exc}")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(caminho)))
        self._atualizar_ia()

    def _testar_ia(self) -> None:
        self.btn_testar_ia.setEnabled(False)
        self.btn_testar_ia.setText("testando…")

        def tarefa():
            return cliente_groq.testar(self.config)

        def pronto(res: dict) -> None:
            self.btn_testar_ia.setEnabled(True)
            self.btn_testar_ia.setText("Testar conexão")
            modelos = res.get("modelos") or []
            if modelos:
                atual = self.combo_modelo_ia.currentText().strip()
                self.combo_modelo_ia.blockSignals(True)
                self.combo_modelo_ia.clear()
                self.combo_modelo_ia.addItems(modelos)
                if atual and atual not in modelos:
                    self.combo_modelo_ia.addItem(atual)
                self.combo_modelo_ia.setCurrentText(atual or modelos[0])
                self.combo_modelo_ia.blockSignals(False)
            self.lbl_ia.setText(str(res.get("mensagem") or ""))
            self.mensagem.emit(str(res.get("mensagem") or "")[:150])

        def falhou(msg: str) -> None:
            self.btn_testar_ia.setEnabled(True)
            self.btn_testar_ia.setText("Testar conexão")
            self.lbl_ia.setText(f"Falha no teste: {msg}")
            self.mensagem.emit(f"Falha no teste da API: {msg[:120]}")

        EXECUTOR_GLOBAL.rodar(tarefa, ao_resultado=pronto, ao_erro=falhou)

    # =========================================================== ferramentas
    def _cartao_ferramentas(self) -> None:
        c = Cartao("Ferramentas externas")
        self.col.addWidget(c)
        grade = QGridLayout()
        grade.setHorizontalSpacing(12)
        grade.setVerticalSpacing(7)
        self.chips_ferr: Dict[str, QLabel] = {}
        self.lbl_ferr: Dict[str, QLabel] = {}
        for i, (chave, nome) in enumerate([("ffmpeg", "FFmpeg"), ("ffprobe", "FFprobe"),
                                           ("yt-dlp", "yt-dlp"), ("deno", "Deno")]):
            rotulo = QLabel(nome)
            rotulo.setStyleSheet("font-weight: 700;")
            grade.addWidget(rotulo, i, 0)
            chip = Chip("-", PALETA["texto_dim"])
            self.chips_ferr[chave] = chip
            grade.addWidget(chip, i, 1, Qt.AlignLeft)
            det = QLabel("-")
            det.setStyleSheet(f"color: {PALETA['texto_fraco']}; font-size: 11px;")
            det.setWordWrap(True)
            self.lbl_ferr[chave] = det
            grade.addWidget(det, i, 2)
        grade.setColumnStretch(2, 1)
        c.layout_.addLayout(grade)

        nota = QLabel("Coloque ffmpeg.exe / yt-dlp.exe / deno.exe na pasta “ferramentas” (ou no PATH). "
                      "O ffprobe é opcional: sem ele o app mede a qualidade pelo próprio ffmpeg.")
        nota.setWordWrap(True)
        nota.setStyleSheet(f"color: {PALETA['texto_fraco']}; font-size: 11px;")
        c.layout_.addWidget(nota)

        linha = QHBoxLayout()
        btn = QPushButton("Procurar novamente")
        btn.setObjectName("fantasma")
        btn.clicked.connect(self._verificar_ferramentas)
        linha.addWidget(btn)

        self.btn_atualizar_yt = QPushButton("Atualizar yt-dlp")
        self.btn_atualizar_yt.setObjectName("fantasma")
        self.btn_atualizar_yt.setToolTip(
            "Roda 'yt-dlp -U' para baixar a versão mais recente.\n"
            "Vale a pena a cada poucas semanas: as plataformas mudam.")
        self.btn_atualizar_yt.clicked.connect(self._atualizar_ytdlp)
        linha.addWidget(self.btn_atualizar_yt)
        linha.addStretch(1)
        c.layout_.addLayout(linha)

    def _atualizar_ytdlp(self) -> None:
        from ...config import CRIAR_SEM_JANELA
        from ...tools import ytdlp
        from ...workers import EXECUTOR_GLOBAL
        f = ytdlp()
        if not f.ok:
            self.mensagem.emit("yt-dlp.exe não encontrado — baixe e coloque em ferramentas/.")
            return
        self.btn_atualizar_yt.setEnabled(False)
        self.btn_atualizar_yt.setText("atualizando…")

        def tarefa():
            p = subprocess.run([f.caminho, "-U"], capture_output=True, text=True,
                               creationflags=CRIAR_SEM_JANELA, encoding="utf-8",
                               errors="replace", timeout=180)
            saida = (p.stdout or "") + (p.stderr or "")
            if p.returncode != 0:
                raise RuntimeError(f'yt-dlp -U falhou (código {p.returncode}): {saida[-300:]}')
            return saida

        EXECUTOR_GLOBAL.rodar(tarefa, ao_resultado=self._fim_atualizacao,
                              ao_erro=self._erro_atualizacao)

    def _fim_atualizacao(self, saida: str) -> None:
        self.btn_atualizar_yt.setEnabled(True)
        self.btn_atualizar_yt.setText("Atualizar yt-dlp")
        linhas = [l.strip() for l in str(saida or "").splitlines() if l.strip()]
        self.mensagem.emit((linhas[-1] if linhas else "yt-dlp já está atualizado.")[:150])
        self._verificar_ferramentas()

    def _erro_atualizacao(self, msg: str) -> None:
        self.btn_atualizar_yt.setEnabled(True)
        self.btn_atualizar_yt.setText("Atualizar yt-dlp")
        self.mensagem.emit(f"Não foi possível atualizar o yt-dlp: {msg[:120]}")

    def _verificar_ferramentas(self) -> None:
        if self._verificando_ferramentas:
            return
        self._verificando_ferramentas = True
        for chave, chip in self.chips_ferr.items():
            chip.setText("verificando…")
        EXECUTOR_GLOBAL.rodar(status_ferramentas, True, ao_resultado=self._mostrar_ferramentas,
                              ao_erro=self._erro_verificar_ferramentas)

    def _erro_verificar_ferramentas(self, mensagem: str) -> None:
        self._verificando_ferramentas = False
        for chip in self.chips_ferr.values():
            chip.setText('erro na verificação')
        self.mensagem.emit(f'Falha ao verificar ferramentas: {mensagem[:150]}')

    def _mostrar_ferramentas(self, dados) -> None:
        self._verificando_ferramentas = False
        self.status_ferr = dados
        for chave, ferramenta in dados.items():
            chip = self.chips_ferr.get(chave)
            if not chip:
                continue
            if ferramenta.ok:
                chip.setText("ok")
                chip.setStyleSheet(f"color: {PALETA['lima']}; background: {alfa(PALETA['lima'], '1A')};"
                                   f"border: 1px solid {alfa(PALETA['lima'], '55')}; border-radius: 8px;"
                                   f"padding: 2px 9px; font-size: 11px; font-weight: 700;")
                self.lbl_ferr[chave].setText(f"{ferramenta.versao}  ·  {ferramenta.caminho}")
            else:
                chip.setText("indisponível")
                chip.setStyleSheet(f"color: {PALETA['amarelo']}; background: {alfa(PALETA['amarelo'], '1A')};"
                                   f"border: 1px solid {alfa(PALETA['amarelo'], '55')}; border-radius: 8px;"
                                   f"padding: 2px 9px; font-size: 11px; font-weight: 700;")
                self.lbl_ferr[chave].setText(ferramenta.erro or "coloque o executável em ferramentas/")
        self.ferramentas_verificadas.emit(dados)

    # ================================================================ saída
    def _cartao_saida(self) -> None:
        c = Cartao("Áudio e destino")
        self.col.addWidget(c)

        linha = QHBoxLayout()
        self.campo_saida = QLineEdit(str(self.config.pasta_saida))
        self.campo_saida.setReadOnly(True)
        linha.addWidget(self.campo_saida, 1)
        btn = QPushButton("Escolher pasta")
        btn.setObjectName("fantasma")
        btn.clicked.connect(self._escolher_saida)
        linha.addWidget(btn)
        c.layout_.addLayout(linha)
        self.aviso_pasta_saida = QLabel()
        self.aviso_pasta_saida.setWordWrap(True)
        self.aviso_pasta_saida.setStyleSheet(f"color: {PALETA['amarelo']}; font-size: 12px;")
        c.layout_.addWidget(self.aviso_pasta_saida)
        self._atualizar_aviso_pasta_saida()

        self.saida_extra = QWidget()
        extra_layout = QVBoxLayout(self.saida_extra)
        extra_layout.setContentsMargins(0, 0, 0, 0)
        c.layout_.addWidget(self.saida_extra)
        linha2 = QHBoxLayout()
        linha2.setSpacing(10)
        rot = QLabel("Organização")
        rot.setStyleSheet("font-weight: 600;")
        linha2.addWidget(rot)
        self.combo_modelo = QComboBox()
        for valor, texto in MODELOS_ORGANIZACAO:
            self.combo_modelo.addItem(texto, valor)
        atual = str(self.config.get("template_organizacao"))
        idx = max(0, self.combo_modelo.findData(atual))
        self.combo_modelo.setCurrentIndex(idx)
        self.combo_modelo.setMinimumWidth(340)
        linha2.addWidget(self.combo_modelo, 1)
        extra_layout.addLayout(linha2)

        linha3 = QHBoxLayout()
        rot2 = QLabel("Qualidade MP3")
        rot2.setStyleSheet("font-weight: 600;")
        linha3.addWidget(rot2)
        self.combo_modo = QComboBox()
        for valor, texto in MODOS_MP3:
            self.combo_modo.addItem(texto, valor)
        self.combo_modo.setCurrentIndex(max(0, self.combo_modo.findData(
            str(self.config.get("qualidade_mp3") or "automatica"))))
        self.combo_modo.setMinimumWidth(420)
        self.combo_modo.currentIndexChanged.connect(self._modo_mudou)
        linha3.addWidget(self.combo_modo, 1)

        self.spin_bitrate = QSpinBox()
        self.spin_bitrate.setRange(128, 320)
        self.spin_bitrate.setSingleStep(32)
        self.spin_bitrate.setValue(int(self.config.get("mp3_bitrate") or 256))
        self.spin_bitrate.setSuffix(" kbps")
        self.spin_bitrate.setFixedWidth(120)
        self.spin_bitrate.setToolTip("Usado apenas no modo Personalizada")
        linha3.addWidget(self.spin_bitrate)
        extra_layout.addLayout(linha3)
        self._modo_mudou()

        self.chk_sobrescrever = QCheckBox("Sobrescrever arquivos existentes (padrão: não)")
        self.chk_sobrescrever.setChecked(bool(self.config.get("sobrescrever")))
        extra_layout.addWidget(self.chk_sobrescrever)

    def _modo_mudou(self, *_args) -> None:
        personalizado = self.combo_modo.currentData() == "personalizada"
        self.spin_bitrate.setEnabled(personalizado)
        self.spin_bitrate.setVisible(personalizado)

    def _atualizar_aviso_pasta_saida(self) -> None:
        try:
            disponivel = Path(self.campo_saida.text()).is_dir()
        except (OSError, ValueError):
            disponivel = False
        texto = ("Pasta não encontrada ou indisponível. Conecte a unidade ou escolha "
                 "outra pasta e salve. Antes do download verificaremos a permissão de escrita.")
        self.aviso_pasta_saida.setText("" if disponivel else texto)
        self.aviso_pasta_saida.setVisible(not disponivel)

    def _escolher_saida(self) -> None:
        atual = Path(self.campo_saida.text())
        try:
            inicial = str(atual if atual.is_dir() else Path.home())
        except (OSError, ValueError):
            inicial = str(Path.home())
        pasta = QFileDialog.getExistingDirectory(self, "Pasta de saída", inicial)
        if pasta:
            self.campo_saida.setText(pasta)
            self._atualizar_aviso_pasta_saida()

    # ============================================================== download
    def _cartao_download(self) -> None:
        c = Cartao("Download")
        self.col.addWidget(c)

        linha = QHBoxLayout()
        rot = QLabel("Downloads simultâneos")
        rot.setStyleSheet("font-weight: 600;")
        linha.addWidget(rot)
        self.spin_simultaneos = QSpinBox()
        self.spin_simultaneos.setRange(1, 4)
        self.spin_simultaneos.setValue(int(self.config.get("downloads_simultaneos") or 2))
        self.spin_simultaneos.setFixedWidth(80)
        self.spin_simultaneos.setToolTip(
            "Quantas músicas processar ao mesmo tempo.\n"
            "2 é o equilíbrio recomendado; acima de 4 a plataforma começa a "
            "responder 429 / verificação de robô.")
        linha.addWidget(self.spin_simultaneos)
        dica = QLabel("2 é o recomendado — acima de 4 a plataforma bloqueia.")
        dica.setStyleSheet(f"color: {PALETA['texto_fraco']}; font-size: 11px;")
        linha.addWidget(dica, 1)
        c.layout_.addLayout(linha)

        self.chk_temp = QCheckBox("Manter arquivos temporários (para diagnóstico)")
        self.chk_temp.setChecked(bool(self.config.get("manter_temporarios")))
        self.chk_temp.setToolTip("Normal: a pasta temp/ é apagada assim que o MP3 fica pronto.")
        c.layout_.addWidget(self.chk_temp)

    # ============================================================ metadados
    def _cartao_metadados(self) -> None:
        c = Cartao("Capa e metadados automáticos")
        self.col.addWidget(c)

        linha = QHBoxLayout()
        linha.setSpacing(16)
        rot = QLabel("Fontes de capa")
        rot.setStyleSheet("font-weight: 600;")
        linha.addWidget(rot)
        self.chk_fontes_capa: Dict[str, QCheckBox] = {}
        ativas = set(self.config.get("fontes_capa") or [])
        for chave, nome in [("coverartarchive", "Cover Art Archive"),
                            ("itunes", "Apple Music / iTunes"),
                            ("deezer", "Deezer (API pública)"),
                            ("discogs", "Discogs (precisa de token)")]:
            chk = QCheckBox(nome)
            chk.setChecked(chave in ativas)
            self.chk_fontes_capa[chave] = chk
            linha.addWidget(chk)
        linha.addStretch(1)
        c.layout_.addLayout(linha)

        dica_ordem = QLabel(
            "A busca automática usa candidatos que o catálogo indica como singles. "
            "Quando não encontra, não substitui pela capa do álbum; confira a imagem.")
        dica_ordem.setWordWrap(True)
        dica_ordem.setStyleSheet(f"color: {PALETA['texto_fraco']}; font-size: 11px;")
        c.layout_.addWidget(dica_ordem)

        linha2 = QHBoxLayout()
        rot2 = QLabel("Tamanho mínimo da capa")
        rot2.setStyleSheet("font-weight: 600;")
        linha2.addWidget(rot2)
        self.spin_capa = QSpinBox()
        self.spin_capa.setRange(100, 3000)
        self.spin_capa.setSingleStep(50)
        self.spin_capa.setValue(int(self.config.get("tamanho_minimo_capa") or 300))
        self.spin_capa.setSuffix(" px")
        linha2.addWidget(self.spin_capa)
        linha2.addStretch(1)
        c.layout_.addLayout(linha2)

        linha3 = QHBoxLayout()
        linha3.setSpacing(18)
        self.chk_baixar_capa = QCheckBox("Baixar capa automaticamente")
        self.chk_baixar_capa.setChecked(bool(self.config.get("baixar_capa", True)))
        linha3.addWidget(self.chk_baixar_capa)
        self.chk_incorporar_capa = QCheckBox("Incorporar a capa no MP3 (ID3/APIC)")
        self.chk_incorporar_capa.setChecked(bool(self.config.get("incorporar_capa", True)))
        linha3.addWidget(self.chk_incorporar_capa)
        linha3.addStretch(1)
        c.layout_.addLayout(linha3)

        self.chk_thumb_capa = QCheckBox(
            "Miniatura do vídeo como capa: indisponível nesta versão")
        self.chk_thumb_capa.setChecked(False)
        self.chk_thumb_capa.setEnabled(False)
        self.chk_thumb_capa.setToolTip(
            "A busca automática não usa miniaturas como substitutas de capas de single.")
        c.layout_.addWidget(self.chk_thumb_capa)

        self.chk_tags = QCheckBox("Gravar título, artista, álbum, ano, faixa, gênero e capa (ID3/APIC)")
        self.chk_tags.setChecked(bool(self.config.get("gravar_tags")))
        c.layout_.addWidget(self.chk_tags)

        self.chk_id3v1 = QCheckBox("Também gravar ID3v1 (compatibilidade com players antigos)")
        self.chk_id3v1.setChecked(bool(self.config.get("gravar_id3v1")))
        c.layout_.addWidget(self.chk_id3v1)

    # ==================================================== pesquisa (v0.5.0)
    def _cartao_pesquisa(self) -> None:
        c = Cartao("Pesquisa, shows e prévia")
        self.col.addWidget(c)

        self.chk_evitar_ao_vivo = QCheckBox(
            "Ocultar resultados de shows / gravações ao vivo (recomendado)")
        self.chk_evitar_ao_vivo.setChecked(bool(self.config.get("evitar_ao_vivo", True)))
        self.chk_evitar_ao_vivo.setToolTip(
            "Prioriza estúdio > clipe oficial > oficial com áudio de estúdio.\n"
            "Nada é descartado: os resultados ficam em “Mostrar resultados filtrados”.")
        c.layout_.addWidget(self.chk_evitar_ao_vivo)

        self.chk_confirmar_processar = QCheckBox(
            "Pedir confirmação antes de processar as músicas")
        self.chk_confirmar_processar.setChecked(
            bool(self.config.get("confirmar_antes_processar", True)))
        c.layout_.addWidget(self.chk_confirmar_processar)

        self.chk_confirmar_capa = QCheckBox(
            "Pedir confirmação da capa antes de gravar no MP3")
        self.chk_confirmar_capa.setChecked(bool(self.config.get("confirmar_capa", True)))
        self.chk_confirmar_capa.setToolTip(
            "Você vê a imagem, o álbum, o artista, o ano, a fonte e o grau de "
            "correspondência, e pode trocar ou recusar a capa.")
        c.layout_.addWidget(self.chk_confirmar_capa)

        linha = QHBoxLayout()
        rot = QLabel("Verificar qualidade automaticamente em")
        rot.setStyleSheet("font-weight: 600;")
        linha.addWidget(rot)
        self.spin_verificar = QSpinBox()
        self.spin_verificar.setRange(0, 30)
        self.spin_verificar.setValue(int(self.config.get("verificar_automatico") or 10))
        self.spin_verificar.setSuffix(" resultado(s)")
        self.spin_verificar.setToolTip("0 = só quando você clicar em “Verificar qualidade”")
        linha.addWidget(self.spin_verificar)
        linha.addStretch(1)
        c.layout_.addLayout(linha)

    # =============================================================== fontes
    def _cartao_fontes(self) -> None:
        c = Cartao("Fontes de pesquisa")
        self.col.addWidget(c)

        self.chk_fontes: Dict[str, QCheckBox] = {}
        ativas = set(self.config.get("fontes_ativas") or [])
        for fid, fonte in todas_as_fontes(self.config).items():
            linha = QHBoxLayout()
            chk = QCheckBox(fonte.nome)
            chk.setChecked(fid in ativas)
            self.chk_fontes[fid] = chk
            linha.addWidget(chk)
            desc = QLabel(fonte.descricao)
            desc.setWordWrap(True)
            desc.setStyleSheet(f"color: {PALETA['texto_fraco']}; font-size: 11px;")
            linha.addWidget(desc, 1)
            c.layout_.addLayout(linha)

        self.chk_ytdlp = self.chk_fontes.get("ytdlp")

        nota_padrao = QLabel("O yt-dlp é a fonte padrão do RiffLab. "
                             "As demais são opcionais e podem ficar desmarcadas.")
        nota_padrao.setWordWrap(True)
        nota_padrao.setStyleSheet(f"color: {PALETA['texto_fraco']}; font-size: 11px;")
        c.layout_.addWidget(nota_padrao)

        fonte_yt = todas_as_fontes(self.config).get("ytdlp")
        if fonte_yt is not None and not fonte_yt.disponivel()[0]:
            falta = QLabel(
                "yt-dlp.exe não encontrado — sem ele a pesquisa volta vazia.\n"
                "Baixe em github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe "
                "e coloque dentro da pasta “ferramentas” do RiffLab.")
            falta.setWordWrap(True)
            falta.setStyleSheet(
                f"color: {PALETA['laranja']}; font-size: 11.5px; font-weight: 600;")
            c.layout_.addWidget(falta)
            self.chk_ytdlp.setToolTip("Baixe o yt-dlp.exe para ativar esta fonte")

        aviso = QLabel("⚠ O yt-dlp acessa plataformas de vídeo: use somente com conteúdo que você "
                       "pode baixar (Creative Commons, domínio público ou próprio). Downloads não "
                       "autorizados violam os termos das plataformas e a lei de direitos autorais.")
        aviso.setWordWrap(True)
        aviso.setStyleSheet(f"color: {PALETA['amarelo']}; font-size: 11px;")
        c.layout_.addWidget(aviso)

        linha2 = QHBoxLayout()
        self.campo_biblioteca = QLineEdit(str(self.config.get("biblioteca_local") or ""))
        self.campo_biblioteca.setPlaceholderText("Pasta da sua biblioteca local (opcional)")
        linha2.addWidget(self.campo_biblioteca, 1)
        btn = QPushButton("Escolher")
        btn.setObjectName("fantasma")
        btn.clicked.connect(self._escolher_biblioteca)
        linha2.addWidget(btn)
        c.layout_.addLayout(linha2)

        linha3 = QHBoxLayout()
        rot = QLabel("Máximo de resultados")
        rot.setStyleSheet("font-weight: 600;")
        linha3.addWidget(rot)
        self.spin_limite = QSpinBox()
        self.spin_limite.setRange(5, 100)
        self.spin_limite.setValue(int(self.config.get("limite_resultados") or 20))
        linha3.addWidget(self.spin_limite)
        linha3.addStretch(1)
        c.layout_.addLayout(linha3)

    def _escolher_biblioteca(self) -> None:
        pasta = QFileDialog.getExistingDirectory(self, "Sua biblioteca de músicas",
                                                 self.campo_biblioteca.text() or str(Path.home()))
        if pasta:
            self.campo_biblioteca.setText(pasta)

    # ================================================================ salvar
    def salvar(self) -> None:
        # Não reaplicar controles ocultos: eles podem estar desatualizados em
        # relação às escolhas feitas na página de pesquisa durante a sessão.
        self.config.update(
            pasta_saida=self.campo_saida.text() or str(self.config.pasta_saida),
            pasta_verificar_baixados=self.campo_pasta_baixados.text(),
            fontes_capa=[chave for chave, chk in self.fontes_capas_visiveis.items() if chk.isChecked()]
                        + [chave for chave in (self.config.get("fontes_capa") or [])
                           if chave not in self.fontes_capas_visiveis],
            ia_ativa=self.chk_ia.isChecked(),
            ia_modelo=self.combo_modelo_ia.currentText().strip() or cliente_groq.MODELO_PADRAO,
        )
        self._atualizar_cookies()
        self._atualizar_ia()
        self._atualizar_aviso_pasta_saida()
        self.config_alterada.emit()
        self.mensagem.emit("Configurações salvas.")

    def _restaurar(self) -> None:
        from ...config import PADROES
        for chave, valor in PADROES.items():
            self.config[chave] = valor
        self.config.salvar()
        self.campo_saida.setText(str(self.config.pasta_saida))
        self._atualizar_aviso_pasta_saida()
        self.campo_pasta_baixados.setText(str(self.config.get("pasta_verificar_baixados") or ""))
        self.combo_modelo.setCurrentIndex(max(0, self.combo_modelo.findData(
            self.config.get("template_organizacao"))))
        self.combo_modo.setCurrentIndex(max(0, self.combo_modo.findData(
            self.config.get("qualidade_mp3") or "automatica")))
        self.spin_bitrate.setValue(int(self.config.get("mp3_bitrate") or 256))
        self.spin_simultaneos.setValue(int(self.config.get("downloads_simultaneos") or 2))
        self.chk_temp.setChecked(bool(self.config.get("manter_temporarios")))
        self.chk_ia.setChecked(bool(self.config.get("ia_ativa")))
        self.combo_modelo_ia.setCurrentText(str(self.config.get("ia_modelo") or cliente_groq.MODELO_PADRAO))
        self.chk_thumb_capa.setChecked(False)
        self.chk_evitar_ao_vivo.setChecked(bool(self.config.get("evitar_ao_vivo", True)))
        self.chk_confirmar_processar.setChecked(
            bool(self.config.get("confirmar_antes_processar", True)))
        self.chk_confirmar_capa.setChecked(bool(self.config.get("confirmar_capa", True)))
        self.spin_verificar.setValue(int(self.config.get("verificar_automatico") or 10))
        self.chk_baixar_capa.setChecked(bool(self.config.get("baixar_capa", True)))
        self.chk_incorporar_capa.setChecked(bool(self.config.get("incorporar_capa", True)))
        self._modo_mudou()
        for fid, chk in self.chk_fontes.items():
            chk.setChecked(fid in (self.config.get("fontes_ativas") or []))
        for fid, chk in self.chk_fontes_capa.items():
            chk.setChecked(fid in (self.config.get("fontes_capa") or []))
        for fid, chk in self.fontes_capas_visiveis.items():
            chk.setChecked(fid in (self.config.get("fontes_capa") or []))
        self.chk_tags.setChecked(bool(self.config.get("gravar_tags")))
        self.chk_id3v1.setChecked(bool(self.config.get("gravar_id3v1")))
        self.campo_biblioteca.setText(str(self.config.get("biblioteca_local") or ""))
        self.config_alterada.emit()
        self.mensagem.emit("Padrões restaurados.")

    def _abrir_pasta(self, pasta: Path) -> None:
        try:
            if os.name == "nt":
                os.startfile(str(pasta))                   # noqa: S606
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(pasta)])
            else:
                subprocess.Popen(["xdg-open", str(pasta)])
        except Exception as exc:                           # noqa: BLE001
            self.mensagem.emit(f"Não foi possível abrir a pasta: {exc}")

"""Página de downloads: acompanhamento em tempo real da fila."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QFrame, QHBoxLayout, QLabel,
                               QLineEdit, QMessageBox, QProgressBar, QPushButton, QScrollArea,
                               QVBoxLayout, QWidget)

from ... import estado_musicas
from ...config import Config
from ...downloader import GerenciadorFila
from ...logging_setup import registrar_erro, texto_seguro
from ...models import CoverResult, hhmmss
from ...preparacao import preparar_musica, aplicar_edicao
from ...workers import EXECUTOR_GLOBAL
from ..dialogos import DialogoCapas
from ..theme import PALETA, alfa
from ..widgets.result_card import Chip

CORES_STATUS = {
    "na fila": PALETA["texto_dim"],
    "processando": PALETA["violeta"],
    "baixando": PALETA["ciano"],
    "convertendo": PALETA["amarelo"],
    "metadados": PALETA["azul"],
    "finalizando": PALETA["lima"],
    "finalizado": PALETA["lima"],
    "erro": PALETA["vermelho"],
    "cancelado": PALETA["texto_fraco"],
}


class LinhaJob(QFrame):
    abrir = Signal(str)
    cancelar = Signal(int)
    tentar = Signal(int)

    def __init__(self, job: dict, pai: Optional[QWidget] = None) -> None:
        super().__init__(pai)
        self.job = dict(job)
        self.setObjectName("cartao")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 11, 14, 11)
        lay.setSpacing(7)

        topo = QHBoxLayout()
        topo.setSpacing(8)
        self.titulo = QLabel()
        self.titulo.setStyleSheet("font-size: 14px; font-weight: 700;")
        topo.addWidget(self.titulo, 1)
        self.chip_status = Chip("na fila", PALETA["texto_dim"])
        topo.addWidget(self.chip_status)
        self.chip_qual = Chip("-", PALETA["amarelo"])
        topo.addWidget(self.chip_qual)
        lay.addLayout(topo)

        self.detalhe = QLabel()
        self.detalhe.setStyleSheet(f"color: {PALETA['texto_dim']}; font-size: 11.5px;")
        lay.addWidget(self.detalhe)

        linha = QHBoxLayout()
        linha.setSpacing(9)
        self.barra = QProgressBar()
        self.barra.setRange(0, 100)
        self.barra.setValue(0)
        linha.addWidget(self.barra, 1)

        self.btn_abrir = QPushButton("Abrir")
        self.btn_abrir.setObjectName("fantasma")
        self.btn_abrir.clicked.connect(self._abrir)
        linha.addWidget(self.btn_abrir)

        self.btn_tentar = QPushButton("Tentar novamente")
        self.btn_tentar.setObjectName("fantasma")
        self.btn_tentar.clicked.connect(lambda: self.tentar.emit(int(self.job.get("id", 0))))
        linha.addWidget(self.btn_tentar)

        self.btn_cancelar = QPushButton("Cancelar")
        self.btn_cancelar.setObjectName("fantasma")
        self.btn_cancelar.clicked.connect(lambda: self.cancelar.emit(int(self.job.get("id", 0))))
        linha.addWidget(self.btn_cancelar)
        lay.addLayout(linha)

        self.mensagem = QLabel("aguardando…")
        self.mensagem.setTextFormat(Qt.PlainText)
        self.mensagem.setWordWrap(True)
        self.mensagem.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.mensagem.setStyleSheet(f"color: {PALETA['texto_fraco']}; font-size: 11px;")
        lay.addWidget(self.mensagem)

        self.atualizar(self.job)

    def atualizar(self, job: dict) -> None:
        self.job = dict(job)
        titulo = f"{job.get('artista') or '—'} — {job.get('titulo') or ''}"
        if len(titulo) > 78:
            titulo = titulo[:77] + "…"
        self.titulo.setText(titulo)
        status = str(job.get("status") or "na fila")
        cor = CORES_STATUS.get(status, PALETA["texto_dim"])
        self.chip_status.setText(status)
        self.chip_status.setStyleSheet(
            f"color: {cor}; background: {alfa(cor, '1A')}; border: 1px solid {alfa(cor, '55')};"
            f"border-radius: 8px; padding: 2px 8px; font-size: 11px; font-weight: 700;")
        self.chip_qual.setText(str(job.get("qualidade") or "-"))
        partes = [job.get("fonte", ""), job.get("formato", "")]
        if job.get("video"):
            partes.append(f"vídeo {job['video']}")
        if job.get("identificacao"):
            partes.append(f"IA: {job['identificacao']}")
        if job.get("capa"):
            partes.append(f"capa: {job['capa']}")
        self.detalhe.setText("  ·  ".join(p for p in partes if p))
        self.barra.setValue(int(job.get("progresso") or 0))
        msg = job.get("erro") or job.get("mensagem") or ""
        self.mensagem.setText(texto_seguro(msg) if status == 'erro' else msg)
        self.mensagem.setStyleSheet(
            f"color: {PALETA['vermelho'] if status == 'erro' else PALETA['texto_fraco']}; font-size: 11px;")
        # O gerenciador só pode cancelar itens ainda aguardando na fila.
        self.btn_cancelar.setVisible(status == 'na fila')
        self.btn_cancelar.setToolTip('Cancelar esta música enquanto aguarda na fila')
        self.btn_abrir.setVisible(status == "finalizado" and bool(job.get("caminho")))
        self.btn_tentar.setVisible(status == 'erro' and not job.get('nova_tentativa'))

    def _abrir(self) -> None:
        caminho = self.job.get("caminho") or ""
        if caminho:
            self.abrir.emit(caminho)


class LinhaSelecao(QFrame):
    """Uma música revisável antes de enviar qualquer áudio para download."""
    alterada = Signal()
    remover = Signal(object)
    escolher_capa = Signal(object)
    editar = Signal(object)

    def __init__(self, pedido: dict, pai=None) -> None:
        super().__init__(pai)
        self.pedido = pedido
        self.preparacao = None
        self.setObjectName("cartao")
        layout = QHBoxLayout(self)
        self.check = QCheckBox()
        self.check.setChecked(True)
        self.check.toggled.connect(lambda _marcado: self.alterada.emit())
        layout.addWidget(self.check)
        textos = QVBoxLayout()
        r = pedido['resultado']
        self.nome = QLabel(f"{r.artista or 'Artista desconhecido'} — {r.titulo}")
        self.nome.setTextFormat(Qt.PlainText)
        self.nome.setWordWrap(True)
        self.nome.setStyleSheet('font-weight: 700;')
        textos.addWidget(self.nome)
        fmt = pedido.get('formato')
        audio = 'Melhor áudio disponível' if not fmt or fmt.format_id == 'bestaudio' else fmt.descricao_curta()
        self.detalhes = QLabel(f'{audio} · capa ainda não escolhida')
        self.detalhes.setWordWrap(True)
        self.detalhes.setObjectName('dim')
        textos.addWidget(self.detalhes)
        layout.addLayout(textos, 1)
        self.btn_editar = QPushButton('Editar dados')
        self.btn_editar.setObjectName('fantasma')
        self.btn_editar.clicked.connect(lambda: self.editar.emit(self))
        layout.addWidget(self.btn_editar)
        self.btn_capa = QPushButton('Escolher capa')
        self.btn_capa.setObjectName('fantasma')
        self.btn_capa.clicked.connect(lambda: self.escolher_capa.emit(self))
        layout.addWidget(self.btn_capa)
        self.btn_remover = QPushButton('Remover')
        self.btn_remover.setObjectName('fantasma')
        self.btn_remover.clicked.connect(lambda: self.remover.emit(self))
        layout.addWidget(self.btn_remover)

    def definir_preparacao(self, preparacao: dict) -> None:
        self.preparacao = preparacao
        meta = preparacao['meta']
        self.nome.setText(f"{meta.artista or 'Artista desconhecido'} — {meta.titulo}")
        capa = preparacao['capa']
        fmt = self.pedido.get('formato')
        audio = 'Melhor áudio disponível' if not fmt or fmt.format_id == 'bestaudio' else fmt.descricao_curta()
        detalhe = f"capa: {capa.album or capa.fonte}" if capa.ok else 'sem capa (escolha confirmada)'
        campos = [f"Álbum: {meta.album or 'não identificado'}",
                  f"Gênero: {meta.genero or 'não identificado'}",
                  f"Ano: {meta.ano or 'não identificado'}",
                  f"Faixa: {meta.faixa or 'não identificada'}",
                  f"Artista do álbum: {meta.artista_album or 'não identificado'}",
                  f"Participações: {', '.join(meta.artistas_participantes) or 'não identificadas'}"]
        self.detalhes.setText(f"{audio} · {detalhe}\n" + ' · '.join(campos) +
                              '\nDuração final medida após a conversão. Revise em Editar dados.')
        self.btn_capa.setText('Trocar capa')
        self.alterada.emit()


class DialogoEditarDados(QDialog):
    """Revisão de metadados antes de iniciar o download."""
    def __init__(self, linha: LinhaSelecao, pai=None):
        super().__init__(pai)
        self.setWindowTitle('Editar dados da música')
        self.setMinimumWidth(460)
        raiz = QVBoxLayout(self)
        aviso = QLabel('Confira os dados: IA e catálogos podem errar. Título e artista definem '
                       'o arquivo e a pasta. Antes de preparar, campos vazios serão procurados; '
                       'apagar um valor conhecido o remove. Depois de preparar, apagar um campo o deixa vazio. '
                       'Se mudar título, artista ou álbum, '
                       'revise a capa novamente.')
        aviso.setWordWrap(True)
        raiz.addWidget(aviso)
        formulario = QFormLayout()
        r = linha.pedido['resultado']
        meta = linha.preparacao.get('meta') if linha.preparacao else None
        edicao = linha.pedido.get('edicao') or {}
        self.campos = {}
        for chave, rotulo in [('titulo', 'Título'), ('artista', 'Artista principal'),
                              ('artistas_participantes', 'Participações (separadas por vírgula)'),
                              ('album', 'Álbum'), ('genero', 'Gênero'), ('ano', 'Ano'),
                              ('faixa', 'Número da faixa'), ('artista_album', 'Artista do álbum')]:
            valor = edicao.get(chave, getattr(meta or r, chave, '') or '')
            if isinstance(valor, list):
                valor = ', '.join(valor)
            campo = QLineEdit(str(valor))
            self.campos[chave] = campo
            formulario.addRow(rotulo, campo)
        duracao = hhmmss(r.duracao_s) if r.duracao_s else 'não informada'
        formulario.addRow('Duração', QLabel(f'{duracao} (origem; MP3 final será medido)'))
        self._ja_preparada = meta is not None
        self._editados_anteriores = set(edicao)
        self._valores_iniciais = {k: c.text().strip() for k, c in self.campos.items()}
        raiz.addLayout(formulario)
        botoes = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        botoes.accepted.connect(self._validar)
        botoes.rejected.connect(self.reject)
        raiz.addWidget(botoes)

    def valores(self) -> dict:
        dados = {k: c.text().strip() for k, c in self.campos.items()}
        # Um campo opcional vazio antes da primeira preparação significa
        # "procure", não "apague". Depois, vazio é uma remoção explícita.
        return {k: v for k, v in dados.items() if v or k in ('titulo', 'artista')
                or self._ja_preparada or k in self._editados_anteriores
                or bool(self._valores_iniciais.get(k))}

    def campos_alterados(self) -> set[str]:
        return {k for k, c in self.campos.items() if c.text().strip() != self._valores_iniciais[k]}

    def _validar(self) -> None:
        dados = self.valores()
        if not dados['titulo'] or not dados['artista']:
            QMessageBox.warning(self, 'Dados incompletos', 'Informe título e artista.')
            return
        for campo, limite, rotulo in (('ano', 9999, 'ano'), ('faixa', 999, 'número da faixa')):
            valor = dados.get(campo, '')
            if valor and (not valor.isdecimal() or not 1 <= int(valor) <= limite):
                QMessageBox.warning(self, 'Dados inválidos', f'Informe um {rotulo} válido ou deixe vazio.')
                return
        self.accept()


class DownloadsPage(QWidget):
    mensagem = Signal(str)

    def __init__(self, config: Config, fila: GerenciadorFila, pai: Optional[QWidget] = None) -> None:
        super().__init__(pai)
        self.config = config
        self.fila = fila
        self.linhas: Dict[int, LinhaJob] = {}
        self.selecoes: list[LinhaSelecao] = []
        self._preparando = False
        self._sem_capa_lote = False
        self._restaurando = True
        self._erro_recuperar = ""
        self._a_preparar: list[LinhaSelecao] = []

        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(26, 22, 26, 16)
        raiz.setSpacing(14)

        topo = QHBoxLayout()
        col = QVBoxLayout()
        col.setSpacing(2)
        t = QLabel("Downloads")
        t.setObjectName("titulo")
        st = QLabel("Revise as músicas e escolha as capas antes de baixar em ordem.")
        st.setObjectName("subtitulo")
        col.addWidget(t)
        col.addWidget(st)
        topo.addLayout(col, 1)

        self.btn_pasta = QPushButton("Abrir pasta de saída")
        self.btn_pasta.clicked.connect(self._abrir_pasta_saida)
        topo.addWidget(self.btn_pasta, 0, Qt.AlignBottom)

        self.btn_limpar = QPushButton("Limpar finalizados")
        self.btn_limpar.setObjectName("fantasma")
        self.btn_limpar.clicked.connect(self._limpar)
        topo.addWidget(self.btn_limpar, 0, Qt.AlignBottom)
        raiz.addLayout(topo)

        acoes = QHBoxLayout()
        self.btn_preparar = QPushButton('Revisar capas selecionadas')
        self.btn_preparar.setObjectName('fantasma')
        self.btn_preparar.clicked.connect(self._preparar_selecionadas)
        acoes.addWidget(self.btn_preparar)
        self.btn_sem_capa = QPushButton('Preparar selecionadas sem capa')
        self.btn_sem_capa.setObjectName('fantasma')
        self.btn_sem_capa.clicked.connect(self._preparar_sem_capa)
        acoes.addWidget(self.btn_sem_capa)
        self.btn_baixar = QPushButton('Baixar selecionadas')
        self.btn_baixar.setObjectName('primario')
        self.btn_baixar.clicked.connect(self._baixar_selecionadas)
        acoes.addWidget(self.btn_baixar)
        acoes.addStretch(1)
        raiz.addLayout(acoes)
        self.resumo = QLabel("Nenhum download na fila.")
        self.resumo.setObjectName("dim")
        raiz.addWidget(self.resumo)

        self.area = QScrollArea()
        self.area.setWidgetResizable(True)
        self.area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        conteudo = QWidget()
        self.lista = QVBoxLayout(conteudo)
        self.lista.setContentsMargins(0, 2, 6, 8)
        self.lista.setSpacing(9)
        self.lista.addStretch(1)
        self.area.setWidget(conteudo)
        raiz.addWidget(self.area, 1)

        fila.job_adicionado.connect(self.adicionar)
        fila.job_atualizado.connect(self.atualizar)
        fila.fila_alterada.connect(self._atualizar_resumo)
        self._restaurar_selecoes()
        self._restaurando = False
        self._atualizar_resumo()

    def adicionar_selecao(self, pedido: dict) -> bool:
        r = pedido.get('resultado')
        if r is None:
            return False
        if any(x.pedido['resultado'].fonte == r.fonte and x.pedido['resultado'].uid == r.uid
               for x in self.selecoes):
            self.mensagem.emit('Esta música já está na lista de Downloads.')
            return False
        linha = LinhaSelecao(pedido)
        linha.alterada.connect(self._selecao_alterada)
        linha.remover.connect(self._remover_selecao)
        linha.escolher_capa.connect(self._preparar_uma)
        linha.editar.connect(self._editar_dados)
        self.selecoes.append(linha)
        # Itens pendentes aparecem antes dos downloads já iniciados.
        self.lista.insertWidget(len(self.selecoes) - 1, linha)
        self._atualizar_resumo()
        if not self._persistir_selecoes():
            self.selecoes.remove(linha)
            self.lista.removeWidget(linha)
            linha.setParent(None)
            linha.deleteLater()
            self._atualizar_resumo()
            return False
        return True

    def _remover_selecao(self, linha: LinhaSelecao) -> None:
        if self._preparando or linha not in self.selecoes:
            return
        self.selecoes.remove(linha)
        self.lista.removeWidget(linha)
        linha.setParent(None)
        linha.deleteLater()
        self._atualizar_resumo()
        self._persistir_selecoes()

    def _selecao_alterada(self) -> None:
        self._atualizar_resumo()
        self._persistir_selecoes()

    def _persistir_selecoes(self) -> bool:
        if self._restaurando:
            return True
        if self._erro_recuperar:
            self.mensagem.emit("Não é possível salvar Downloads: falha ao recuperar dados anteriores.")
            return False
        try:
            self.fila.banco.salvar_estado('downloads_selecionados',
                [estado_musicas.serializar_selecao(linha) for linha in self.selecoes])
            return True
        except Exception as exc:
            registrar_erro('Salvar seleção de Downloads', f'{type(exc).__name__}: {exc}')
            self.mensagem.emit(f"Não foi possível salvar a lista de Downloads: {exc}")
            return False

    def _restaurar_selecoes(self) -> None:
        try:
            registros = self.fila.banco.ler_estado('downloads_selecionados', []) or []
            dados = [estado_musicas.desserializar_selecao(d) for d in registros]
            for pedido, marcada, preparacao in dados:
                if self.adicionar_selecao(pedido):
                    linha = self.selecoes[-1]
                    linha.check.setChecked(marcada)
                    if preparacao:
                        linha.definir_preparacao(preparacao)
                    elif pedido.get('edicao'):
                        linha.nome.setText(f"{pedido['edicao'].get('artista', '')} — {pedido['edicao'].get('titulo', '')}")
        except Exception as exc:
            registrar_erro('Recuperar seleção de Downloads', f'{type(exc).__name__}: {exc}')
            self._erro_recuperar = str(exc)

    def _editar_dados(self, linha: LinhaSelecao) -> None:
        if self._preparando:
            return
        dialogo = DialogoEditarDados(linha, self)
        if dialogo.exec() != QDialog.Accepted:
            return
        edicao = dialogo.valores()
        preparacao = linha.preparacao
        identidade_mudou = preparacao and any(
            str(edicao.get(c, '')).strip() != str(getattr(preparacao['meta'], c, '') or '').strip()
            for c in ('titulo', 'artista', 'album'))
        if identidade_mudou:
            alterados = dialogo.campos_alterados()
            if isinstance(alterados, (set, list, tuple)):
                # Não carregar automaticamente faixa/ano/gênero da edição
                # anterior para uma identidade ou álbum modificado.
                edicao = {k: v for k, v in edicao.items()
                          if k in ('titulo', 'artista', 'album') or k in alterados}
        linha.pedido['edicao'] = edicao
        if preparacao and not identidade_mudou:
            preparacao['apagar_tags'] = aplicar_edicao(preparacao['meta'], edicao)
            linha.definir_preparacao(preparacao)
        else:
            linha.preparacao = None
            linha.nome.setText(f"{edicao['artista']} — {edicao['titulo']}")
            linha.detalhes.setText('Dados editados · escolha ou dispense a capa novamente')
            linha.btn_capa.setText('Escolher capa')
        self._selecao_alterada()

    def _preparar_uma(self, linha: LinhaSelecao) -> None:
        if self._preparando:
            return
        self._iniciar_preparacao([linha])

    def _preparar_selecionadas(self) -> None:
        self._iniciar_preparacao([l for l in self.selecoes if l.check.isChecked()])

    def _preparar_sem_capa(self) -> None:
        linhas = [l for l in self.selecoes if l.check.isChecked()]
        if not linhas or self._preparando:
            return
        nao_marcadas = len(self.selecoes) - len(linhas)
        resposta = QMessageBox.question(self, 'Preparar sem capa',
            f"Preparar {len(linhas)} música(s) marcadas sem capa? "
            f"{nao_marcadas} música(s) desmarcadas não serão alteradas. "
            "Isso prepara os próximos downloads; não altera MP3s já existentes e não inicia o download.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if resposta == QMessageBox.Yes:
            self._iniciar_preparacao(linhas, sem_capa=True)

    def _iniciar_preparacao(self, linhas: list[LinhaSelecao], sem_capa: bool = False) -> None:
        if self._preparando or not linhas:
            return
        self._preparando = True
        self._sem_capa_lote = sem_capa
        self._a_preparar = list(linhas)
        self._atualizar_resumo()
        self._proxima_capa()

    def _proxima_capa(self) -> None:
        if not self._a_preparar:
            self._preparando = False
            self._atualizar_resumo()
            self.mensagem.emit('Preparação concluída. Você já pode iniciar o lote.')
            return
        linha = self._a_preparar.pop(0)
        r = linha.pedido['resultado']
        self.resumo.setText(f'Preparando metadados: {r.artista} — {r.titulo}…')
        EXECUTOR_GLOBAL.rodar(
            preparar_musica, r, self.config, edicao=linha.pedido.get('edicao'),
            sem_capa=self._sem_capa_lote,
            ao_resultado=lambda dados, l=linha: self._capa_pronta(l, dados),
            ao_erro=self._falha_preparacao)

    def _capa_pronta(self, linha: LinhaSelecao, dados: dict) -> None:
        if not self._preparando or linha not in self.selecoes:
            return
        capa = dados['capa']
        meta = dados['meta']
        if self._sem_capa_lote:
            linha.definir_preparacao(dados)
            self._proxima_capa()
            return
        consulta = dados.get('consulta_capa') or {}
        dialogo = DialogoCapas(self, capa, {'titulo': consulta.get('titulo', meta.titulo),
                                            'artista': consulta.get('artista', meta.artista),
                                            'consulta_capa': consulta,
                                            'album': meta.album, 'ano': meta.ano,
                                            'metadados': {'titulo': meta.titulo, 'artista': meta.artista,
                                                          'album': meta.album, 'ano': meta.ano,
                                                          'faixa': meta.faixa, 'genero': meta.genero,
                                                          'artista_album': meta.artista_album,
                                                          'participacoes': ', '.join(meta.artistas_participantes)},
                                            'abrir_google_automaticamente': True})
        if dialogo.exec() != QDialog.Accepted:
            self._cancelar_preparacao()
            return
        capa = dialogo.escolhida if not dialogo.recusou else None
        dados['capa'] = capa or CoverResult(observacao='Usuário escolheu não usar capa')
        linha.definir_preparacao(dados)
        self._proxima_capa()

    def _cancelar_preparacao(self) -> None:
        self._a_preparar.clear()
        self._preparando = False
        self._atualizar_resumo()
        self.mensagem.emit('Escolha de capas interrompida; nenhum áudio foi baixado.')

    def _falha_preparacao(self, mensagem: str) -> None:
        registrar_erro('Preparar música e capa', mensagem)
        self._cancelar_preparacao()
        QMessageBox.warning(self, 'Não foi possível buscar a capa', mensagem[:500])

    def _baixar_selecionadas(self) -> None:
        selecionadas = [l for l in self.selecoes if l.check.isChecked()]
        if not selecionadas or self._preparando:
            return
        if any(l.preparacao is None for l in selecionadas):
            self.mensagem.emit('Escolha as capas de todas as músicas selecionadas primeiro.')
            return
        for linha in selecionadas:
            capa = linha.preparacao['capa']
            if capa.ok and not Path(capa.caminho).is_file():
                self.mensagem.emit('Uma capa não está mais disponível. Escolha-a novamente.')
                linha.preparacao = None
                self._atualizar_resumo()
                return
        try:
            self.config.garantir_pasta_saida()
        except RuntimeError as exc:
            registrar_erro('Pasta de saída antes do lote', f'{type(exc).__name__}: {exc}')
            QMessageBox.warning(self, 'Pasta de saída indisponível', str(exc))
            return
        self.btn_baixar.setEnabled(False)
        for linha in selecionadas:
            pedido = linha.pedido
            try:
                self.fila.adicionar(pedido['resultado'], pedido.get('formato'),
                                    preparacao=linha.preparacao)
            except Exception as exc:
                # Preserva na lista o item que falhou e todos os seguintes.
                registrar_erro('Iniciar lote', f'{type(exc).__name__}: {exc}')
                QMessageBox.warning(self, 'Falha ao iniciar o lote', str(exc)[:500])
                break
            self._remover_selecao(linha)
        self._atualizar_resumo()

    # ------------------------------------------------------------------ slots
    def adicionar(self, job: dict) -> None:
        linha = LinhaJob(job)
        linha.abrir.connect(self._abrir_arquivo)
        linha.cancelar.connect(self.fila.cancelar)
        linha.tentar.connect(self._tentar_novamente)
        self.linhas[int(job["id"])] = linha
        self.lista.insertWidget(self.lista.count() - 1, linha)
        self._atualizar_resumo()

    def _tentar_novamente(self, jid: int) -> None:
        try:
            self.fila.tentar_novamente(jid)
            self.mensagem.emit('Nova tentativa adicionada à fila.')
        except Exception as exc:
            registrar_erro('Tentar download novamente', f'{type(exc).__name__}: {exc}')
            QMessageBox.warning(self, 'Não foi possível tentar novamente', str(exc)[:500])

    def atualizar(self, job: dict) -> None:
        linha = self.linhas.get(int(job.get("id", 0)))
        if linha:
            linha.atualizar(job)
        self._atualizar_resumo()

    def _atualizar_resumo(self) -> None:
        total = len(self.linhas)
        pendentes = self.fila.pendentes
        prontos = sum(1 for l in self.linhas.values()
                      if l.job.get("status") == "finalizado")
        erros = sum(1 for l in self.linhas.values() if l.job.get("status") == "erro")
        escolhidas = [l for l in self.selecoes if l.check.isChecked()]
        faltam = sum(l.preparacao is None for l in escolhidas)
        self.btn_preparar.setEnabled(bool(escolhidas) and not self._preparando)
        self.btn_sem_capa.setEnabled(bool(escolhidas) and not self._preparando)
        self.btn_baixar.setEnabled(bool(escolhidas) and not faltam and not self._preparando)
        self.btn_baixar.setText(f'Baixar selecionadas ({len(escolhidas)})')
        for linha in self.selecoes:
            linha.setEnabled(not self._preparando)
        if self._erro_recuperar:
            self.resumo.setText('Não foi possível recuperar Downloads salvos; dados anteriores foram preservados. ' + self._erro_recuperar[:180])
        elif not self._preparando:
            self.resumo.setText(f'{len(self.selecoes)} na seleção · {faltam} capa(s) a revisar · '
                                f'{pendentes} na fila · {prontos} concluído(s) · {erros} erro(s)')

    def _limpar(self) -> None:
        for jid, linha in list(self.linhas.items()):
            if linha.job.get("status") in ("finalizado", "erro", "cancelado"):
                linha.setParent(None)
                linha.deleteLater()
                self.linhas.pop(jid, None)
        self.fila.limpar_finalizados()
        self._atualizar_resumo()

    def _abrir_arquivo(self, caminho: str) -> None:
        try:
            if os.name == "nt":
                os.startfile(caminho)                      # noqa: S606
            elif sys.platform == "darwin":
                subprocess.Popen(["open", caminho])
            else:
                subprocess.Popen(["xdg-open", caminho])
        except Exception as exc:                           # noqa: BLE001
            self.mensagem.emit(f"Não foi possível abrir: {exc}")

    def _abrir_pasta_saida(self) -> None:
        pasta = self.config.pasta_saida
        try:
            if not pasta.is_dir():
                raise OSError("pasta indisponível; escolha outra em Configurações")
            if os.name == "nt":
                os.startfile(str(pasta))                   # noqa: S606
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(pasta)])
            else:
                subprocess.Popen(["xdg-open", str(pasta)])
        except Exception as exc:                           # noqa: BLE001
            self.mensagem.emit(f"Não foi possível abrir a pasta: {exc}")

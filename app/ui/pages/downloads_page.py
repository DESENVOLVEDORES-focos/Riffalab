"""Página de downloads: acompanhamento em tempo real da fila."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QDialog, QFrame, QHBoxLayout, QLabel,
                               QMessageBox, QProgressBar, QPushButton, QScrollArea,
                               QVBoxLayout, QWidget)

from ...config import Config
from ...downloader import GerenciadorFila
from ...models import CoverResult
from ...preparacao import preparar_musica
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

        self.btn_cancelar = QPushButton("Cancelar")
        self.btn_cancelar.setObjectName("fantasma")
        self.btn_cancelar.clicked.connect(lambda: self.cancelar.emit(int(self.job.get("id", 0))))
        linha.addWidget(self.btn_cancelar)
        lay.addLayout(linha)

        self.mensagem = QLabel("aguardando…")
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
        self.mensagem.setText(msg[:190])
        self.mensagem.setStyleSheet(
            f"color: {PALETA['vermelho'] if status == 'erro' else PALETA['texto_fraco']}; font-size: 11px;")
        # O gerenciador só pode cancelar itens ainda aguardando na fila.
        self.btn_cancelar.setVisible(status == 'na fila')
        self.btn_cancelar.setToolTip('Cancelar esta música enquanto aguarda na fila')
        self.btn_abrir.setVisible(status == "finalizado" and bool(job.get("caminho")))

    def _abrir(self) -> None:
        caminho = self.job.get("caminho") or ""
        if caminho:
            self.abrir.emit(caminho)


class LinhaSelecao(QFrame):
    """Uma música revisável antes de enviar qualquer áudio para download."""
    alterada = Signal()
    remover = Signal(object)
    escolher_capa = Signal(object)

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
        nome = QLabel(f"{r.artista or 'Artista desconhecido'} — {r.titulo}")
        nome.setWordWrap(True)
        nome.setStyleSheet('font-weight: 700;')
        textos.addWidget(nome)
        fmt = pedido.get('formato')
        audio = 'Melhor áudio disponível' if not fmt or fmt.format_id == 'bestaudio' else fmt.descricao_curta()
        self.detalhes = QLabel(f'{audio} · capa ainda não escolhida')
        self.detalhes.setWordWrap(True)
        self.detalhes.setObjectName('dim')
        textos.addWidget(self.detalhes)
        layout.addLayout(textos, 1)
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
        capa = preparacao['capa']
        fmt = self.pedido.get('formato')
        audio = 'Melhor áudio disponível' if not fmt or fmt.format_id == 'bestaudio' else fmt.descricao_curta()
        detalhe = f"capa: {capa.album or capa.fonte}" if capa.ok else 'sem capa (escolha confirmada)'
        self.detalhes.setText(f'{audio} · {detalhe}')
        self.btn_capa.setText('Trocar capa')
        self.alterada.emit()


class DownloadsPage(QWidget):
    mensagem = Signal(str)

    def __init__(self, config: Config, fila: GerenciadorFila, pai: Optional[QWidget] = None) -> None:
        super().__init__(pai)
        self.config = config
        self.fila = fila
        self.linhas: Dict[int, LinhaJob] = {}
        self.selecoes: list[LinhaSelecao] = []
        self._preparando = False
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
        self.btn_preparar = QPushButton('Escolher capas selecionadas')
        self.btn_preparar.setObjectName('fantasma')
        self.btn_preparar.clicked.connect(self._preparar_selecionadas)
        acoes.addWidget(self.btn_preparar)
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
        linha.alterada.connect(self._atualizar_resumo)
        linha.remover.connect(self._remover_selecao)
        linha.escolher_capa.connect(self._preparar_uma)
        self.selecoes.append(linha)
        # Itens pendentes aparecem antes dos downloads já iniciados.
        self.lista.insertWidget(len(self.selecoes) - 1, linha)
        self._atualizar_resumo()
        return True

    def _remover_selecao(self, linha: LinhaSelecao) -> None:
        if self._preparando or linha not in self.selecoes:
            return
        self.selecoes.remove(linha)
        self.lista.removeWidget(linha)
        linha.setParent(None)
        linha.deleteLater()
        self._atualizar_resumo()

    def _preparar_uma(self, linha: LinhaSelecao) -> None:
        if self._preparando:
            return
        self._iniciar_preparacao([linha])

    def _preparar_selecionadas(self) -> None:
        self._iniciar_preparacao([l for l in self.selecoes if l.check.isChecked()
                                  and l.preparacao is None])

    def _iniciar_preparacao(self, linhas: list[LinhaSelecao]) -> None:
        if self._preparando or not linhas:
            return
        self._preparando = True
        self._a_preparar = list(linhas)
        self._atualizar_resumo()
        self._proxima_capa()

    def _proxima_capa(self) -> None:
        if not self._a_preparar:
            self._preparando = False
            self._atualizar_resumo()
            self.mensagem.emit('Capas revisadas. Você já pode iniciar o lote.')
            return
        linha = self._a_preparar.pop(0)
        r = linha.pedido['resultado']
        self.resumo.setText(f'Buscando metadados e capas: {r.artista} — {r.titulo}…')
        EXECUTOR_GLOBAL.rodar(
            preparar_musica, r, self.config,
            ao_resultado=lambda dados, l=linha: self._capa_pronta(l, dados),
            ao_erro=self._falha_preparacao)

    def _capa_pronta(self, linha: LinhaSelecao, dados: dict) -> None:
        if not self._preparando or linha not in self.selecoes:
            return
        capa = dados['capa']
        meta = dados['meta']
        dialogo = DialogoCapas(self, capa, {'titulo': meta.titulo, 'artista': meta.artista,
                                            'album': meta.album, 'ano': meta.ano})
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
                QMessageBox.warning(self, 'Falha ao iniciar o lote', str(exc)[:500])
                break
            self._remover_selecao(linha)
        self._atualizar_resumo()

    # ------------------------------------------------------------------ slots
    def adicionar(self, job: dict) -> None:
        linha = LinhaJob(job)
        linha.abrir.connect(self._abrir_arquivo)
        linha.cancelar.connect(self.fila.cancelar)
        self.linhas[int(job["id"])] = linha
        self.lista.insertWidget(self.lista.count() - 1, linha)
        self._atualizar_resumo()

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
        self.btn_preparar.setEnabled(bool(escolhidas) and bool(faltam) and not self._preparando)
        self.btn_baixar.setEnabled(bool(escolhidas) and not faltam and not self._preparando)
        self.btn_baixar.setText(f'Baixar selecionadas ({len(escolhidas)})')
        for linha in self.selecoes:
            linha.setEnabled(not self._preparando)
        if not self._preparando:
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

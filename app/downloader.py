"""Fila de processamento (download → conversão → tags → organização).

A fila processa uma música de cada vez, na ordem de entrada.
Cada job tem estado próprio e é registrado no SQLite a cada mudança.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any, Deque, Dict, List, Optional

from PySide6.QtCore import QObject, Signal

from . import pipeline, sources
from .config import Config
from .db import Banco
from .models import AudioFormat, TrackResult
from .quality import rotulo
from .workers import EXECUTOR_GLOBAL


# A interface registra aqui o confirmador de capa (thread da UI). Fica em
# nível de módulo porque o download acontece em threads do pool.
_APROVADOR_CAPA = None


def definir_aprovador_capa(fn) -> None:
    global _APROVADOR_CAPA
    _APROVADOR_CAPA = fn


class GerenciadorFila(QObject):
    job_atualizado = Signal(dict)
    job_adicionado = Signal(dict)
    fila_alterada = Signal()
    mensagem = Signal(str)
    terminou_tudo = Signal()

    def __init__(self, config: Config, banco: Banco, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.config = config
        self.banco = banco
        self.fila: Deque[Dict[str, Any]] = deque()
        self.jobs: Dict[int, Dict[str, Any]] = {}
        self._ativos = 0
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ API
    def adicionar(self, resultado: TrackResult, formato: Optional[AudioFormat] = None,
                  meta_extra: Optional[Dict[str, Any]] = None,
                  preparacao: Optional[Dict[str, Any]] = None) -> int:
        formato = formato or resultado.melhor
        job_db = self.banco.criar_download({
            "titulo": resultado.titulo, "artista": resultado.artista,
            "album": resultado.album, "ano": resultado.ano, "fonte": resultado.fonte,
            "codec": formato.codec if formato else "",
            "bitrate": formato.bitrate_kbps if formato else None,
            "sample_rate": formato.sample_rate if formato else None,
            "qualidade": rotulo(formato), "status": "na fila",
        })
        job = {
            "id": job_db,
            "titulo": resultado.titulo,
            "artista": resultado.artista or resultado.fonte,
            "fonte": resultado.fonte,
            "formato": formato.descricao_curta() if formato else "-",
            "video": resultado.resumo_video(),
            "qualidade": rotulo(formato),
            "progresso": 0,
            "status": "na fila",
            "mensagem": "aguardando…",
            "caminho": "",
            "erro": "",
        }
        with self._lock:
            self.jobs[job_db] = job
            self.fila.append({"job": job, "resultado": resultado, "formato": formato,
                              "meta": meta_extra or {}, "preparacao": preparacao})
        self.job_adicionado.emit(dict(job))
        self.fila_alterada.emit()
        self._proximo()
        return job_db

    def adicionar_varios(self, itens: List[TrackResult]) -> int:
        n = 0
        for r in itens:
            self.adicionar(r)
            n += 1
        return n

    def cancelar(self, job_id: int) -> None:
        with self._lock:
            alvo = None
            for item in list(self.fila):
                if item["job"]["id"] == job_id:
                    alvo = item
                    self.fila.remove(item)
                    break
        if alvo is None:
            return
        job = alvo["job"]
        job["status"] = "cancelado"
        job["mensagem"] = "cancelado pelo usuário"
        self.banco.atualizar_download(job_id, status="cancelado")
        self.job_atualizado.emit(dict(job))
        self.fila_alterada.emit()

    def limpar_finalizados(self) -> None:
        with self._lock:
            for jid in [j for j, d in self.jobs.items()
                        if d["status"] in ("finalizado", "erro", "cancelado")]:
                self.jobs.pop(jid, None)
        self.fila_alterada.emit()

    @property
    def pendentes(self) -> int:
        """Quantos ainda não terminaram (em qualquer etapa)."""
        return sum(1 for d in self.jobs.values()
                   if d["status"] not in ("finalizado", "erro", "cancelado"))

    @property
    def ativos(self) -> int:
        return self._ativos

    # ------------------------------------------------------------- interno
    def _limite(self) -> int:
        # O lote segue a ordem escolhida, uma música por vez.
        return 1

    def _proximo(self) -> None:
        """Inicia tantos jobs quantos o limite permitir (e houver na fila)."""
        while True:
            terminar = False
            with self._lock:
                if not self.fila or self._ativos >= self._limite():
                    terminar = not self.fila and self._ativos == 0
                    item = None
                else:
                    item = self.fila.popleft()
                    self._ativos += 1
            if terminar:
                self.terminou_tudo.emit()      # fora do lock: o slot pode reentrar
                return
            if item is None:
                return
            self._iniciar(item)

    def _iniciar(self, item: Dict[str, Any]) -> None:
        job = item["job"]
        job["status"] = "analisando"
        job["mensagem"] = "iniciando…"
        self.banco.atualizar_download(job["id"], status="analisando")
        self.job_atualizado.emit(dict(job))

        fonte = sources.por_id(item["resultado"].fonte, self.config)

        def ao_progresso(pct: int, msg: str) -> None:
            job["progresso"] = int(pct)
            job["mensagem"] = msg
            job["status"] = self._status_por_etapa(msg)
            self.banco.atualizar_download(job["id"], progresso=int(pct), status=job["status"])
            self.job_atualizado.emit(dict(job))

        def ao_terminar(res: Any) -> None:
            self._concluir(job, res)

        def ao_erro(msg: str) -> None:
            job["status"] = "erro"
            job["erro"] = msg
            job["mensagem"] = msg
            self.banco.atualizar_download(job["id"], status="erro", erro=msg)
            self.job_atualizado.emit(dict(job))
            self._liberar()

        EXECUTOR_GLOBAL.rodar(
            pipeline.processar_resultado,
            item["resultado"], self.config, item["formato"],
            meta_extra=item["meta"], fonte=fonte,
            preparacao=item["preparacao"], aprovador_capa=_APROVADOR_CAPA,
            ao_resultado=ao_terminar, ao_erro=ao_erro, ao_progresso=ao_progresso,
            com_progresso=True,
        )

    @staticmethod
    def _status_por_etapa(msg: str) -> str:
        m = msg.lower()
        if "baixando" in m or "obtendo" in m or "copiando" in m or "download" in m:
            return "baixando"
        if "identificando" in m or "identificada" in m or "ia não confirmou" in m:
            return "identificando"
        if "analisando" in m or "consultando" in m:
            return "analisando"
        if "convertendo" in m:
            return "convertendo"
        if "capa" in m or "metadados" in m:
            return "metadados"
        if "gravando" in m or "organizando" in m:
            return "finalizando"
        return "processando"

    def _concluir(self, job: Dict[str, Any], res: Any) -> None:
        res = res or {}
        if res.get("ok"):
            job["status"] = "finalizado"
            job["progresso"] = 100
            job["caminho"] = res.get("caminho", "")
            job["mensagem"] = res.get("mensagem") or "arquivo organizado"
            capa = res.get("capa") or {}
            if capa.get("fonte"):
                detalhe_capa = (f"{capa['fonte']} · {capa.get('album') or 'sem álbum'}"
                                + (f" · {capa['artista']}" if capa.get("artista") else ""))
                if capa.get("dimensoes"):
                    detalhe_capa += f" · {capa['dimensoes']}"
                if capa.get("score"):
                    detalhe_capa += f" · correspondência {float(capa['score']):.2f}"
                job["capa"] = detalhe_capa
            elif capa.get("observacao"):
                job["capa"] = f"sem capa: {capa['observacao'][:70]}"
            ident = res.get("identificacao") or {}
            if ident.get("ok"):
                resumo = f"{ident.get('artista') or '?'} — {ident.get('titulo') or '?'}"
                if ident.get("album"):
                    resumo += f"  ·  {ident['album']}"
                job["identificacao"] = resumo
                job["ia_confianca"] = ident.get("confianca")
            self.banco.atualizar_download(
                job["id"], status="finalizado", progresso=100,
                caminho=job["caminho"], acao=(res.get("conversao") or {}).get("acao", ""),
                capa_fonte=(res.get("capa") or {}).get("fonte", ""),
                tamanho=res.get("tamanho") or 0, fim_em=time.time(),
            )
            self.banco.registrar_historico(
                "processamento", f"{job['artista']} - {job['titulo']}",
                job["fonte"], job["mensagem"], 1)
            self.mensagem.emit(f"Pronto: {job['artista']} - {job['titulo']}")
        else:
            job["status"] = "erro"
            job["erro"] = res.get("erro", "erro desconhecido")
            job["mensagem"] = job["erro"]
            self.banco.atualizar_download(job["id"], status="erro", erro=job["erro"])
            self.mensagem.emit(f"Erro em {job['titulo']}: {job['erro'][:80]}")
        self.job_atualizado.emit(dict(job))
        self._liberar()

    def _liberar(self) -> None:
        with self._lock:
            self._ativos = max(0, self._ativos - 1)
        self.fila_alterada.emit()
        self._proximo()

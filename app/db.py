"""Banco local (SQLite): histórico de pesquisas, downloads e biblioteca."""
from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .config import ARQ_BANCO

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;

CREATE TABLE IF NOT EXISTS historico (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo      TEXT NOT NULL,            -- 'pesquisa' | 'processamento'
    consulta  TEXT NOT NULL,
    fonte     TEXT DEFAULT '',
    detalhe   TEXT DEFAULT '',
    n_itens   INTEGER DEFAULT 0,
    criado_em REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS downloads (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo      TEXT DEFAULT '',
    artista     TEXT DEFAULT '',
    album       TEXT DEFAULT '',
    ano         INTEGER,
    fonte       TEXT DEFAULT '',
    codec       TEXT DEFAULT '',
    bitrate     INTEGER,
    sample_rate INTEGER,
    qualidade   TEXT DEFAULT '',
    acao        TEXT DEFAULT '',        -- copiar | recodificar
    capa_fonte  TEXT DEFAULT '',
    caminho     TEXT DEFAULT '',
    tamanho     INTEGER DEFAULT 0,
    status      TEXT DEFAULT 'na fila', -- na fila | baixando | convertendo | finalizado | erro
    progresso   INTEGER DEFAULT 0,
    erro        TEXT DEFAULT '',
    criado_em   REAL NOT NULL,
    fim_em      REAL
);

CREATE TABLE IF NOT EXISTS biblioteca (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    caminho     TEXT UNIQUE NOT NULL,
    titulo      TEXT DEFAULT '',
    artista     TEXT DEFAULT '',
    album       TEXT DEFAULT '',
    ano         TEXT DEFAULT '',
    codec       TEXT DEFAULT '',
    bitrate     INTEGER,
    sample_rate INTEGER,
    duracao     REAL,
    tamanho     INTEGER DEFAULT 0,
    tem_capa    INTEGER DEFAULT 0,
    modificado  REAL DEFAULT 0,
    indexado_em REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_hist_criado ON historico(criado_em DESC);
CREATE INDEX IF NOT EXISTS idx_dl_criado   ON downloads(criado_em DESC);
CREATE INDEX IF NOT EXISTS idx_bib_artista ON biblioteca(artista);
"""


class Banco:
    """Uma conexão compartilhada, protegida por Lock (thread-safe)."""

    def __init__(self, caminho: str | Path | None = None) -> None:
        self.caminho = Path(caminho or ARQ_BANCO)
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._con = sqlite3.connect(str(self.caminho), check_same_thread=False, timeout=30)
        self._con.row_factory = sqlite3.Row
        with self._lock:
            self._con.executescript(SCHEMA)
            self._con.commit()

    # ---------------------------------------------------------- genéricos
    def _exec(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._con.execute(sql, tuple(params))
            self._con.commit()
            return cur

    def _query(self, sql: str, params: Iterable[Any] = ()) -> List[Dict[str, Any]]:
        with self._lock:
            cur = self._con.execute(sql, tuple(params))
            return [dict(r) for r in cur.fetchall()]

    def fechar(self) -> None:
        with self._lock:
            try:
                self._con.close()
            except Exception:
                pass

    # ---------------------------------------------------------- histórico
    def registrar_historico(self, tipo: str, consulta: str, fonte: str = "",
                            detalhe: str = "", n_itens: int = 0) -> int:
        cur = self._exec(
            "INSERT INTO historico (tipo, consulta, fonte, detalhe, n_itens, criado_em) "
            "VALUES (?,?,?,?,?,?)",
            (tipo, consulta, fonte, detalhe, n_itens, time.time()),
        )
        return int(cur.lastrowid)

    def listar_historico(self, limite: int = 200, filtro: str = "") -> List[Dict[str, Any]]:
        if filtro:
            like = f"%{filtro}%"
            return self._query(
                "SELECT * FROM historico WHERE consulta LIKE ? OR detalhe LIKE ? "
                "ORDER BY criado_em DESC LIMIT ?", (like, like, limite))
        return self._query("SELECT * FROM historico ORDER BY criado_em DESC LIMIT ?", (limite,))

    def limpar_historico(self) -> None:
        self._exec("DELETE FROM historico")

    # ---------------------------------------------------------- downloads
    def criar_download(self, dados: Dict[str, Any]) -> int:
        campos = ["titulo", "artista", "album", "ano", "fonte", "codec", "bitrate",
                  "sample_rate", "qualidade", "caminho", "status"]
        valores = [dados.get(c) for c in campos]
        cur = self._exec(
            f"INSERT INTO downloads ({','.join(campos)}, criado_em) VALUES "
            f"({','.join('?' for _ in campos)}, ?)",
            (*valores, time.time()),
        )
        return int(cur.lastrowid)

    def atualizar_download(self, id_: int, **campos: Any) -> None:
        if not campos:
            return
        sets = ", ".join(f"{k}=?" for k in campos)
        self._exec(f"UPDATE downloads SET {sets} WHERE id=?", (*campos.values(), id_))

    def listar_downloads(self, limite: int = 200) -> List[Dict[str, Any]]:
        return self._query("SELECT * FROM downloads ORDER BY criado_em DESC LIMIT ?", (limite,))

    def limpar_downloads(self) -> None:
        self._exec("DELETE FROM downloads")

    # ---------------------------------------------------------- biblioteca
    def indexar(self, caminho: str, titulo: str = "", artista: str = "", album: str = "",
                ano: str = "", codec: str = "", bitrate: Optional[int] = None,
                sample_rate: Optional[int] = None, duracao: Optional[float] = None,
                tamanho: int = 0, tem_capa: bool = False, modificado: float = 0.0) -> None:
        self._exec(
            "INSERT INTO biblioteca (caminho, titulo, artista, album, ano, codec, bitrate, "
            "sample_rate, duracao, tamanho, tem_capa, modificado, indexado_em) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(caminho) DO UPDATE SET titulo=excluded.titulo, artista=excluded.artista, "
            "album=excluded.album, ano=excluded.ano, codec=excluded.codec, bitrate=excluded.bitrate, "
            "sample_rate=excluded.sample_rate, duracao=excluded.duracao, tamanho=excluded.tamanho, "
            "tem_capa=excluded.tem_capa, modificado=excluded.modificado, indexado_em=excluded.indexado_em",
            (caminho, titulo, artista, album, ano, codec, bitrate, sample_rate, duracao,
             tamanho, int(tem_capa), modificado, time.time()),
        )

    def listar_biblioteca(self, filtro: str = "", limite: int = 1000) -> List[Dict[str, Any]]:
        if filtro:
            like = f"%{filtro}%"
            return self._query(
                "SELECT * FROM biblioteca WHERE titulo LIKE ? OR artista LIKE ? OR album LIKE ? "
                "OR caminho LIKE ? ORDER BY artista, album, titulo LIMIT ?",
                (like, like, like, like, limite))
        return self._query(
            "SELECT * FROM biblioteca ORDER BY artista, album, titulo LIMIT ?", (limite,))

    def remover_da_biblioteca(self, caminho: str) -> None:
        self._exec("DELETE FROM biblioteca WHERE caminho=?", (caminho,))

    def contar(self) -> Dict[str, int]:
        with self._lock:
            def _c(tabela: str) -> int:
                return int(self._con.execute(f"SELECT COUNT(*) FROM {tabela}").fetchone()[0])
            return {"historico": _c("historico"), "downloads": _c("downloads"),
                    "biblioteca": _c("biblioteca")}

    def estatisticas(self) -> Dict[str, Any]:
        with self._lock:
            total = self._con.execute("SELECT COUNT(*), COALESCE(SUM(tamanho),0) FROM biblioteca").fetchone()
            com_capa = self._con.execute("SELECT COUNT(*) FROM biblioteca WHERE tem_capa=1").fetchone()[0]
        return {"arquivos": int(total[0]), "bytes": int(total[1]), "com_capa": int(com_capa)}

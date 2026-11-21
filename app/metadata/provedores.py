"""Provedores de candidatos de capa, sem baixar a imagem.

A busca de singles utiliza MusicBrainz/Cover Art Archive, iTunes e Deezer.
A filtragem e a validação ocorrem em busca_capas; Discogs está desativado.
"""
from __future__ import annotations

import os
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..config import RAIZ
from ..texto import normalizar
from . import coverartarchive, itunes, musicbrainz

UA = "RiffLab/0.5 (uso local; capas) "
TIMEOUT = 25

# serviço -> (intervalo mínimo entre chamadas em segundos)
_INTERVALOS = {"musicbrainz": 1.05, "coverartarchive": 0.3, "itunes": 3.0,
               "deezer": 0.35, "discogs": 1.1}
_ultimo: Dict[str, float] = {}

PRIORIDADE = {"coverartarchive_confirmado": 1, "coverartarchive": 2,
              "itunes": 3, "deezer": 4, "discogs": 5, "miniatura": 9}


@dataclass
class Capa:
    url: str = ""
    fonte: str = ""
    prioridade: int = 5
    album: str = ""
    artista: str = ""
    ano: Optional[int] = None
    titulo: str = ""
    isrc: str = ""
    mbid: str = ""
    confirmada: bool = False          # álbum confirmado pela IA + MusicBrainz
    frontal: bool = True              # só capa frontal (CAA: types/Front)
    score_provedor: float = 0.0       # confiança que o próprio provedor deu
    observacao: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

    def como_dict(self) -> Dict[str, Any]:
        return {"url": self.url, "fonte": self.fonte, "prioridade": self.prioridade,
                "album": self.album, "artista": self.artista, "ano": self.ano,
                "titulo": self.titulo, "isrc": self.isrc, "mbid": self.mbid,
                "confirmada": self.confirmada, "frontal": self.frontal,
                "score": self.score_provedor, "observacao": self.observacao}


def _aguardar(servico: str) -> None:
    intervalo = _INTERVALOS.get(servico, 0.5)
    agora = time.monotonic()
    espera = intervalo - (agora - _ultimo.get(servico, 0.0))
    if espera > 0:
        time.sleep(min(espera, 5.0))
    _ultimo[servico] = time.monotonic()


def _get_json(url: str, servico: str, cabecalhos: Optional[Dict[str, str]] = None,
              tentativas: int = 2, timeout: int = TIMEOUT) -> Any:
    _aguardar(servico)
    for tentativa in range(tentativas):
        try:
            cab = {"User-Agent": UA, "Accept": "application/json"}
            cab.update(cabecalhos or {})
            req = urllib.request.Request(url, headers=cab)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                import json
                return json.loads(resp.read().decode("utf-8", "replace"))
        except Exception:                                         # noqa: BLE001
            if tentativa + 1 >= tentativas:
                return None
            time.sleep(1.2 * (tentativa + 1))
    return None


# ------------------------------------------------------------------ 1 e 2: CAA
def caa_album_confirmado(mbid_release_group: str, album: str = "",
                         artista: str = "", ano: Optional[int] = None
                         ) -> List[Capa]:
    """Capa do release-group que a identificação confirmou."""
    if not mbid_release_group:
        return []
    saida: List[Capa] = []
    for imagem in coverartarchive.imagens(release_group=mbid_release_group)[:3]:
        saida.append(Capa(url=imagem.get("url", ""),
                          fonte="coverartarchive_confirmado",
                          prioridade=PRIORIDADE["coverartarchive_confirmado"],
                          album=album, artista=artista, ano=ano,
                          mbid=mbid_release_group, confirmada=True,
                          frontal=True, score_provedor=0.97,
                          observacao="capa do álbum confirmado (MusicBrainz)",
                          extra={"tipos": imagem.get("tipos") or []}))
    return [c for c in saida if c.url]


def caa_busca(titulo: str, artista: str = "", album: str = "",
              ano: Optional[int] = None) -> List[Capa]:
    """CAA por busca de texto — usa a confiança real da MusicBrainz."""
    try:
        achado = musicbrainz.melhor_capa(titulo, artista, "", somente_single=True)
    except Exception:                                             # noqa: BLE001
        return []
    if not achado or not achado.get("url"):
        return []
    confianca = float(achado.get("confianca") or 0.0)
    if confianca < 0.70:                     # portão: evita capa de outra música
        return []
    return [Capa(url=achado["url"], fonte="coverartarchive",
                 prioridade=PRIORIDADE["coverartarchive"],
                 album=achado.get("album") or "",
                 artista=achado.get("artista") or "",
                 titulo=achado.get("titulo") or "",
                 ano=achado.get("ano"),
                 mbid=achado.get("release_group") or "",
                 score_provedor=round(confianca, 3),
                 observacao="Cover Art Archive (busca por gravação)",
                 extra={"release_id": achado.get("release_id") or "",
                        "tipo_lancamento": str(achado.get("tipo_lancamento") or "").lower()})]


# ------------------------------------------------------------------ 3: Apple
def apple_music(titulo: str, artista: str = "", album: str = "",
                ano: Optional[int] = None) -> List[Capa]:
    saida = []
    for faixa in itunes.faixas_capa(titulo, artista, album, ano):
        saida.append(Capa(url=faixa["capa_url"], fonte="itunes",
                          prioridade=PRIORIDADE["itunes"], album=faixa["album"],
                          artista=faixa["artista"], titulo=faixa["titulo"],
                          ano=faixa["ano"], observacao="Apple Music / iTunes",
                          extra={"tipo_lancamento": faixa.get("tipo_lancamento") or ""}))
    return saida


# ------------------------------------------------------------------ 4: Deezer
def deezer(titulo: str, artista: str = "", album: str = "",
           ano: Optional[int] = None) -> List[Capa]:
    """API pública do Deezer (sem chave). Só aceita com artista batendo."""
    if not titulo:
        return []
    termo = f"{artista} {titulo}".strip()
    url = ("https://api.deezer.com/search?" +
           urllib.parse.urlencode({"q": termo, "limit": 25}))
    dados = _get_json(url, "deezer")
    if not isinstance(dados, dict):
        return []
    alvo_artista, alvo_album = normalizar(artista), normalizar(album)
    from .correspondencia import pontuar
    saida: List[Capa] = []
    urls = set()
    tipos_album: Dict[str, str] = {}
    falha_detalhes = False
    # A pesquisa costuma listar muitos álbuns antes do single. Os detalhes são
    # limitados a quatro lançamentos, então consultar primeiro os nomes que
    # parecem com o título. O nome NÃO confirma o tipo: a API ainda precisa
    # informar record_type=single antes de a imagem ser aceita.
    alvo_titulo = normalizar(titulo)
    def prioridade(item):
        alb = item.get('album') or {}
        nome = normalizar(alb.get('title') or '')
        tipo = str(alb.get('record_type') or '').lower()
        return 0 if tipo == 'single' or nome in (alvo_titulo, alvo_titulo + ' single') else 1
    for item in sorted(dados.get("data") or [], key=prioridade):
        alb = item.get("album") or {}
        nome_album = str(alb.get("title") or "")
        nome_artista = str((item.get("artist") or {}).get("name") or "")
        capa = str(alb.get("cover_xl") or alb.get("cover_big") or "")
        if not capa or capa in urls:
            continue
        if alvo_artista and normalizar(nome_artista) != alvo_artista:
            continue                      # portão: artista tem que ser o mesmo
        if alvo_album and alvo_album not in normalizar(nome_album) \
                and normalizar(nome_album) not in alvo_album:
            continue
        if not pontuar(titulo, artista, album, cand={"titulo": item.get("title") or "",
                       "artista": nome_artista, "album": nome_album}).aprovado:
            continue
        tipo = str(alb.get("record_type") or "").lower()
        album_id = str(alb.get("id") or "")
        if not tipo and album_id.isdigit():
            if album_id not in tipos_album and len(tipos_album) < 4 and not falha_detalhes:
                detalhe = _get_json(f"https://api.deezer.com/album/{album_id}", "deezer", tentativas=1, timeout=8)
                if detalhe is None:
                    falha_detalhes = True
                tipos_album[album_id] = str((detalhe or {}).get("record_type") or "").lower() if isinstance(detalhe, dict) else ""
            tipo = tipos_album.get(album_id, "")
        urls.add(capa)
        saida.append(Capa(url=capa, fonte="deezer", prioridade=PRIORIDADE["deezer"],
                          album=nome_album, artista=nome_artista,
                          ano=None, titulo=str(item.get("title") or ""),
                          score_provedor=0.80, observacao="Deezer",
                          extra={"tipo_lancamento": tipo}))
        if len(saida) >= 8:
            break
    return saida


# ------------------------------------------------------------------ 5: Discogs
def token_discogs() -> str:
    """Token opcional (env DISCOGS_TOKEN ou arquivo discogs.txt na raiz)."""
    do_ambiente = (os.environ.get("DISCOGS_TOKEN") or "").strip()
    if do_ambiente:
        return do_ambiente
    try:
        arquivo = Path(RAIZ) / "discogs.txt"
        if arquivo.exists():
            return arquivo.read_text(encoding="utf-8").strip().splitlines()[0].strip()
    except (OSError, IndexError):
        return ""
    return ""


def discogs(titulo: str, artista: str = "", album: str = "",
            ano: Optional[int] = None) -> List[Capa]:
    # O resultado de pesquisa do Discogs é um lançamento, não confirma a
    # faixa. Não fabricar título/artista com a consulta para passar os filtros.
    return []


# ------------------------------------------------------------------ 6: miniatura
def miniatura(url: str) -> List[Capa]:
    """Thumbnail do vídeo. **Não é capa oficial** — só se o usuário mandar."""
    if not url:
        return []
    return [Capa(url=url, fonte="miniatura do vídeo", prioridade=PRIORIDADE["miniatura"],
                 frontal=False, score_provedor=0.30,
                 observacao="miniatura do vídeo (não é capa oficial)")]


# ------------------------------------------------------------------ 7: Spotify
def referencia_spotify(url_ou_id: str = "") -> str:
    """Devolve o link do Spotify como REFERÊNCIA de conferência, nunca imagem.

    A proposta é explícita: Spotify serve para o usuário comparar, jamais para
    baixar ou incorporar capa.
    """
    texto = (url_ou_id or "").strip()
    if not texto:
        return ""
    if texto.startswith("http"):
        return texto
    return f"https://open.spotify.com/search/{urllib.parse.quote(texto)}"


PROVEDORES = {
    "coverartarchive_confirmado": caa_album_confirmado,
    "coverartarchive": caa_busca,
    "itunes": apple_music,
    "deezer": deezer,
    "discogs": discogs,
}


def disponiveis(fontes: Optional[List[str]] = None) -> List[str]:
    """Quais provedores estão habilitados (e têm como funcionar agora)."""
    fontes = fontes or ["coverartarchive", "itunes"]
    saida = []
    for nome in fontes:
        if nome == "discogs" and not token_discogs():
            continue
        if nome in PROVEDORES:
            saida.append(nome)
    return saida

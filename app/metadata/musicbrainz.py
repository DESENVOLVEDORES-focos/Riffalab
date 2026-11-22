"""Metadados pela MusicBrainz + capas pela Cover Art Archive (ambas livres).

A MusicBrainz pede 1 requisição por segundo por cliente: usamos um lock.
Erros 404 (sem capa / release inexistente) NÃO são repetidos — só falhas
temporárias (5xx, timeout) entram em nova tentativa.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from ..texto import normalizar, similaridade

UA = "RiffLab/0.1 ( uso local )"
BASE = "https://musicbrainz.org/ws/2"
CAA = "https://coverartarchive.org"
TIMEOUT = 25

_lock = threading.Lock()
_ultimo = 0.0


class SemConteudo(LookupError):
    """O recurso não existe (404) — não vale a pena tentar de novo."""


def _get(url: str, tentativas: int = 2) -> Any:
    """GET com limite de 1 req/s e nova tentativa apenas em falhas temporárias."""
    global _ultimo
    ultimo_erro: Optional[Exception] = None
    for tentativa in range(tentativas):
        with _lock:
            espera = 1.05 - (time.time() - _ultimo)
            if espera > 0:
                time.sleep(espera)
            _ultimo = time.time()
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return json.loads(resp.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            if e.code in (400, 404):
                raise SemConteudo(f"HTTP {e.code}: {url}") from e
            ultimo_erro = e
            time.sleep(1.2 * (tentativa + 1))
        except Exception as e:                                   # noqa: BLE001
            ultimo_erro = e
            time.sleep(1.2 * (tentativa + 1))
    raise ultimo_erro if ultimo_erro else RuntimeError("falha na MusicBrainz")


def _artista(creditos: List[Dict[str, Any]]) -> str:
    nomes = []
    for c in creditos or []:
        nome = c.get("name") or (c.get("artist") or {}).get("name")
        if nome:
            nomes.append(nome)
    return " & ".join(nomes)


def buscar_gravacao(titulo: str, artista: str = "", album: str = "",
                    limite: int = 4, somente_single: bool = False,
                    todos_singles: bool = False) -> List[Dict[str, Any]]:
    """Pesquisa gravações e escolhe, para cada uma, o release mais provável.

    Se `album` for informado, releases com nome parecido têm prioridade
    (evita pegar coletâneas/ao vivo quando existe o álbum de estúdio).

    Cada resultado traz `confianca` (0-1) calculada de verdade:
    similaridade do título + do artista + a nota que a própria MusicBrainz deu.
    Gravações com título diferente ou artista diferente são DESCARTADAS — antes
    a busca só mandava `recording:"Take Me Away"` e a primeira capa frontal
    servia, o que rendia capa de outra música (Insane Clown Posse no lugar de
    Christina Vidal, por exemplo).
    """
    partes = []
    if titulo:
        partes.append(f'recording:"{titulo}"')
    if artista:
        partes.append(f'artist:"{artista}"')
    if album:
        partes.append(f'release:"{album}"')
    consulta = " AND ".join(partes) or titulo
    params = urllib.parse.urlencode({"query": consulta, "fmt": "json",
                                     "limit": max(limite, 6)})
    try:
        dados = _get(f"{BASE}/recording/?{params}")
    except Exception:
        return []

    alvo_album = normalizar(album)
    saida: List[Dict[str, Any]] = []
    for rec in dados.get("recordings") or []:
        releases = rec.get("releases") or []
        if not releases:
            continue
        melhor_rel, melhor_nota = None, -1.0
        singles = []
        for rel in releases:
            tipo = str((rel.get("release-group") or {}).get("primary-type") or "")
            if somente_single and tipo.lower() != "single":
                continue
            nota = 0.0
            if alvo_album:
                nome_rel = normalizar(rel.get("title") or "")
                if nome_rel == alvo_album:
                    nota += 2.0
                elif alvo_album in nome_rel or nome_rel in alvo_album:
                    nota += 1.2
            if rel.get("date"):
                nota += 0.3
            if rel.get("track-count") and 5 <= int(rel["track-count"]) <= 25:
                nota += 0.2                      # álbum, não coletânea gigante
            if (rel.get("release-group") or {}).get("primary-type") == "Album":
                nota += 0.5
            if somente_single and todos_singles and rel.get("id"):
                singles.append((rel, nota))
            if nota > melhor_nota:
                melhor_rel, melhor_nota = rel, nota
        if not melhor_rel:
            continue
        nome_rec = rec.get("title") or ""
        artista_rec = _artista(rec.get("artist-credit") or []) or ""
        sim_titulo = similaridade(titulo, nome_rec)
        sim_artista = (similaridade(artista, artista_rec) if artista else 0.0)
        if sim_titulo < 0.85:
            continue                                  # outra música
        if artista and sim_artista < 0.55:
            continue                                  # outra música, mesmo nome
        if not artista and not album:
            # sem artista/álbum só aceitamos título idêntico E nota alta da MB
            if sim_titulo < 0.99 or int(rec.get("score") or 0) < 90:
                continue
        confianca = min(1.0, (sim_titulo * 0.55) + (sim_artista * 0.35)
                        + (min(int(rec.get("score") or 0), 100) / 100.0) * 0.10)
        for melhor_rel, melhor_nota in (singles if somente_single and todos_singles else [(melhor_rel, melhor_nota)]):
            saida.append({
                "titulo": nome_rec or titulo,
                "artista": artista_rec or artista,
                "confianca": round(confianca, 3),
                "album": melhor_rel.get("title") or "",
                "album_score": round(melhor_nota, 2),
                "tipo_lancamento": str((melhor_rel.get("release-group") or {}).get("primary-type") or ""),
                "release_id": melhor_rel.get("id"),
                "release_group": (melhor_rel.get("release-group") or {}).get("id"),
                "ano": int((melhor_rel.get("date") or "0")[:4] or 0) or None,
                "pais": melhor_rel.get("country") or "",
                "score_mb": int(rec.get("score") or 0),
            })
    saida.sort(key=lambda r: (r.get("confianca") or 0, r.get("album_score") or 0,
                              r.get("score_mb") or 0), reverse=True)
    # um mesmo release não precisa aparecer duas vezes
    vistos, unicos = set(), []
    for item in saida:
        if item["release_id"] in vistos:
            continue
        vistos.add(item["release_id"])
        unicos.append(item)
    return unicos


def detalhes_release(release_id: str, titulo_faixa: str = "") -> Dict[str, Any]:
    """Álbum, ano, gênero e a posição da faixa dentro do disco."""
    if not release_id:
        return {}
    try:
        params = urllib.parse.urlencode({"inc": "recordings artist-credits genres", "fmt": "json"})
        dados = _get(f"{BASE}/release/{release_id}?{params}")
    except SemConteudo:
        return {}
    except Exception:
        return {}

    alvo = normalizar(titulo_faixa)
    faixa = disco = None
    midias = dados.get("media") or []
    if alvo:
        for i, media in enumerate(midias, start=1):
            for t in media.get("tracks") or []:
                nome_faixa = normalizar(t.get("title") or "")
                if nome_faixa == alvo or nome_faixa.startswith(alvo) or alvo.startswith(nome_faixa):
                    numero = str(t.get("number") or "")
                    digitos = "".join(ch for ch in numero if ch.isdigit())
                    faixa = digitos or numero
                    disco = media.get("position") or i
                    break
            if faixa:
                break
    generos = dados.get("genres") or []
    return {
        "album": dados.get("title") or "",
        "ano": int((dados.get("date") or "0")[:4] or 0) or None,
        "pais": dados.get("country") or "",
        "faixa": int(faixa) if str(faixa or "").isdigit() else None,
        "disco": int(disco) if str(disco or "").isdigit() else None,
        "total_faixas": sum(int(m.get("track-count") or 0) for m in midias) or None,
        "genero": generos[0]["name"] if generos else "",
        "artista": _artista(dados.get("artist-credit") or []),
    }


def capas_release(release_id: str = "", release_group: str = "") -> List[Dict[str, Any]]:
    """Imagens do Cover Art Archive (frontal primeiro). Aceita release ou grupo."""
    urls = []
    if release_id:
        urls.append(f"{CAA}/release/{release_id}")
    if release_group:
        urls.append(f"{CAA}/release-group/{release_group}")
    for url in urls:
        try:
            dados = _get(url)
        except Exception:
            continue
        imagens = []
        for img in dados.get("images") or []:
            mini = img.get("thumbnails") or {}
            link = mini.get("1200") or mini.get("large") or mini.get("500") or img.get("image") or ""
            if not link:
                continue
            link = link.replace("http://", "https://", 1)      # sempre https
            imagens.append({
                "url": link,
                "frontal": bool(img.get("front")),
                "tipos": img.get("types") or [],
                "comentario": img.get("comment") or "",
                "aprovada": img.get("approved", True),
            })
        if imagens:
            imagens.sort(key=lambda i: (not i["frontal"], not i["aprovada"]))
            return imagens
    return []


def buscar_release_group(album: str, artista: str = "", ano: Optional[int] = None,
                         limite: int = 5) -> List[Dict[str, Any]]:
    """Procura o *álbum* (release-group) por nome + artista — usado para
    CONFIRMAR o álbum que a IA identificou antes de pegar a capa."""
    if not album:
        return []
    partes = [f'releasegroup:"{album}"']
    if artista:
        partes.append(f'artist:"{artista}"')
    consulta = " AND ".join(partes)
    url = (f"{BASE}/release-group/?query={urllib.parse.quote(consulta)}"
           f"&fmt=json&limit={max(1, min(20, limite))}")
    try:
        dados = _get(url)
    except Exception:                                             # noqa: BLE001
        return []
    alvo = normalizar(album)
    saida: List[Dict[str, Any]] = []
    for grupo in dados.get("release-groups") or []:
        nome = grupo.get("title") or ""
        nome_norm = normalizar(nome)
        if alvo and alvo not in nome_norm and nome_norm not in alvo:
            continue                      # não é o álbum pedido
        try:
            ano_grupo = int((grupo.get("first-release-date") or "")[:4])
        except ValueError:
            ano_grupo = None
        saida.append({
            "mbid": grupo.get("id") or "",
            "album": nome,
            "artista": _artista(grupo.get("artist-credit") or []),
            "ano": ano_grupo,
            "tipo": grupo.get("primary-type") or "",
            "score": int(grupo.get("score") or 0),
            "ano_bate": bool(ano and ano_grupo and abs(int(ano) - ano_grupo) <= 1),
        })
    # prioriza quem bate o ano e a pontuação da busca
    saida.sort(key=lambda g: (not g["ano_bate"], -g["score"]))
    return saida


def melhor_capa(titulo: str, artista: str = "", album: str = "", somente_single: bool = False) -> Dict[str, Any]:
    """Capa frontal do álbum correspondente (ou {} se não houver).

    Sem artista **ou** álbum não há como provar que a gravação é a mesma
    música: nesse caso devolve {} de propósito. Era assim que uma busca por
    "Take Me Away" trazia a capa de um álbum de techno aleatório.
    """
    if not artista and not album:
        return {}
    alvo_album = normalizar(album)
    # Singles podem estar além dos primeiros resultados dominados por álbuns;
    # examinar mais gravações sem aceitar lançamentos de tipo desconhecido.
    limite = 25 if somente_single else 3
    for grav in buscar_gravacao(titulo, artista, album, limite=limite, somente_single=somente_single):
        # confiança baixa = não sabemos se é a mesma música: não usa a capa
        if float(grav.get("confianca") or 0) < 0.70:
            continue
        # se o usuário sabe o álbum, não aceita capa de outro disco
        if alvo_album and grav.get("album"):
            nome = normalizar(grav["album"])
            if alvo_album not in nome and nome not in alvo_album:
                continue
        for capa in capas_release(grav.get("release_id"), grav.get("release_group")):
            if capa["frontal"]:
                return {**capa, "titulo": grav.get("titulo"), "album": grav.get("album"), "ano": grav.get("ano"),
                        "artista": grav.get("artista") or artista,
                        "confianca": grav.get("confianca"),
                        "tipo_lancamento": grav.get("tipo_lancamento") or "",
                        "release_id": grav.get("release_id"), "fonte": "coverartarchive"}
    return {}

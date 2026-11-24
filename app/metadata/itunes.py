"""Metadados e capas pela API pública de catálogo do iTunes/Apple Music.

Sem chave de API. Devolve arte de até 3000x3000 (pedimos 1200 para ficar
nítido em qualquer tela e não pesar no arquivo final).
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

from ..texto import ano_de, normalizar, similaridade

API = "https://itunes.apple.com/search"
UA = "RiffLab/0.1 (uso local)"
TIMEOUT = 20


def _get(url: str) -> Dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def buscar(termo: str, limite: int = 10, pais: str = "US", entidade: str = "song") -> List[Dict[str, Any]]:
    params = urllib.parse.urlencode({"term": termo, "entity": entidade,
                                     "limit": max(1, min(50, limite)), "country": pais})
    try:
        return list(_get(f"{API}?{params}").get("results") or [])
    except Exception as exc:
        from ..logging_setup import registrar_erro
        registrar_erro('Catálogo iTunes', f'{type(exc).__name__}: {exc}')
        return []


def arte(item: Dict[str, Any], tamanho: int = 1200) -> str:
    url = item.get("artworkUrl100") or item.get("artworkUrl60") or ""
    if not url:
        return ""
    for alvo in ("100x100bb", "60x60bb", "100x100", "170x170bb", "600x600bb"):
        if alvo in url:
            return url.replace(alvo, f"{tamanho}x{tamanho}bb")
    return url


def melhor_faixa(titulo: str, artista: str = "", album: str = "",
                 ano: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """Procura a faixa no catálogo e devolve a de maior similaridade.

    Portões (o que evita "capa de outra música"):
      * o TÍTULO tem que bater de verdade (>= 0.85);
      * se sabemos o artista, ele tem que bater (>= 0.55) — título igual com
        artista diferente é OUTRA música (existem dezenas de "Take Me Away");
      * se sabemos o álbum, ele tem que bater (>= 0.60);
      * sem artista e sem álbum não há como provar nada: devolve None em vez de
        arriscar (regra "não inventar" da proposta §3).
    """
    artista = (artista or "").strip()
    album = (album or "").strip()
    consulta = " ".join(x for x in (artista, titulo, album) if x)
    resultados = buscar(consulta, limite=15)
    if not resultados and album:
        resultados = buscar(f"{album} {artista}".strip(), limite=15)
    if not resultados:
        return None

    melhor, melhor_score = None, 0.0
    from .correspondencia import pontuar
    for item in resultados:
        candidato = {"titulo": item.get("trackName") or "", "artista": item.get("artistName") or "",
                     "album": item.get("collectionName") or ""}
        if not pontuar(titulo, artista, album, cand=candidato).aprovado:
            continue  # outra versão, artista ou lançamento
        s_titulo = similaridade(titulo, item.get("trackName") or "")
        if s_titulo < 0.85:
            continue                                  # nem é a mesma música
        s_artista = similaridade(artista, item.get("artistName") or "") if artista else 0.0
        s_album = similaridade(album, item.get("collectionName") or "") if album else 0.0

        if artista and s_artista < 0.55:
            continue                                  # outra música, mesmo título
        if album and s_album < 0.60:
            continue                                  # outro álbum
        if not artista and not album:
            return None                               # nada confirmado → sem capa

        score = s_titulo * 0.6 + s_artista * 0.3 + s_album * 0.1
        ano_item = ano_de(item.get("releaseDate") or "")
        if ano and ano_item and abs(int(ano) - ano_item) <= 1:
            score += 0.05                             # só quando o ano bate
        if score > melhor_score:
            melhor, melhor_score = item, score

    if not melhor or melhor_score < 0.60:
        return None

    return {
        "titulo": melhor.get("trackName") or titulo,
        "artista": melhor.get("artistName") or artista,
        "album": melhor.get("collectionName") or album,
        "artista_album": melhor.get("collectionArtistName") or "",
        "ano": int((melhor.get("releaseDate") or "0")[:4] or 0) or None,
        "faixa": melhor.get("trackNumber"),
        "total_faixas": melhor.get("trackCount"),
        "disco": melhor.get("discNumber"),
        "genero": melhor.get("primaryGenreName") or "",
        "capa_url": arte(melhor),
        "score": round(min(1.0, melhor_score), 3),
        "fonte": "itunes",
        "album_id": melhor.get("collectionId"),
    }


def faixas_capa(titulo: str, artista: str = "", album: str = "",
                 ano: Optional[int] = None, incluir_albuns: bool = False) -> List[Dict[str, Any]]:
    """Candidatos reais do catálogo; a validação final é compartilhada."""
    consulta = " ".join(x for x in (artista, titulo, album) if x)
    if not titulo or not (artista or album):
        return []
    from .correspondencia import pontuar
    saida = []
    indice_por_url = {}
    # A mesma imagem pode estar associada tanto a um álbum como a um single.
    # Guardar primeiro o álbum e descartar o single pela URL faz a etapa
    # seguinte rejeitar ambos, mesmo quando o catálogo identifica um single.
    for pais in ('US', 'BR'):
        for item in buscar(consulta, limite=50, pais=pais):
            url = arte(item)
            if not url:
                continue
            candidato = {"titulo": item.get("trackName") or "",
                         "artista": item.get("artistName") or "",
                         "album": item.get("collectionName") or ""}
            if not pontuar(titulo, artista, album, cand=candidato).aprovado:
                continue
            novo = {"titulo": candidato['titulo'], "artista": candidato['artista'],
                    "album": candidato['album'],
                    "ano": ano_de(item.get("releaseDate") or ""),
                    # O sufixo do catálogo é indício, não prova.
                    "tipo_lancamento": ("single" if re.search(
                        r"(?:\s*-\s*single|\s*\(single\))\s*$",
                        candidato['album'], re.I) else ""),
                    "capa_url": url}
            if incluir_albuns and not novo['tipo_lancamento']:
                # collectionType=Album inclui singles; não confirma o tipo. Nomes de EP não
                # são classificados como álbum. A edição original não é provada.
                tipo = str(item.get('collectionType') or '').lower()
                nome = candidato['album']
                if tipo == 'album' and not re.search(r'(?:\s*-\s*ep|\s*\(ep\))\s*$', nome, re.I):
                    novo['tipo_lancamento'] = 'colecao'
            chave = (url, novo['tipo_lancamento'], novo['album']) if incluir_albuns else url
            indice = indice_por_url.get(chave)
            if indice is None:
                indice_por_url[chave] = len(saida)
                saida.append(novo)
            elif not incluir_albuns and novo['tipo_lancamento'] == 'single' and saida[indice]['tipo_lancamento'] != 'single':
                saida[indice] = novo
    return saida


def metadados_album(album_id: int) -> Dict[str, Any]:
    """Detalhes de um álbum (para número de faixa/ano quando disponível)."""
    params = urllib.parse.urlencode({"id": album_id, "entity": "song", "country": "US"})
    try:
        dados = _get(f"https://itunes.apple.com/lookup?{params}")
        itens = dados.get("results") or []
        return itens[0] if itens else {}
    except Exception:
        return {}

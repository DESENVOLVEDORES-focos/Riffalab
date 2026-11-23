"""Utilidades de texto: normalização para comparação e formatação."""
from __future__ import annotations

import difflib
import re
import unicodedata
from typing import Optional

_RE_NAO_ALNUM = re.compile(r"[^a-z0-9 ]+")
_RE_ESPACOS = re.compile(r"\s+")

def normalizar(texto: str) -> str:
    """minúsculas, sem acento, sem pontuação — para comparação."""
    if not texto:
        return ""
    s = unicodedata.normalize("NFD", str(texto))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.lower()
    s = _RE_NAO_ALNUM.sub(" ", s)
    return _RE_ESPACOS.sub(" ", s).strip()


def similaridade(a: str, b: str) -> float:
    """0..1 — quão parecidos são dois textos (já normalizados por dentro)."""
    a, b = normalizar(a), normalizar(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if a in b or b in a:
        return 0.92
    return difflib.SequenceMatcher(None, a, b).ratio()


def relevancia(consulta: str, *campos: str, pesos=None) -> float:
    """Melhor similaridade entre a consulta e vários campos do resultado."""
    consulta_n = normalizar(consulta)
    if not consulta_n:
        return 0.0
    pesos = pesos or [1.0] * len(campos)
    melhor = 0.0
    for campo, peso in zip(campos, pesos):
        if not campo:
            continue
        s = similaridade(consulta_n, campo)
        # todos os termos da consulta aparecendo no campo contam bastante
        if all(t in normalizar(campo) for t in consulta_n.split()):
            s = max(s, 0.85)
        melhor = max(melhor, s * peso)
    return melhor


def limpar_titulo(titulo: str) -> str:
    """Remove apenas marcadores de vídeo, preservando partes do nome da música.

    Remix, feat., versão ao vivo e outras expressões entre parênteses podem
    fazer parte do título e não podem ser descartadas automaticamente.
    """
    if not titulo:
        return ""
    ruido = (r"(?:official\s*(?:music\s*)?(?:video|audio)|"
             r"(?:official\s*)?lyric\s*video|video\s*oficial|clipe\s*oficial|"
             r"visualizer|hd|hq|4k|lyrics|lyric video|legendado|tradu[çc][ãa]o)")
    s = re.sub(r"[\(\[\{]\s*" + ruido + r"\s*[\)\]\}]", " ", titulo,
               flags=re.IGNORECASE)
    s = re.sub(r"\s+[-–—|]\s*" + ruido + r"\s*$", " ", s, flags=re.IGNORECASE)
    s = _RE_ESPACOS.sub(" ", s).strip(" -–—|.")
    return s or titulo.strip()


def separar_artista_titulo(nome: str) -> tuple[str, str]:
    """Tenta dividir 'Artista - Título' (padrão comum de vídeos)."""
    if not nome:
        return "", ""
    m = re.match(r"^\s*(?P<artista>[^\-–—|]{2,60}?)\s*[-–—|]\s*(?P<titulo>.+)$", nome)
    if m:
        return m.group("artista").strip(), m.group("titulo").strip()
    return "", nome.strip()


def ano_de(texto: Optional[str]) -> Optional[int]:
    if not texto:
        return None
    m = re.search(r"(19|20)\d{2}", str(texto))
    return int(m.group(0)) if m else None


def abreviar(texto: str, limite: int = 60) -> str:
    if not texto:
        return ""
    return texto if len(texto) <= limite else texto[: limite - 1].rstrip() + "…"


# ---------------------------------------------------------------------------
def parece_canal(nome: str) -> bool:
    """Diz se o "artista" é, na verdade, nome de canal/selo — não de intérprete.

    Vídeos do YouTube trazem o canal quando não há padrão "Artista - Título".
    Usar "DisneyMusicVEVO" como artista faz a busca de capa escolher outra
    música com o mesmo nome (foi exatamente o caso de "Take Me Away").
    """
    if not nome:
        return True
    n = normalizar(nome)
    if not n:
        return True
    sinais = ("vevo", "topic", "official", "oficial", "records", "record label",
              "music", "musica", "canal", "channel", "tv", "hd", "lyrics", "letra",
              "disney", "soundtrack", "trilha", "karaoke", "cover channel")
    if any(sinal in n for sinal in sinais):
        return True
    return len(n) <= 3


# palavras que indicam que o lado esquerdo é o TÍTULO (não o artista)
_NAO_ARTISTA = ("live", "ao vivo", "concert", "concerto", "festival", "unplugged",
                "show", "session", "bootleg", "remix", "cover", "tribute",
                "official video", "video clip", "clipe")


def artista_do_titulo(titulo: str) -> tuple[str, str]:
    """'Artista - Título' → (artista, titulo); ('', '') quando não é confiável.

    Só aceita quando o lado esquerdo *parece* um nome de artista: curto (até 40
    caracteres / 5 palavras), sem palavras de "ao vivo" e sem cara de canal.
    Assim "Take Me Away (Live at Wembley 2003) - Christina Vidal" não vira
    artista "Take Me Away (Live at Wembley 2003)".
    """
    esquerda, direita = separar_artista_titulo(titulo or "")
    if not esquerda or not direita:
        return "", ""
    if len(esquerda) > 40 or len(esquerda.split()) > 5:
        return "", ""
    alvo = normalizar(esquerda)
    if any(palavra in alvo for palavra in _NAO_ARTISTA):
        return "", ""
    if parece_canal(esquerda) or esquerda[:1].isdigit():
        return "", ""
    return esquerda, direita

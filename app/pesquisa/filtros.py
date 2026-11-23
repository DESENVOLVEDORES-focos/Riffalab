"""Filtro inteligente: prioriza estúdio, avisa (sem esconder) sobre shows.

Regras da proposta §3:

* usa os metadados do yt-dlp (`live_status`, `is_live`, `was_live`,
  `availability`, `playable_in_embed`, `duration`) **e** palavras-chave do
  título — nenhum dos dois isolado é prova;
* nada é descartado em silêncio: quem é filtrado vai para a lista
  `filtrados` e pode reaparecer com "Mostrar resultados filtrados";
* em dúvida, marca como **possível** gravação ao vivo (aviso), não como certa.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Sequence, Tuple

from ..models import TrackResult
from ..texto import normalizar, similaridade

# --- sinais de "ao vivo" no título/descrição -------------------------------
# (peso, expressão) — quanto maior o peso, mais forte o indício
_SINAIS_TITULO: Sequence[Tuple[float, str]] = (
    (0.55, r"\blive\s*(?:at|in|from|@)\b"),
    (0.50, r"\bao\s*vivo\b"),
    (0.50, r"\bmtv\s*unplugged\b"),
    (0.45, r"\bfull\s*concert\b"),
    (0.45, r"\bconcert\b"),
    (0.45, r"\bfestival\b"),
    (0.40, r"\blive\s*(?:performance|session|show|version|stream)\b"),
    (0.35, r"\b(?:ao\s*vivo|live)\b"),
    (0.35, r"\btour\b"),
    (0.30, r"\bshow\b"),
    (0.30, r"\bunplugged\b"),
    (0.30, r"\bbootleg\b"),
    (0.28, r"\baudience\b"),
    (0.25, r"\bacoustic\s*live\b"),
    (0.22, r"\bperformance\b"),
    (0.20, r"\bcrowd\b"),
    (0.18, r"\b(?:live\s*)?stream(?:ing)?\b"),
)

# palavras que, no MEIO de um título de estúdio, são inofensivas
_CONTRAEXEMPLOS = (
    r"\blive\s*and\s*let\s*die\b",
    r"\blive\s*forever\b",
    r"\blive\s*to\s*tell\b",
    r"\blive\s*like\s*you\s*re\s*dying\b",
)

_VIVO_STATUS = {"is_live", "is_upcoming", "post_live", "was_live"}


@dataclass
class Analise:
    """Resultado da análise de um resultado de pesquisa."""
    pontos_ao_vivo: float = 0.0
    certeza: str = ""                       # "" | "provavel" | "confirmado"
    sinais: List[str] = field(default_factory=list)
    nota: float = 0.0                       # prioridade geral (0-1)
    motivos: List[str] = field(default_factory=list)

    @property
    def ao_vivo(self) -> bool:
        return bool(self.certeza)


def _texto_para_analise(r: TrackResult) -> str:
    """Texto onde procurar os indícios de ao vivo.

    Usa o título ORIGINAL do vídeo (`extra["titulo_original"]`) além do título
    já limpo: versões antigas de `limpar_titulo` removiam parênteses e apagavam justamente
    "(Live at Wembley)" / "(Ao Vivo)" — que são a pista mais forte.
    """
    extra = r.extra or {}
    pedacos = [r.titulo or "", extra.get("titulo_original") or "",
               r.artista or "", r.canal or "",
               str(extra.get("descricao") or "")]
    return normalizar(" ".join(str(p) for p in pedacos if p))


def _sinais_do_titulo(texto: str) -> Tuple[float, List[str]]:
    if not texto:
        return 0.0, []
    limpo = texto
    for contra in _CONTRAEXEMPLOS:
        limpo = re.sub(contra, " ", limpo)
    pontos, achados = 0.0, []
    for peso, padrao in _SINAIS_TITULO:
        achado = re.search(padrao, limpo)
        if achado:
            achados.append(achado.group(0).strip())
            pontos = min(0.95, pontos + peso)
    return pontos, achados


def _sinais_do_status(r: TrackResult) -> Tuple[float, List[str]]:
    """live_status/is_live/was_live — a fonte mais confiável quando existe."""
    extra = r.extra or {}
    status = str(extra.get("live_status") or "").lower()
    sinais: List[str] = []
    pontos = 0.0
    if extra.get("is_live") is True:
        pontos = 1.0
        sinais.append("transmitindo ao vivo agora")
    elif status in _VIVO_STATUS:
        pontos = 0.9 if status != "was_live" else 0.8
        sinais.append({
            "is_live": "transmissão ao vivo",
            "is_upcoming": "transmissão futura (agendada)",
            "post_live": "fim de transmissão ao vivo",
            "was_live": "era transmissão ao vivo",
        }.get(status, status))
    elif extra.get("was_live") is True:
        pontos = 0.8
        sinais.append("era transmissão ao vivo")
    if extra.get("availability") in ("private", "premium_only", "subscriber_only"):
        sinais.append(f"disponibilidade restrita ({extra['availability']})")
    return pontos, sinais


def _bonus_oficial(r: TrackResult) -> Tuple[float, List[str]]:
    """Canal oficial / tópico oficial = mais chance de áudio de estúdio."""
    canal = normalizar(r.canal or r.artista or "")
    artista = normalizar(r.artista or "")
    motivos: List[str] = []
    bonus = 0.0
    if not canal:
        return 0.0, motivos
    if canal.endswith("topic"):
        bonus += 0.22
        motivos.append("canal de tópico (áudio oficial)")
    if "vevo" in canal:
        bonus += 0.18
        motivos.append("canal VEVO")
    if "official" in canal or "oficial" in canal:
        bonus += 0.15
        motivos.append("canal oficial")
    if artista and similaridade(canal, artista) >= 0.75:
        bonus += 0.12
        motivos.append("canal do próprio artista")
    if (r.extra or {}).get("uploader_id") and "topic" in str(r.extra.get("uploader_id")):
        bonus += 0.05
    return min(0.3, bonus), motivos


def _nota_audio(r: TrackResult) -> float:
    """Duração plausível de música (evita 3 h de show e 20 s de teaser)."""
    d = float(r.duracao_s or 0)
    if not d:
        return 0.0
    if 90 <= d <= 600:
        return 0.12
    if 45 <= d < 90 or 600 < d <= 900:
        return 0.05
    if d > 1500:                     # 25 min+: quase sempre show/compilação
        return -0.2
    return 0.0


def analisar(r: TrackResult, consulta: str = "") -> Analise:
    """Calcula sinais de 'ao vivo' e a nota de prioridade de um resultado."""
    pontos_status, sinais_status = _sinais_do_status(r)
    pontos_titulo, sinais_titulo = _sinais_do_titulo(_texto_para_analise(r))
    bonus, motivos_bonus = _bonus_oficial(r)

    # o status do yt-dlp manda; o título só reforça
    pontos = max(pontos_status, pontos_titulo * 0.85)
    if pontos_status and pontos_titulo:
        pontos = min(1.0, pontos + 0.1)

    # o `live_status` do yt-dlp é prova: was_live/is_live/post_live/is_upcoming
    if pontos_status >= 0.80:
        certeza = "confirmado"
    elif pontos >= 0.42:
        certeza = "provavel"
    elif pontos_status:
        certeza = "provavel"
    else:
        certeza = ""

    sinais = sinais_status + [f"título: “{s}”" for s in sinais_titulo]

    nota = 0.5 + bonus + _nota_audio(r) - (0.55 if certeza == "confirmado"
                                           else 0.30 if certeza == "provavel" else 0.0)
    if consulta:
        nota += 0.15 * similaridade(consulta, f"{r.artista} {r.titulo}")
    if (r.extra or {}).get("playable_in_embed") is False:
        nota -= 0.03
    return Analise(pontos_ao_vivo=round(min(1.0, pontos), 2), certeza=certeza,
                   sinais=sinais, nota=round(max(0.0, min(1.5, nota)), 3),
                   motivos=motivos_bonus)


def aplicar(resultados: Iterable[TrackResult], consulta: str = "",
            evitar_ao_vivo: bool = True, limite_aviso: float = 0.42
            ) -> Tuple[List[TrackResult], List[TrackResult]]:
    """Analisa, ordena e separa em (visíveis, filtrados).

    Nada é apagado: o que cai no filtro vai para a segunda lista, para o botão
    "Mostrar resultados filtrados".
    """
    itens = list(resultados)
    for r in itens:
        analise = analisar(r, consulta)
        r.ao_vivo = analise.ao_vivo
        r.ao_vivo_certeza = analise.certeza
        r.sinais_ao_vivo = analise.sinais
        r.nota_musica = analise.nota
        r.filtrado = bool(evitar_ao_vivo and analise.pontos_ao_vivo >= limite_aviso)
        r.motivos_filtro = (analise.sinais[:3] if r.filtrado else [])

    visiveis = [r for r in itens if not r.filtrado]
    filtrados = [r for r in itens if r.filtrado]
    visiveis.sort(key=lambda r: r.nota_musica, reverse=True)
    filtrados.sort(key=lambda r: r.nota_musica, reverse=True)
    return visiveis, filtrados


def ordenar(resultados: Iterable[TrackResult],
            criterio: str = "relevancia") -> List[TrackResult]:
    """'relevancia' (nota de música: estúdio > clipe > ao vivo) ou 'qualidade'."""
    from ..quality import pontuar

    itens = list(resultados)
    if criterio == "qualidade":
        itens.sort(key=lambda r: pontuar(r.melhor) if r.melhor else -1, reverse=True)
    else:
        itens.sort(key=lambda r: (r.nota_musica,
                                  pontuar(r.melhor) if r.melhor else -1),
                   reverse=True)
    return itens

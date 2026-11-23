"""Pontuação de correspondência entre a música e um candidato (faixa/capa).

A regra da proposta §1.4: **é melhor não colocar capa nenhuma do que colocar a
capa errada**. Por isso existem dois níveis:

* **portões** (`aceitavel`): título obrigatório; artista e álbum obrigatórios
  quando conhecidos. Reprovou → o candidato é descartado;
* **nota** (`pontuar`): entre os aprovados, ordena quem é a melhor edição
  (ano que bate, ISRC/MBID igual, capa frontal, prioridade da fonte).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from ..texto import normalizar, similaridade

# mínimos para aceitar um candidato
MIN_TITULO = 0.85
MIN_ARTISTA = 0.55
MIN_ALBUM = 0.80
MIN_TOTAL = 0.62

PESOS = {"titulo": 0.28, "artista": 0.28, "album": 0.22, "ano": 0.07,
         "identificador": 0.10, "imagem": 0.05}


@dataclass
class Pontuacao:
    total: float = 0.0
    componentes: Dict[str, float] = field(default_factory=dict)
    aprovado: bool = False
    motivos: list = field(default_factory=list)

    def como_dict(self) -> Dict[str, Any]:
        return {"total": round(self.total, 3), "aprovado": self.aprovado,
                **{k: round(v, 3) for k, v in self.componentes.items()},
                "motivos": list(self.motivos)}


def _ano_pontos(ano: Optional[int], outro: Optional[int]) -> float:
    if not ano or not outro:
        return 0.0
    diferenca = abs(int(ano) - int(outro))
    if diferenca == 0:
        return 1.0
    if diferenca == 1:
        return 0.8
    if diferenca <= 3:
        return 0.4
    return 0.0


def versoes(texto: str) -> set[str]:
    """Marcadores de versão que não podem ser trocados silenciosamente."""
    import re
    texto = normalizar(texto or "")
    return {rotulo for rotulo, padrao in (
        ("live", r"\b(?:live|ao vivo|en vivo)\b"),
        ("remix", r"\bremix\b"), ("karaoke", r"\bkaraoke\b"),
        ("instrumental", r"\binstrumental\b"),
        ("acustico", r"\b(?:acoustic|acustico)\b")) if re.search(padrao, texto)}


def pontuar(titulo: str, artista: str = "", album: str = "",
            ano: Optional[int] = None, isrc: str = "", mbid: str = "",
            cand: Optional[Dict[str, Any]] = None,
            imagem_frontal: bool = True) -> Pontuacao:
    """Compara o que sabemos da música com os dados de um candidato."""
    cand = cand or {}
    s_titulo = similaridade(titulo, cand.get("titulo") or "")
    s_artista = similaridade(artista, cand.get("artista") or "") if artista else 0.0
    s_album = similaridade(album, cand.get("album") or "") if album else 0.0
    p_ano = _ano_pontos(ano, cand.get("ano"))

    p_id = 0.0
    if isrc and cand.get("isrc"):
        p_id = 1.0 if str(isrc).upper() == str(cand["isrc"]).upper() else 0.0
    elif mbid and cand.get("mbid"):
        p_id = 1.0 if str(mbid) == str(cand["mbid"]) else 0.0

    componentes = {"titulo": s_titulo, "artista": s_artista, "album": s_album,
                   "ano": p_ano, "identificador": p_id,
                   "imagem": 1.0 if imagem_frontal else 0.25}

    # Não punir ausência de informação que não é conhecida na consulta.
    ativos = ["titulo", "imagem"]
    if artista:
        ativos.append("artista")
    if album:
        ativos.append("album")
    if ano and cand.get("ano"):
        ativos.append("ano")
    if (isrc and cand.get("isrc")) or (mbid and cand.get("mbid")):
        ativos.append("identificador")
    total = sum(componentes[k] * PESOS[k] for k in ativos) / sum(PESOS[k] for k in ativos)

    motivos = []
    aprovado = True
    if s_titulo < MIN_TITULO:
        aprovado = False
        motivos.append(f"título diferente ({s_titulo:.2f})")
    # "Música (ao vivo)" não é automaticamente a gravação de estúdio.
    if versoes(titulo) != versoes(cand.get("titulo")):
        aprovado = False
        motivos.append("versão da faixa diferente")
    if artista and s_artista < MIN_ARTISTA:
        aprovado = False
        motivos.append(f"artista diferente ({s_artista:.2f})")
    if album and s_album < MIN_ALBUM:
        aprovado = False
        motivos.append(f"álbum diferente ({s_album:.2f})")
    if not artista and not album:
        aprovado = False
        motivos.append("sem artista e sem álbum para confirmar")
    if total < MIN_TOTAL:
        aprovado = False
        motivos.append(f"nota total baixa ({total:.2f})")
    if not imagem_frontal:
        motivos.append("imagem não é capa frontal")

    return Pontuacao(total=round(min(1.0, total), 3), componentes=componentes,
                     aprovado=aprovado, motivos=motivos)


def explicacao(p: Pontuacao) -> str:
    """Texto curto para a interface: 'título 1.00 · artista 0.94 · álbum 1.00'."""
    partes = []
    for chave, rotulo in (("titulo", "título"), ("artista", "artista"),
                          ("album", "álbum"), ("ano", "ano"),
                          ("identificador", "identificador"), ("imagem", "imagem")):
        valor = p.componentes.get(chave)
        if valor:
            partes.append(f"{rotulo} {valor:.2f}")
    return "  ·  ".join(partes) or "sem dados para comparar"


def normalizar_nome(valor: str) -> str:
    return normalizar(valor or "")

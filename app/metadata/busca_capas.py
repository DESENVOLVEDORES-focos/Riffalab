"""Busca de capas de single e, somente para revisão, de álbum.

Catálogos e classificações podem estar errados. A escolha é do usuário.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from ..models import CoverResult, Identificacao
from . import capa_validacao, correspondencia, provedores
from .covers import baixar_imagem, salvar_cache


@dataclass
class Avaliacao:
    capa: provedores.Capa
    caminho: str = ""
    largura: int = 0
    altura: int = 0
    score: float = 0.0
    aprovada: bool = False
    motivo: str = ""
    explicacao: str = ""
    componentes: Dict[str, float] = field(default_factory=dict)
    hash_imagem: str = ""

    def como_cover_result(self) -> CoverResult:
        return CoverResult(caminho=self.caminho or None, fonte=self.capa.fonte,
                           largura=self.largura, altura=self.altura,
                           score=round(self.score, 3), album=self.capa.album,
                           artista=self.capa.artista, ano=self.capa.ano,
                           tipo_lancamento=str(self.capa.extra.get('tipo_lancamento') or ''),
                           observacao=self.motivo or
                           ("Lançamento indicado pelo catálogo; confira a imagem. " + self.explicacao))


def _url_em_cache(url: str) -> Optional[str]:
    """Caminho de cache existente para a URL (evita baixar de novo)."""
    import hashlib
    from pathlib import Path

    from ..config import PASTA_CACHE_CAPAS
    chave = hashlib.sha1(url.encode("utf-8")).hexdigest()[:20]
    for ext in (".jpg", ".png", ".webp", ".gif"):
        possivel = Path(PASTA_CACHE_CAPAS) / f"{chave}{ext}"
        if possivel.exists():
            return str(possivel)
    return None


def _obter_imagem(url: str) -> Tuple[Optional[str], bytes]:
    caminho = _url_em_cache(url)
    if caminho:
        try:
            from pathlib import Path
            return caminho, Path(caminho).read_bytes()
        except OSError:
            caminho = None
    dados = baixar_imagem(url)
    if not dados:
        return None, b""
    try:
        destino = salvar_cache(url, dados)
    except OSError:
        return None, b""
    return str(destino), dados


def _identidade_estrita(titulo: str, artista: str, capa: provedores.Capa) -> bool:
    """Evita aceitar Queen como Queens, ou 'One' como 'One More Time'."""
    import difflib
    import re
    from ..texto import normalizar
    def titulo_normal(t):
        t = re.sub(r"\s*(?:[\(\[]\s*|[-–—]\s*)(?:\d{4}\s+)?remaster(?:ed)?(?:\s+\d{4})?\s*[\)\]]?\s*$", "", t or "", flags=re.I)
        return normalizar(t)
    t1, t2 = titulo_normal(titulo), titulo_normal(capa.titulo)
    if not t1 or not t2 or (t1 != t2 and difflib.SequenceMatcher(None, t1, t2).ratio() < .85):
        return False
    def principal(a):
        return normalizar(re.split(r"\s+(?:feat\.?|featuring|ft\.?)\s+", a or "", maxsplit=1, flags=re.I)[0])
    a1, a2 = principal(artista), principal(capa.artista)
    return bool(a1 and a2 and a1 == a2)


def _album_compativel(referencia: str, candidato: str) -> bool:
    """Compara nomes de álbuns para ordenação e aviso, sem excluir edições."""
    import difflib
    import re
    from ..texto import normalizar
    def nome(t):
        # Remove somente qualificadores comuns de edição; não remove o nome.
        t = re.sub(r"\s*[\(\[][^\)\]]*\b(?:deluxe|remaster(?:ed)?|expanded|anniversary)\b[^\)\]]*[\)\]]\s*$", "", t or "", flags=re.I)
        t = re.sub(r"\s*[-–—]\s*(?:\d{4}\s+)?(?:deluxe|remaster(?:ed)?|expanded|anniversary)\b.*$", "", t, flags=re.I)
        return normalizar(t)
    a, b = nome(referencia), nome(candidato)
    return bool(a and b and (a == b or difflib.SequenceMatcher(None, a, b).ratio() >= .90))


def avaliar(capa: provedores.Capa, contexto: Dict[str, Any],
            minimo_lado: int = 300, exigir_quadrada: bool = False) -> Avaliacao:
    """Baixa, valida e pontua um candidato."""
    avaliacao = Avaliacao(capa=capa)
    if not capa.url:
        avaliacao.motivo = "candidato sem endereço de imagem"
        return avaliacao
    if contexto.get('revisar_albuns'):
        if not _identidade_estrita(contexto.get('titulo') or '', contexto.get('artista') or '', capa):
            avaliacao.motivo = 'título ou artista não correspondem com segurança'
            return avaliacao
    caminho, dados = _obter_imagem(capa.url)
    if not dados:
        avaliacao.motivo = "não foi possível baixar a imagem"
        return avaliacao
    validacao = capa_validacao.validar(dados, minimo_lado=minimo_lado,
                                       exigir_quadrada=exigir_quadrada)
    avaliacao.caminho = caminho or ""
    avaliacao.largura, avaliacao.altura = validacao.largura, validacao.altura
    avaliacao.hash_imagem = validacao.hash
    if not validacao.ok:
        avaliacao.motivo = validacao.motivo
        return avaliacao

    nota = correspondencia.pontuar(
        contexto.get("titulo") or "", contexto.get("artista") or "",
        contexto.get("album") or "",
        contexto.get("ano"), isrc=contexto.get("isrc") or "",
        mbid=contexto.get("mbid") or "",
        cand={"titulo": capa.titulo or "",
              "artista": capa.artista or "", "album": capa.album or "",
              "ano": capa.ano, "isrc": capa.isrc, "mbid": capa.mbid},
        imagem_frontal=capa.frontal)
    avaliacao.score = nota.total
    avaliacao.componentes = nota.componentes
    avaliacao.explicacao = correspondencia.explicacao(nota)
    if (contexto.get("revisar_albuns") and contexto.get("album_referencia") and capa.album
            and str(capa.extra.get("tipo_lancamento") or "").lower() != "single"
            and not _album_compativel(contexto["album_referencia"], capa.album)):
        avaliacao.explicacao = "Álbum diferente do informado; confira a edição. " + avaliacao.explicacao
    avaliacao.aprovada = nota.aprovado
    if not avaliacao.aprovada:
        avaliacao.motivo = "; ".join(nota.motivos) or "correspondência insuficiente"
    return avaliacao


def coletar(titulo: str, artista: str = "", album: str = "",
            ano: Optional[int] = None, fontes: Optional[List[str]] = None,
            minimo_lado: int = 300, thumb_extra: str = "",
            usar_miniatura: bool = False, identificacao: Optional[Identificacao] = None,
            isrc: str = "", mbid: str = "", exigir_quadrada: bool = False,
            incluir_albuns_para_revisao: bool = False
            ) -> Tuple[List[Avaliacao], List[Avaliacao]]:
    """(aprovadas, reprovadas); alternativas aprovadas sem bytes repetidos."""
    fontes = ["coverartarchive", "itunes", "deezer"] if fontes is None else fontes
    if identificacao is not None:
        incertos = {str(c).lower().strip() for c in (getattr(identificacao, 'campos_incertos', None) or [])}
        if 'album' not in incertos:
            album = album or getattr(identificacao, "album", "") or ""
        artista = artista or getattr(identificacao, "artista", "") or ""
        ano = ano or getattr(identificacao, "ano", None)
        isrc = isrc or getattr(identificacao, "isrc", "") or ""

    # Sem revisão, mantém a busca restrita a singles; na revisão, outras
    # coleções entram apenas como opções que a pessoa precisa confirmar.
    if not titulo or not artista:
        return [], []
    contexto = {"titulo": titulo, "artista": artista, "album": "",
                "ano": ano, "isrc": isrc, "mbid": mbid,
                "revisar_albuns": incluir_albuns_para_revisao,
                "album_referencia": album if incluir_albuns_para_revisao else ""}
    brutos: List[provedores.Capa] = []
    for nome, funcao in (("itunes", provedores.apple_music),
                         ("coverartarchive", provedores.caa_busca),
                         ("deezer", provedores.deezer)):
        if nome in fontes:
            try:
                # Single e álbum são recuperados para escolha explícita; a
                # busca sem revisão continua exclusivamente de single.
                if nome == 'itunes' and incluir_albuns_para_revisao:
                    brutos += funcao(titulo, artista, "", ano, incluir_albuns=True)
                else:
                    brutos += funcao(titulo, artista, "", ano)
            except Exception as exc:
                from ..logging_setup import registrar_erro
                registrar_erro('Busca de capas ' + nome, f'{type(exc).__name__}: {exc}')
            if nome == 'coverartarchive' and incluir_albuns_para_revisao:
                try:
                    brutos += provedores.caa_albuns(titulo, artista, album, ano)
                except Exception as exc:
                    from ..logging_setup import registrar_erro
                    registrar_erro('Busca de capas de álbum CAA', f'{type(exc).__name__}: {exc}')
    tipos = {'single', 'album', 'colecao'} if incluir_albuns_para_revisao else {'single'}
    elegiveis = [c for c in brutos if str(c.extra.get("tipo_lancamento") or "").lower() in tipos]
    motivo_tipo = ('não foi possível confirmar que é álbum ou single' if incluir_albuns_para_revisao
                   else 'não foi possível confirmar que a capa é de um single')
    reprovadas = [Avaliacao(capa=c, motivo=motivo_tipo) for c in brutos if c not in elegiveis]
    aprovadas, falhas = _avaliar_lista(elegiveis, contexto, minimo_lado, exigir_quadrada)
    reprovadas.extend(falhas)
    # Miniaturas não são alternativas automáticas. Álbuns só entram na revisão.

    # Ordem final: preferência pelo álbum informado, nota, resolução e provedor.
    # Empatou na nota? ganha a imagem maior — capa de 300 px não serve quando
    # existe a mesma capa em 1200 px.
    aprovadas.sort(key=lambda a: (a.capa.confirmada,
                                  bool(incluir_albuns_para_revisao and album and _album_compativel(album, a.capa.album)),
                                  round(a.score, 2),
                                  min(a.largura, a.altura), -a.capa.prioridade),
                   reverse=True)
    reprovadas.sort(key=lambda a: a.capa.prioridade)
    return aprovadas, reprovadas


def _avaliar_lista(brutos: List[provedores.Capa], contexto: Dict[str, Any],
                   minimo_lado: int, exigir_quadrada: bool,
                   minimo: Optional[float] = None
                   ) -> Tuple[List[Avaliacao], List[Avaliacao]]:
    aprovadas: List[Avaliacao] = []
    reprovadas: List[Avaliacao] = []
    vistos: set = set()
    for bruto in brutos:
        chave_url = ((bruto.url, bruto.extra.get('tipo_lancamento'), bruto.album)
                     if contexto.get('revisar_albuns') else bruto.url)
        if not bruto.url or chave_url in vistos:
            continue
        vistos.add(chave_url)
        avaliacao = avaliar(bruto, contexto, minimo_lado, exigir_quadrada)
        if minimo is not None and avaliacao.score < minimo:
            avaliacao.aprovada = False
            avaliacao.motivo = f"nota {avaliacao.score:.2f} abaixo do mínimo {minimo:.2f}"
        (aprovadas if avaliacao.aprovada else reprovadas).append(avaliacao)
    # mesma imagem vinda de dois provedores conta uma vez
    unicas: List[Avaliacao] = []
    hashes = set()
    for avaliacao in aprovadas:
        imagem = avaliacao.hash_imagem or avaliacao.capa.url
        chave = ((imagem, avaliacao.capa.extra.get('tipo_lancamento'), avaliacao.capa.album)
                 if contexto.get('revisar_albuns') else imagem)
        if chave in hashes:
            continue
        hashes.add(chave)
        unicas.append(avaliacao)
    return unicas, reprovadas


def melhor(aprovadas: List[Avaliacao]) -> Optional[Avaliacao]:
    return aprovadas[0] if aprovadas else None


def ambiguidade(aprovadas: List[Avaliacao], margem: float = 0.06) -> bool:
    """Dois candidatos bons, de álbuns diferentes e praticamente empatados.

    Só vale a pena perguntar quando a nota empata **e** as imagens têm tamanho
    parecido; se uma é 1200 px e a outra 300 px, a melhor já está decidida.
    Mesma capa em provedores diferentes (mesmo álbum) também não é dúvida.
    """
    if len(aprovadas) < 2:
        return False
    primeira, segunda = aprovadas[0], aprovadas[1]
    if abs(primeira.score - segunda.score) > margem:
        return False
    lado_a = min(primeira.largura, primeira.altura) or 1
    lado_b = min(segunda.largura, segunda.altura) or 1
    if max(lado_a, lado_b) / max(1, min(lado_a, lado_b)) > 1.25:
        return False
    from ..texto import normalizar
    album_a = normalizar(primeira.capa.album or "")
    album_b = normalizar(segunda.capa.album or "")
    return not (album_a and album_b and (album_a in album_b or album_b in album_a))

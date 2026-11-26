"""Reavalia uma música com a IA e um catálogo, sempre pela mesma identidade."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict

from ..metadata import album_original, itunes
from ..metadata.correspondencia import identidade_metadados, versoes
from ..models import Identificacao, TrackResult
from ..texto import limpar_titulo_tags, normalizar, separar_artista_titulo
from . import identificador


def consulta_revisao(revisao: Dict[str, Any]) -> Dict[str, str]:
    """Separa o prefixo apenas quando corresponde ao artista preenchido."""
    dados = revisao.get('dados_atuais') or {}
    titulo = str(dados.get('titulo') or '').strip()
    artista = str(dados.get('artista') or '').strip()
    prefixo, faixa = separar_artista_titulo(titulo)
    if prefixo and faixa and artista and normalizar(prefixo) == normalizar(artista):
        titulo = faixa
    return {'titulo': limpar_titulo_tags(titulo), 'artista': artista}


def mesma_identidade(titulo: str, artista: str, dados: Dict[str, Any]) -> bool:
    # Comparação aproximada de nomes de artistas ainda troca homônimos parecidos.
    return bool(artista and dados.get('artista') and
                normalizar(artista) == normalizar(dados['artista']) and
                identidade_metadados(titulo, artista, dados) and
                versoes(titulo) == versoes(dados.get('titulo') or ''))


def reavaliar(resultado: TrackResult, config, revisao: Dict[str, Any]) -> Dict[str, Any]:
    """Consulta Groq e catálogos em paralelo; nenhuma resposta é prova absoluta."""
    consulta = consulta_revisao(revisao)
    titulo, artista = consulta['titulo'], consulta['artista']
    if not titulo or not artista:
        return {'ident': Identificacao(ok=False, erro='informe o título e o artista'),
                'catalogo': {}, 'consulta': consulta}
    atualizados = dict(revisao.get('dados_atuais') or {}, titulo=titulo, artista=artista)
    pedido = dict(revisao, dados_atuais=atualizados)

    def procurar():
        # A associação da gravação e do lançamento vem do MusicBrainz. O iTunes
        # complementa gênero e, apenas para a mesma edição/ano, posição/crédito.
        try:
            mb = album_original.encontrar(titulo, artista) or {}
        except Exception:
            mb = {}
        if not isinstance(mb, dict) or not mb.get('album') or not mesma_identidade(titulo, artista, mb):
            mb = {}
        if mb and all(mb.get(k) for k in ('genero', 'faixa', 'artista_album')):
            return dict(mb, fonte='musicbrainz', fontes=['musicbrainz'])
        try:
            it = itunes.melhor_faixa(titulo, artista, mb.get('album', '')) or {}
        except Exception:
            it = {}
        if not isinstance(it, dict) or not it.get('album') or not mesma_identidade(titulo, artista, it):
            it = {}
        if not mb:
            return dict(it, fonte='itunes', fontes=['itunes']) if it else {}
        dados = dict(mb, fonte='musicbrainz', fontes=['musicbrainz'])
        if it:
            dados['fontes'].append('itunes')
            if it.get('genero') and not dados.get('genero'):
                dados['genero'] = it['genero']
            mesma_edicao = (normalizar(str(it.get('album') or '')) == normalizar(str(mb.get('album') or ''))
                            and it.get('ano') and it.get('ano') == mb.get('ano'))
            if mesma_edicao:
                for chave in ('faixa', 'artista_album'):
                    if it.get(chave) and not dados.get(chave):
                        dados[chave] = it[chave]
        return dados

    with ThreadPoolExecutor(max_workers=2, thread_name_prefix='revisao-musica') as executor:
        futuro_ia = executor.submit(identificador.identificar, resultado, config, revisao=pedido)
        futuro_catalogo = executor.submit(procurar)
        ident, catalogo = futuro_ia.result(), futuro_catalogo.result()
    return {'ident': ident, 'catalogo': catalogo, 'consulta': consulta}

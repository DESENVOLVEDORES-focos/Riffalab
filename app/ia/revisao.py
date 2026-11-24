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
        # Uma associação de gravação/lancamento no MusicBrainz tem prioridade;
        # caso não haja, a coleção do iTunes é apenas outra edição possível.
        for fonte, funcao in (('musicbrainz', album_original.encontrar),
                             ('itunes', itunes.melhor_faixa)):
            try:
                dados = funcao(titulo, artista) or {}
            except Exception:
                continue
            if (isinstance(dados, dict) and dados.get('album') and
                    mesma_identidade(titulo, artista, dados)):
                return dict(dados, fonte=fonte)
        return {}

    with ThreadPoolExecutor(max_workers=2, thread_name_prefix='revisao-musica') as executor:
        futuro_ia = executor.submit(identificador.identificar, resultado, config, revisao=pedido)
        futuro_catalogo = executor.submit(procurar)
        ident, catalogo = futuro_ia.result(), futuro_catalogo.result()
    return {'ident': ident, 'catalogo': catalogo, 'consulta': consulta}

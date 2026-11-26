"""Álbum associado à gravação, sem confiar apenas na resposta textual da IA."""
from __future__ import annotations

import re
from typing import Any, Dict
from . import musicbrainz
from .correspondencia import identidade_metadados, versoes
from ..texto import normalizar


def album_canonico(nome: str) -> str:
    """Remove qualificadores editoriais apenas no fim, mantendo a grafia do catálogo."""
    s = str(nome or '').strip()
    padrao = r'(?:remaster(?:ed|izado|izada)?|deluxe|expanded|anniversary|edição especial|special edition)'
    s = re.sub(r'\s*[\(\[][^\)\]]*\b' + padrao + r'\b[^\)\]]*[\)\]]\s*$', '', s, flags=re.I)
    s = re.sub(r'\s*[-–—]\s*(?:\d{4}\s+)?' + padrao + r'\b.*$', '', s, flags=re.I)
    return s.strip()


def encontrar(titulo: str, artista: str) -> Dict[str, Any]:
    """Usa lançamentos de álbum que o MusicBrainz liga à gravação.

    Priorizamos o álbum regular mais antigo dentre os retornados. Isso não
    prova que o catálogo esteja completo ou que a edição seja a original.
    """
    if not titulo or not artista:
        return {}
    try:
        gravacoes = musicbrainz.buscar_gravacao(titulo, artista, '', limite=25, todos_lancamentos=True)
    except Exception as exc:
        from ..logging_setup import registrar_erro
        registrar_erro('Álbum da música', f'{type(exc).__name__}: {exc}')
        return {}
    # A resposta de pesquisa de gravação muitas vezes informa apenas o ID e
    # tipo do grupo, sem o nome. Buscar o grupo é necessário para obter a
    # grafia oficial, a data original e as classificações secundárias.
    grupos = {}
    for g in gravacoes:
        if (str(g.get('tipo_lancamento') or '').lower() not in ('album', 'single')
                or not g.get('release_id') or not g.get('release_group')
                or not identidade_metadados(titulo, artista, g)):
            continue
        if str(g.get('status') or '').lower() not in ('', 'official'):
            continue
        chave = str(g['release_group'])
        data = str(g.get('data_release') or '9999')
        if chave not in grupos or data < str(grupos[chave].get('data_release') or '9999'):
            grupos[chave] = g
    grupos_ordenados = sorted(grupos.values(), key=lambda g: (
        0 if str(g.get('tipo_lancamento')).lower() == 'album' else 1,
        str(g.get('data_release') or '9999'), str(g['release_group'])))
    candidatos = []
    for g in grupos_ordenados[:4]:
        nome_grupo = str(g.get('album_grupo') or '').strip()
        data_grupo = str(g.get('data_grupo') or '')
        secundarios = {str(x).lower() for x in g.get('tipos_secundarios') or []}
        if not nome_grupo or not data_grupo:
            try:
                grupo = musicbrainz.detalhes_grupo(str(g['release_group']))
            except musicbrainz.SemConteudo:
                continue
            except Exception:
                # O serviço pode estar fora do ar; não repetir quatro tempos
                # de espera para grupos diferentes do mesmo catálogo.
                break
            if str(grupo.get('primary-type') or '').lower() != str(g.get('tipo_lancamento') or '').lower():
                continue
            nome_grupo = str(grupo.get('title') or '').strip()
            data_grupo = str(grupo.get('first-release-date') or '')
            secundarios = {str(x).lower() for x in grupo.get('secondary-types') or []}
        if secundarios & {'compilation', 'remix', 'dj-mix', 'mixtape/street'}:
            continue
        if 'live' in secundarios and 'live' not in versoes(titulo):
            continue
        nome = nome_grupo
        if not nome or re.search(r'\b(greatest hits|best of|anthology|compilation|colet[aâ]nea)\b', nome, re.I):
            continue
        data = data_grupo or str(g.get('data_release') or '')
        if not re.match(r'^(?:19|20)\d{2}', data):
            continue
        ano = int(data[:4])
        candidatos.append((0 if str(g.get('tipo_lancamento')).lower() == 'album' else 1,
                           ano, data, normalizar(nome), nome, str(g['release_id']), g))
    if not candidatos:
        return {}
    # Preferir o ano original conhecido; desempate estável, nunca depender da
    # ordem arbitrária de buscas ou capitalização sugerida pela IA.
    candidatos.sort(key=lambda x: x[:6])
    _tipo, ano, _data, _chave, nome, _release_id, g = candidatos[0]
    try:
        det = musicbrainz.detalhes_release(g['release_id'], titulo) or {}
    except Exception:
        det = {}
    # A gravação já estava associada a este lançamento; número da faixa só se
    # a lista detalhada também contiver o título da música.
    from ..texto import limpar_titulo_tags
    retorno = {'album': nome, 'ano': ano, 'fonte': 'musicbrainz', 'release_group': g['release_group'],
               'titulo': limpar_titulo_tags(g.get('titulo') or titulo),
               'artista': g.get('artista') or artista}
    if (det.get('ano') == ano and normalizar(det.get('album') or '') == normalizar(nome)):
        for k in ('faixa', 'total_faixas', 'disco', 'artista_album', 'genero',
                  'creditos_album', 'creditos_faixa'):
            if det.get(k):
                retorno[k] = det[k]
    return retorno

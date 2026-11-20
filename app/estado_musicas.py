"""Serialização explícita de seleções locais, sem cookies nem URLs temporárias do yt-dlp."""
from __future__ import annotations

from dataclasses import asdict, fields
from pathlib import Path
from typing import Any

from .models import AudioFormat, CoverResult, Identificacao, TrackMeta, TrackResult


def _construir(cls, valores):
    if not isinstance(valores, dict):
        raise ValueError('dados inválidos')
    nomes = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in valores.items() if k in nomes})


def _formato(fmt, fonte):
    if fmt is None:
        return None
    d = asdict(fmt)
    # Links diretos de fluxo do yt-dlp expiram e podem conter tokens; o ID e a
    # URL da página bastam para solicitar o formato novamente.
    if fonte == 'ytdlp':
        d['url'] = ''
    extra = fmt.extra or {}
    d['extra'] = {k: extra[k] for k in ('metodos', 'detalhes_audio', 'nota') if k in extra}
    return d


def serializar_pedido(pedido: dict) -> dict:
    r = pedido['resultado']
    d = asdict(r)
    d['formatos'] = [_formato(f, r.fonte) for f in r.formatos]
    extra = r.extra or {}
    d['extra'] = {k: extra[k] for k in ('id', 'url', 'caminho', 'canal', 'titulo_original',
                    'metodos_consulta', 'erro_detalhe') if k in extra}
    return {'resultado': d, 'formato': _formato(pedido.get('formato'), r.fonte),
            'edicao': dict(pedido.get('edicao') or {})}


def desserializar_pedido(d: dict) -> dict:
    dados = dict(d['resultado'])
    dados['formatos'] = [_construir(AudioFormat, x) for x in dados.get('formatos', [])]
    r = _construir(TrackResult, dados)
    if not r.uid or not r.fonte:
        raise ValueError('resultado sem identidade')
    fmt = _construir(AudioFormat, d['formato']) if d.get('formato') else None
    edicao = d.get('edicao') or {}
    if not isinstance(edicao, dict):
        raise ValueError('edição inválida')
    return {'resultado': r, 'formato': fmt, 'edicao': edicao}


def serializar_selecao(linha) -> dict:
    d = {'pedido': serializar_pedido(linha.pedido), 'marcada': linha.check.isChecked()}
    prep = linha.preparacao
    if prep:
        capa = asdict(prep['capa'])
        capa['alternativas'] = []
        d['preparacao'] = {'meta': asdict(prep['meta']), 'capa': capa,
                            'ident': asdict(prep['ident']) if prep.get('ident') else None,
                            'apagar_tags': list(prep.get('apagar_tags') or [])}
    return d


def desserializar_selecao(d: dict) -> tuple[dict, bool, dict | None]:
    pedido = desserializar_pedido(d['pedido'])
    p = d.get('preparacao')
    preparacao = None
    if p:
        capa = _construir(CoverResult, p['capa'])
        # Capas removidas não podem ser aceitas silenciosamente.
        if not capa.ok or Path(capa.caminho).is_file():
            apagar = [x for x in p.get('apagar_tags', []) if x == 'album']
            # Migração de seleções preparadas pela versão anterior, que já
            # guardava a edição mas ainda não registrava remoção da tag.
            edicao = pedido.get('edicao') or {}
            if 'album' in edicao and not str(edicao['album']).strip() and 'album' not in apagar:
                apagar.append('album')
            preparacao = {'meta': _construir(TrackMeta, p['meta']), 'capa': capa,
                          'ident': _construir(Identificacao, p['ident']) if p.get('ident') else None,
                          'apagar_tags': apagar}
    return pedido, bool(d.get('marcada', True)), preparacao

"""Preparação de metadados e capas antes de baixar qualquer áudio."""
from __future__ import annotations

from typing import Any, Dict

from . import pipeline
from .config import Config
from .ia import identificador
from .models import TrackResult


# Edições explícitas têm precedência sobre qualquer fonte ou resposta de IA.
CAMPOS_EDITAVEIS = ('titulo', 'artista', 'album', 'artista_album',
                    'artistas_participantes', 'genero', 'ano', 'faixa')
CAMPOS_REMOVIVEIS = ('album', 'artista_album', 'genero', 'ano', 'faixa')


def aplicar_edicao(meta, edicao):
    edicao = edicao or {}
    for chave in CAMPOS_EDITAVEIS:
        if chave not in edicao:
            continue
        valor = str(edicao[chave] or '').strip()
        if chave in ('ano', 'faixa'):
            if valor and (not valor.isdecimal() or not (1 <= int(valor) <= (9999 if chave == 'ano' else 999))):
                raise ValueError(f'{chave} inválido')
            anterior = getattr(meta, chave)
            novo = int(valor) if valor else None
            setattr(meta, chave, novo)
            if chave == 'ano' and novo != anterior:
                # A data completa anterior não pode contradizer a edição.
                meta.data_lancamento = ''
            if chave == 'faixa' and novo != anterior:
                meta.total_faixas = None
        elif chave == 'artistas_participantes':
            import re
            meta.artistas_participantes = [n.strip() for n in re.split(r'[,;]', valor) if n.strip()]
        else:
            setattr(meta, chave, valor)
    return [campo for campo in CAMPOS_REMOVIVEIS
            if campo in edicao and not str(edicao[campo] or '').strip()]


def preparar_musica(resultado: TrackResult, config: Config, progresso=None,
                     edicao=None, sem_capa: bool = False) -> Dict[str, Any]:
    """Identifica a faixa e busca capas; não chama a fonte nem baixa áudio.

    A identificação por IA é opcional. A escolha efetiva da capa é sempre
    responsabilidade da interface, antes de passar o resultado para o pipeline.
    """
    from dataclasses import replace
    campos = {k: str(edicao[k]).strip() for k in ('titulo', 'artista', 'album')
              if edicao is not None and k in edicao}
    consulta = replace(resultado, **campos) if campos else resultado
    ident = None
    if config.get('ia_ativa'):
        ident = identificador.identificar(consulta, config, progresso)
    meta = pipeline.montar_metadados(consulta, config, progresso=progresso, ident=ident)
    apagar_tags = aplicar_edicao(meta, edicao)
    if sem_capa:
        from .models import CoverResult
        capa = CoverResult(observacao='Usuário escolheu não usar capa no lote')
    else:
        capa = pipeline.buscar_capa(meta, config,
            resultado.thumb_url or resultado.extra.get('thumb', ''), progresso, ident=ident)
    return {'meta': meta, 'ident': ident, 'capa': capa, 'apagar_tags': apagar_tags}

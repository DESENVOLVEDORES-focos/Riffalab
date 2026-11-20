"""Preparação de metadados e capas antes de baixar qualquer áudio."""
from __future__ import annotations

from typing import Any, Dict

from . import pipeline
from .config import Config
from .ia import identificador
from .models import TrackResult


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
    for chave in ('titulo', 'artista', 'album'):
        if edicao is not None and chave in edicao:
            setattr(meta, chave, str(edicao[chave]).strip())
    if sem_capa:
        from .models import CoverResult
        capa = CoverResult(observacao='Usuário escolheu não usar capa no lote')
    else:
        capa = pipeline.buscar_capa(meta, config,
            resultado.thumb_url or resultado.extra.get('thumb', ''), progresso, ident=ident)
    return {'meta': meta, 'ident': ident, 'capa': capa}

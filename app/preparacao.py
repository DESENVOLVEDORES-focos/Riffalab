"""Preparação de metadados e capas antes de baixar qualquer áudio."""
from __future__ import annotations

from typing import Any, Dict

from . import pipeline
from .config import Config
from .ia import identificador
from .models import TrackResult


def preparar_musica(resultado: TrackResult, config: Config, progresso=None) -> Dict[str, Any]:
    """Identifica a faixa e busca capas; não chama a fonte nem baixa áudio.

    A identificação por IA é opcional. A escolha efetiva da capa é sempre
    responsabilidade da interface, antes de passar o resultado para o pipeline.
    """
    ident = None
    if config.get('ia_ativa'):
        ident = identificador.identificar(resultado, config, progresso)
    meta = pipeline.montar_metadados(resultado, config, progresso=progresso, ident=ident)
    capa = pipeline.buscar_capa(meta, config,
        resultado.thumb_url or resultado.extra.get('thumb', ''), progresso, ident=ident)
    return {'meta': meta, 'ident': ident, 'capa': capa}

"""Camada de pesquisa: enriquecimento, filtros e pré-visualização.

Nada aqui importa Qt: são funções puras sobre `models.TrackResult`, testáveis
pela linha de comando (ver `app/pesquisa/__init__.py` docstring e os testes).
"""
from .filtros import Analise, analisar, aplicar, ordenar  # noqa: F401
from .preview import pode_incorporar, tem_player, url_incorporada  # noqa: F401
from .resultados import enriquecer, normalizar_resultados  # noqa: F401

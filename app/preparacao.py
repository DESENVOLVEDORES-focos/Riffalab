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
    if 'album' in edicao:
        from .texto import normalizar
        if normalizar(str(edicao['album'] or '')) != normalizar(meta.album or ''):
            # Dados de posição e edição anterior não pertencem necessariamente
            # ao álbum corrigido. O que o usuário digitar abaixo terá prioridade.
            meta.faixa = meta.total_faixas = meta.disco = meta.ano = None
            meta.data_lancamento = ''
            meta.genero = ''
            meta.artista_album = ''
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


def identidade_para_capa(meta, ident, config, edicao=None):
    """Define a consulta por música sem alterar metadados ou edições do usuário.

    A sugestão textual da IA orienta a busca, não prova a gravação nem a capa.
    Uma divergência de versão ou resposta incompleta não é usada silenciosamente.
    """
    from .texto import normalizar
    from .metadata.correspondencia import versoes
    from .ia.identificador import _confianca

    edicao = edicao or {}
    titulo, artista = meta.titulo or '', meta.artista or ''
    origem = 'dados revisados' if any(k in edicao for k in ('titulo', 'artista')) else 'dados da música'
    aviso = ''
    usar_ident = None
    confianca = _confianca(getattr(ident, 'confianca', 0)) if ident is not None else 0
    limiar = max(0.70, _confianca(config.get('ia_min_confianca') or 0))
    incertos = {normalizar(str(c)).replace(' ', '_') for c in (getattr(ident, 'campos_incertos', None) or [])}
    from .texto import limpar_titulo_tags
    ai_titulo = limpar_titulo_tags(str(getattr(ident, 'titulo', '') or ''))
    ai_artista = str(getattr(ident, 'artista', '') or '').strip()
    identidade_revisada = 'titulo' in edicao and 'artista' in edicao
    if identidade_revisada:
        # A identidade editada tem prioridade sobre qualquer resposta da IA.
        pass
    elif (ident is not None and getattr(ident, 'ok', False) and confianca >= limiar
            and ai_titulo and ai_artista and not {'titulo', 'artista'}.intersection(incertos)):
        if 'titulo' not in edicao and versoes(titulo) != versoes(ai_titulo):
            aviso = 'A versão identificada pela IA difere da música; confira o título antes de buscar a capa.'
        else:
            titulo = titulo if 'titulo' in edicao else ai_titulo
            artista = artista if 'artista' in edicao else ai_artista
            origem = 'IA + dados revisados' if any(k in edicao for k in ('titulo', 'artista')) else 'IA'
            if (normalizar(titulo) == normalizar(ai_titulo)
                    and normalizar(artista) == normalizar(ai_artista)):
                usar_ident = ident
            if (normalizar(titulo) != normalizar(meta.titulo or '')
                    or normalizar(artista) != normalizar(meta.artista or '')):
                aviso = ('A identidade usada para a capa difere dos metadados do arquivo. '
                         'Confira ambos antes de confirmar a capa.')
    elif ident is not None:
        aviso = 'IA sem título e artista confiáveis; usando os dados disponíveis para procurar a capa.'
    elif config.get('ia_ativa'):
        aviso = 'IA não disponível; usando os dados disponíveis para procurar a capa.'
    else:
        aviso = 'IA desativada; usando os dados disponíveis para procurar a capa.'
    # Normalização somente para um nome de canal não revisado: a identidade
    # mostrada na tela é exatamente a identidade usada na chamada ao catálogo.
    if not origem.startswith('IA') and 'artista' not in edicao:
        from .texto import parece_canal, separar_artista_titulo
        if artista and parece_canal(artista):
            candidato, resto = separar_artista_titulo(titulo)
            if candidato and resto and not parece_canal(candidato):
                artista, titulo = candidato, resto
    return {'titulo': titulo, 'artista': artista, 'origem': origem, 'aviso': aviso}, usar_ident


def preparar_musica(resultado: TrackResult, config: Config, progresso=None,
                     edicao=None, sem_capa: bool = False) -> Dict[str, Any]:
    """Identifica a faixa para revisão manual; não baixa áudio nem busca capas.

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
    consulta_capa = None
    if sem_capa:
        from .models import CoverResult
        capa = CoverResult(observacao='Usuário escolheu não usar capa no lote')
    else:
        consulta_capa, _ = identidade_para_capa(meta, ident, config, edicao)
        from .models import CoverResult
        capa = CoverResult(observacao='Pesquise no Google quando quiser e cole a imagem copiada.')
    return {'meta': meta, 'ident': ident, 'capa': capa, 'apagar_tags': apagar_tags,
            'consulta_capa': consulta_capa}

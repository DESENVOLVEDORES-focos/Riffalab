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


def preparar_previa(resultado: TrackResult, config: Config, edicao=None) -> Dict[str, Any]:
    """Identidade provisória local para abrir a janela sem esperar a rede."""
    from dataclasses import replace
    from .models import CoverResult
    campos = {k: str(edicao[k]).strip() for k in ('titulo', 'artista', 'album')
              if edicao is not None and k in edicao}
    consulta = replace(resultado, **campos) if campos else resultado
    meta = pipeline.montar_metadados(consulta, config, consultar_catalogos=False)
    apagar = aplicar_edicao(meta, edicao)
    identidade, _ = identidade_para_capa(meta, None, config, edicao)
    identidade['origem'] = 'dados provisórios'
    identidade['aviso'] = ('Identificando a música em segundo plano. Você já pode pesquisar, '
                            'mas confira a identidade atualizada antes de confirmar a capa.')
    return {'meta': meta, 'ident': None, 'capa': CoverResult(), 'apagar_tags': apagar,
            'consulta_capa': identidade}


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


def identificar_antes_de_download(resultado: TrackResult, config: Config, edicao=None) -> Dict[str, Any]:
    """Duas etapas: identidade do vídeo, depois dados da música e catálogos.

    Não escuta o áudio. Sugestões não são prova; nunca usa álbum da IA como
    confirmação nem deixa uma identificação automática substituir edição manual.
    """
    from .ia import revisao as revisao_ia
    from .metadata.correspondencia import versoes
    from .models import CoverResult, TrackMeta
    from .texto import limpar_titulo_tags, normalizar, separar_artista_titulo

    edicao = dict(edicao or {})
    original = str((resultado.extra or {}).get('titulo_original') or resultado.titulo or '')
    titulo = str(edicao.get('titulo') or resultado.titulo or '').strip()
    artista = str(edicao.get('artista') or resultado.artista or '').strip()
    prefixo, faixa = separar_artista_titulo(titulo)
    if prefixo and faixa and artista and normalizar(prefixo) == normalizar(artista):
        titulo = faixa
    titulo = limpar_titulo_tags(titulo)
    primeira = None
    segura = False
    avisos = []
    if config.get('ia_ativa'):
        primeira = identificador.identificar(resultado, config, somente_identidade=True)
        incertos = {normalizar(str(c)).replace(' ', '_') for c in (primeira.campos_incertos or [])}
        ai_titulo = limpar_titulo_tags(primeira.titulo or '')
        ai_artista = str(primeira.artista or '').strip()
        bruto = normalizar(original)
        # O vídeo ou sua fonte devem sustentar ambos os nomes: autoconfiança do
        # modelo, sozinha, não impede confusão com uma música homônima.
        titulo_no_video = bool(normalizar(ai_titulo) and normalizar(ai_titulo) in bruto)
        artista_no_video = bool(normalizar(ai_artista) and normalizar(ai_artista) in bruto)
        artista_da_fonte = bool(artista and normalizar(ai_artista) == normalizar(artista))
        segura = (primeira.ok and identificador._confianca(primeira.confianca) >= max(.70, identificador._confianca(config.get('ia_min_confianca') or 0))
                  and not {'titulo', 'artista'}.intersection(incertos)
                  and titulo_no_video and (artista_no_video or artista_da_fonte)
                  and versoes(original) == versoes(ai_titulo))
        if segura:
            if 'titulo' not in edicao:
                titulo = ai_titulo
            if 'artista' not in edicao:
                artista = ai_artista
        else:
            if not primeira.ok and primeira.erro:
                avisos.append('IA indisponível ou sem resposta; confira título e artista.')
            else:
                avisos.append('IA não confirmou a identidade do vídeo; confira título e artista.')
    else:
        avisos.append('IA desativada; usando os dados disponíveis da origem.')

    # Para vídeos, nome do canal isolado não prova o intérprete. Uma
    # identidade explícita no título, uma origem não-vídeo ou uma edição
    # manual podem sustentar a consulta mesmo se a IA estiver indisponível.
    artista_no_original = bool(normalizar(artista) and normalizar(artista) in normalizar(original))
    fonte_confiavel = resultado.fonte != 'ytdlp' or artista_no_original
    confiavel = bool(titulo and artista and (segura or fonte_confiavel))
    if 'titulo' in edicao and 'artista' in edicao:
        confiavel = bool(titulo and artista)
    segunda, catalogo = None, {}
    if confiavel:
        pedido = {'dados_atuais': {'titulo': titulo, 'artista': artista,
                                    'album': edicao.get('album') or ''}, 'observacao': ''}
        resposta = revisao_ia.reavaliar(resultado, config, pedido)
        segunda, catalogo = resposta['ident'], resposta['catalogo']
    else:
        avisos.append('Artista não identificado com segurança; revise os dados antes de baixar.')

    meta = TrackMeta(titulo=titulo, artista=artista, album=resultado.album or '',
                     ano=resultado.ano, fonte_identificacao='dados da origem')
    if catalogo:
        # Não combinar ano/álbum de origem com uma edição de catálogo diferente.
        meta.album = ''
        meta.ano = None
        meta.titulo = catalogo.get('titulo') or titulo
        meta.artista = artista
        for campo in ('album', 'ano', 'faixa', 'artista_album', 'genero', 'total_faixas', 'disco'):
            if catalogo.get(campo):
                setattr(meta, campo, catalogo[campo])
        meta.fonte_identificacao = ' + '.join(catalogo.get('fontes') or [catalogo.get('fonte') or 'catálogo'])
        if segunda and segunda.ok and identificador._confianca(segunda.confianca) >= .70:
            incertos = {normalizar(str(c)).replace(' ', '_') for c in (segunda.campos_incertos or [])}
            mesma = revisao_ia.mesma_identidade(titulo, artista,
                       {'titulo': segunda.titulo, 'artista': segunda.artista})
            if mesma and not {'titulo', 'artista'}.intersection(incertos):
                if 'artistas_participantes' not in incertos:
                    meta.artistas_participantes = list(segunda.artistas_participantes or [])
                    if meta.artistas_participantes:
                        avisos.append('Participações sugeridas pela IA, não confirmadas pelo catálogo.')
                if (not meta.genero and segunda.genero and 'genero' not in incertos
                        and 'album' not in incertos and segunda.album
                        and normalizar(segunda.album) == normalizar(meta.album)):
                    meta.genero = segunda.genero
                    avisos.append('Gênero sugerido pela IA, não confirmado pelo catálogo.')
    elif confiavel:
        avisos.append('Catálogo não confirmou um lançamento; confira os campos antes de baixar.')
    if segunda and not segunda.ok and config.get('ia_ativa'):
        avisos.append('A segunda consulta à IA não pôde ser concluída.')
    apagar = aplicar_edicao(meta, edicao)
    creditos = []
    for chave, rotulo in (('creditos_album', 'Créditos do álbum no MusicBrainz'),
                          ('creditos_faixa', 'Créditos da faixa no MusicBrainz')):
        if catalogo.get(chave):
            creditos.append(rotulo + ': ' + '; '.join(catalogo[chave][:30]))
    consulta = {'titulo': meta.titulo, 'artista': meta.artista, 'origem': 'dados identificados',
                'aviso': ' '.join(avisos) or 'Confira a identidade e a edição antes de confirmar a capa.'}
    return {'meta': meta, 'ident': segunda or primeira, 'capa': CoverResult(),
            'apagar_tags': apagar, 'consulta_capa': consulta,
            'capa_pendente': True, 'identificacao_aviso': ' '.join(avisos),
            'creditos_catalogo': creditos}

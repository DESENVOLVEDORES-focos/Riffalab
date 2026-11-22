"""Quatro consultas independentes do mesmo link, sem download de áudio."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List

# Consultas usam processos externos pesados. Compartilhar apenas dois em todo
# o aplicativo reduz a carga ao navegar e usar a prévia em listas grandes.
_LIMITE = threading.BoundedSemaphore(2)
NOMES = ('Lista -F', 'JSON -j', 'Lista + JSON', 'Biblioteca Python')


def _json_saida(saida: str) -> Dict[str, Any] | None:
    for linha in reversed(saida.splitlines()):
        if not linha.lstrip().startswith('{'):
            continue
        try:
            obj = json.loads(linha)
            if isinstance(obj, dict) and isinstance(obj.get('formats'), list):
                return obj
        except (ValueError, TypeError):
            pass
    return None


def _lista_texto(saida: str) -> List[Dict[str, Any]]:
    """Interpretação conservadora da tabela -F; colunas podem variar por versão."""
    formatos = []
    codec_re = re.compile(r'\b(opus|vorbis|mp4a(?:\.\d+)*|aac|mp3|flac|alac|ac-3|ec-3)\b', re.I)
    pos_abr = pos_asr = None
    for linha in saida.splitlines():
        # Colunas são alinhadas à direita; os limites vêm do cabeçalho real,
        # não da posição de tokens ou da suposição de que 48k é bitrate.
        if re.match(r'^\s*ID\s+EXT\b', linha, re.I) and re.search(r'\bACODEC\b', linha, re.I):
            cab_abr = re.search(r'\bABR\b', linha, re.I)
            cab_asr = re.search(r'\bASR\b', linha, re.I)
            pos_abr = cab_abr.end() if cab_abr else None
            pos_asr = cab_asr.end() if cab_asr else None
            continue
        partes = linha.strip().split()
        if len(partes) < 3 or not re.fullmatch(r'[\w.\-]+', partes[0]):
            continue
        ident, ext = partes[0], partes[1].lower()
        if ident.lower() in ('id', 'format') or ext in ('mhtml', 'jpg', 'png', 'webp'):
            continue
        codec = codec_re.search(linha)
        apenas_audio = bool(re.search(r'\baudio only\b', linha, re.I))
        if not codec and not apenas_audio:
            continue
        item: Dict[str, Any] = {'format_id': ident, 'ext': ext,
                                'acodec': codec.group(1).lower() if codec else 'unknown',
                                'vcodec': 'none' if apenas_audio else 'unknown'}
        if codec and pos_abr and codec.end() <= pos_abr:
            parte = linha[codec.end():pos_abr].strip()
            if re.fullmatch(r'\d+(?:\.\d+)?k', parte, re.I):
                item['abr'] = float(parte[:-1])
                item['_abr_da_tabela'] = True
        if codec and pos_abr and pos_asr and pos_asr > pos_abr:
            parte = linha[pos_abr:pos_asr].strip()
            if re.fullmatch(r'\d+(?:\.\d+)?k', parte, re.I):
                item['_asr_tabela'] = parte.lower()
        formatos.append(item)
    return formatos


def _somente_audio(formats: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [f for f in formats if isinstance(f, dict) and f.get('format_id')
            and str(f.get('acodec') or 'none').lower() != 'none']


def _erro_seguro(texto: str) -> str:
    baixo = (texto or '').lower()
    for chave, msg in (('sign in to confirm', 'o YouTube pediu autenticação'),
                       ('http error 403', 'acesso recusado (403)'),
                       ('http error 429', 'limite de consultas atingido (429)'),
                       ('requested format is not available', 'formato solicitado indisponível'),
                       ('cookies file', 'não foi possível ler os cookies'),
                       ('unsupported url', 'link não reconhecido')):
        if chave in baixo:
            return msg
    return 'consulta falhou'


def consultar(url: str, base: List[str], rodar, aviso_extracao, ao_parcial=None,
              indices=None) -> Dict[str, Any]:
    """Executa todos os métodos para o mesmo URL e cruza formatos por ID.

    Cada subprocesso recebe sua própria cópia temporária do cookie: yt-dlp pode
    atualizar esse arquivo ao sair; concorrência jamais altera o original.
    """
    def metodo(indice: int) -> Dict[str, Any]:
        nome = NOMES[indice]
        try:
            with _LIMITE, tempfile.TemporaryDirectory(prefix='rifflab-formats-') as temp:
                args = list(base)
                cookies = ''
                if '--cookies' in args:
                    pos = args.index('--cookies') + 1
                    cookies = str(Path(temp) / 'cookies.txt')
                    shutil.copyfile(args[pos], cookies)
                    args[pos] = cookies
                ffmpeg = args[args.index('--ffmpeg-location') + 1] if '--ffmpeg-location' in args else ''
                if indice == 3:
                    helper = Path(__file__).resolve().parent.parent / 'consulta_biblioteca_ytdlp.py'
                    comando = [sys.executable, str(helper), url, cookies, ffmpeg, str(Path(base[0]).parent)]
                else:
                    flags = (['-F'], ['-j'], ['-F', '--print-json'])[indice]
                    comando = args + ['--no-cache-dir'] + flags + ['--no-playlist', '--', url]
                codigo, saida, erro = rodar(comando, timeout=45)
                diagnostico = aviso_extracao(erro)
                versao = ''
                dados = None
                if indice == 0:
                    brutos = _lista_texto(saida) if codigo == 0 else []
                else:
                    dados = _json_saida(saida) if codigo == 0 else None
                    brutos = list(dados.get('formats') or []) if dados else []
                    if indice == 2:
                        # A saída combinada pode trazer tabela mesmo quando o JSON
                        # está ausente ou incompleto; aproveitar ambas as partes.
                        ids_json = {str(f.get('format_id')) for f in brutos if isinstance(f, dict)}
                        brutos.extend(f for f in _lista_texto(saida) if str(f['format_id']) not in ids_json)
                    if dados and indice == 3:
                        versao = str(dados.get('_versao_biblioteca') or '')
                permitidos = ('id', 'title', 'channel', 'uploader', 'channel_id', 'uploader_id',
                              'view_count', 'concurrent_view_count', 'release_date', 'upload_date',
                              'modified_date', 'playable_in_embed', 'age_limit', 'duration',
                              'thumbnail', 'description', 'live_status', 'was_live', 'is_live',
                              'is_upcoming', 'availability', 'channel_is_verified', 'categories', 'tags')
                info = {k: dados[k] for k in permitidos if k in dados} if dados else {}
                validos = _somente_audio(brutos)
                # Preservar também os dados de vídeo para a resolução mostrada no cartão;
                # esses formatos não contam como áudio sem uma faixa de áudio.
                videos = [f for f in brutos if isinstance(f, dict)
                          and str(f.get('vcodec') or 'none').lower() != 'none'] if indice else []
                if validos:
                    return {'nome': nome, 'estado': 'ok', 'formatos': validos, 'videos': videos,
                            'aviso': diagnostico, 'versao': versao, 'info': info}
                if codigo == 0 and indice != 0 and not dados and not brutos:
                    return {'nome': nome, 'estado': 'falhou', 'motivo': 'resposta ilegível'}
                if indice == 3 and codigo == 3:
                    return {'nome': nome, 'estado': 'indisponível', 'motivo': 'biblioteca não instalada'}
                return {'nome': nome, 'estado': 'sem áudio' if codigo == 0 else 'falhou',
                        'videos': videos, 'info': info, 'motivo': diagnostico or
                        ('nenhum áudio reconhecido' if codigo == 0 else _erro_seguro(erro))} 
        except subprocess.TimeoutExpired:
            return {'nome': nome, 'estado': 'falhou', 'motivo': 'tempo esgotado'}
        except Exception:
            return {'nome': nome, 'estado': 'falhou', 'motivo': 'erro ao executar ou ler os cookies'}

    escolhidos = tuple(range(4)) if indices is None else tuple(indices)
    if not escolhidos or any(i not in range(4) for i in escolhidos):
        raise ValueError('Seleção inválida de métodos')
    resultados = [{'nome': nome, 'estado': 'consultando' if i in escolhidos else 'aguardando',
                   'formatos': []} for i, nome in enumerate(NOMES)]
    with ThreadPoolExecutor(max_workers=len(escolhidos)) as pool:
        futuros = {pool.submit(metodo, i): i for i in escolhidos}
        for futuro in as_completed(futuros):
            resultados[futuros[futuro]] = futuro.result()
            if ao_parcial and any(r.get('formatos') for r in resultados):
                try:
                    ao_parcial(_consolidar(resultados))
                except Exception:
                    pass  # uma falha de interface não interrompe a consulta
    return _consolidar(resultados)


def _consolidar(resultados: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Combina somente dados técnicos, inclusive enquanto métodos estão pendentes."""
    # Priorizar metadados estruturados sobre os inferidos da tabela de texto.
    por_id: Dict[str, Dict[str, Any]] = {}
    for r in sorted(resultados, key=lambda x: x['nome'] == NOMES[0]):
        for formato in r.get('formatos', []):
            ident = str(formato['format_id'])
            if ident not in por_id:
                por_id[ident] = dict(formato, _metodos=[])
            destino = por_id[ident]
            if r['nome'] not in destino['_metodos']:
                destino['_metodos'].append(r['nome'])
            ja_tinha_bitrate = destino.get('abr') not in (None, '')
            for k, v in formato.items():
                if k == '_abr_da_tabela' and ja_tinha_bitrate and '_abr_da_tabela' not in destino:
                    continue
                if destino.get(k) in (None, '', 'unknown') and v not in (None, '', 'unknown'):
                    destino[k] = v
    ids_video = set(por_id)
    for r in resultados:
        for video in r.get('videos', []):
            vid = str(video.get('format_id') or '')
            if vid and vid not in ids_video:
                por_id[vid] = video
                ids_video.add(vid)
    # Mesmo ID pode chegar com campos diferentes de processos/versões distintos.
    # Preservar divergências em dados técnicos, sem guardar URLs nem cabeçalhos.
    chaves_comparaveis = ('acodec', 'vcodec', 'abr', 'asr', 'audio_channels', 'ext', 'tbr')
    observacoes: Dict[str, Dict[str, Dict[str, Any]]] = {}
    arredondados: Dict[str, set[str]] = {}
    for r in resultados:
        for f in r.get('formatos', []) + r.get('videos', []):
            ident = str(f.get('format_id') or '')
            if ident not in por_id:
                continue
            for campo in chaves_comparaveis:
                valor = f.get(campo)
                if not isinstance(valor, (str, int, float)) or valor in ('', 'unknown'):
                    continue
                observacoes.setdefault(ident, {}).setdefault(campo, {})[r['nome']] = valor
                if campo == 'abr' and f.get('_abr_da_tabela'):
                    arredondados.setdefault(ident, set()).add(r['nome'])
    for ident, campos_por_metodo in observacoes.items():
        divergencias = {}
        for campo, valores in campos_por_metodo.items():
            def diferente(a, b):
                na, va = a
                nb, vb = b
                try:
                    if campo in ('abr', 'asr', 'audio_channels', 'tbr'):
                        va, vb = float(va), float(vb)
                        if campo == 'abr' and (na in arredondados.get(ident, set()) or nb in arredondados.get(ident, set())):
                            return abs(va - vb) > 0.5
                        return va != vb
                except (TypeError, ValueError):
                    pass
                return str(va).lower() != str(vb).lower()
            itens = list(valores.items())
            if any(diferente(itens[i], itens[j]) for i in range(len(itens)) for j in range(i)):
                divergencias[campo] = valores
        if divergencias:
            por_id[ident]['_divergencias'] = divergencias
    info_unificada: Dict[str, Any] = {}
    for r in resultados:
        for k, v in r.get('info', {}).items():
            if k not in info_unificada and v not in (None, '', []):
                info_unificada[k] = v
    resumo = [{k: v for k, v in r.items() if k not in ('formatos', 'videos', 'info')} |
              {'quantidade': len(r.get('formatos', []))} for r in resultados]
    return {**info_unificada, 'formats': list(por_id.values()), 'metodos': resumo}

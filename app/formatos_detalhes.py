"""Texto de comparação dos formatos, usando só valores efetivamente informados."""
from __future__ import annotations

import math
import re
from typing import Any, Dict

from .models import AudioFormat, bytes_legivel


def _numero(valor: Any, unidade: str = '') -> str:
    try:
        num = float(valor)
        if not math.isfinite(num) or num <= 0:
            return 'não informado'
        return f'{num:g}{unidade}'
    except (TypeError, ValueError):
        return 'não informado'


def _texto(valor: Any) -> str:
    if valor in (None, '', 'unknown', '?'):
        return 'não informado'
    texto = re.sub(r'https?://\S+', '[link omitido]', str(valor))
    return ' '.join(texto.split())[:200]


def campos(fmt: AudioFormat) -> Dict[str, str]:
    """Valores exibíveis sem confundir bitrate total com bitrate de áudio."""
    dados = fmt.extra.get('detalhes_audio') or {}
    codec_original = _texto(dados.get('acodec') or fmt.codec)
    codec = (f'{fmt.codec.upper()} ({codec_original})'
             if codec_original != 'não informado' and fmt.codec not in ('', '?', 'unknown')
             and fmt.codec.lower() != codec_original.lower() else codec_original)
    vcodec = dados.get('vcodec')
    if vcodec == 'none':
        tipo = 'Somente áudio'
    elif vcodec and vcodec != 'unknown':
        tipo = 'Áudio + vídeo'
    else:
        tipo = 'Não informado'
    divergencias = fmt.extra.get('divergencias') or {}
    if str(dados.get('acodec') or '').lower() == 'unknown' or 'acodec' in divergencias:
        tipo += ' (áudio não confirmado)'
    tamanho = dados.get('filesize') or fmt.filesize
    aproximado = False
    if not dados.get('filesize') and dados.get('filesize_approx'):
        tamanho, aproximado = dados['filesize_approx'], True
    try:
        tamanho_num = float(tamanho)
        tamanho_texto = bytes_legivel(tamanho_num) if math.isfinite(tamanho_num) and tamanho_num > 0 else 'não informado'
    except (TypeError, ValueError):
        tamanho_texto = 'não informado'
    if aproximado and tamanho_texto != 'não informado':
        tamanho_texto += ' (aproximado)'
    canais = dados.get('audio_channels') or fmt.channels
    canais_txt = _numero(canais)
    if canais_txt == '1':
        canais_txt = '1 (mono)'
    elif canais_txt == '2':
        canais_txt = '2 (estéreo)'
    metodos = fmt.extra.get('metodos') or []
    divergencias_txt = []
    nomes_campos = {'acodec':'codec de áudio', 'vcodec':'codec de vídeo',
                    'abr':'bitrate de áudio', 'asr':'amostragem',
                    'audio_channels':'canais', 'ext':'contêiner', 'tbr':'bitrate total'}
    for campo, valores in divergencias.items():
        if campo in nomes_campos and isinstance(valores, dict):
            pares = ', '.join(f'{_texto(k)}: {_texto(v)}' for k, v in valores.items())
            divergencias_txt.append(nomes_campos[campo] + ' (' + pares + ')')
    bitrate_audio = _numero(dados.get('abr') or fmt.bitrate_kbps, ' kbps')
    if dados.get('_abr_da_tabela') and bitrate_audio != 'não informado':
        bitrate_audio += ' (arredondado da tabela)'
    amostragem = _numero(dados.get('asr') or fmt.sample_rate, ' Hz')
    if amostragem == 'não informado' and dados.get('_asr_tabela'):
        amostragem = _texto(dados['_asr_tabela']) + ' Hz (tabela, arredondado)'
    return {
        'ID': _texto(fmt.format_id),
        'Codec': codec,
        'Bitrate áudio': bitrate_audio,
        'Amostragem': amostragem,
        'Canais': canais_txt,
        'Contêiner': _texto(dados.get('ext') or fmt.container),
        'Tipo': tipo,
        'Tamanho': tamanho_texto,
        'Bits por amostra': _numero(dados.get('bits_per_sample'), ' bits'),
        'Proteção DRM': ('sim' if dados.get('has_drm') is True else
                         'não' if dados.get('has_drm') is False else 'não informado'),
        'Bitrate total': _numero(dados.get('tbr'), ' kbps'),
        'Codec de vídeo': _texto(vcodec if vcodec != 'none' else 'sem vídeo'),
        'Idioma': _texto(dados.get('language')),
        'Protocolo': _texto(dados.get('protocol')),
        'Nota da fonte': _texto(dados.get('format_note') or fmt.extra.get('nota')),
        'Métodos': ', '.join(str(x) for x in metodos) if metodos else 'não informado',
        'Divergências entre métodos': '; '.join(divergencias_txt) if divergencias_txt else 'nenhuma detectada nos campos comparados',
    }

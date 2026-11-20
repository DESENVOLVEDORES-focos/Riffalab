"""Consulta isolada pela biblioteca Python do yt-dlp; não baixa o áudio."""
from __future__ import annotations

import json
import sys


def main() -> int:
    try:
        import yt_dlp
        from yt_dlp.version import __version__
    except ImportError:
        print('Biblioteca yt-dlp não instalada', file=sys.stderr)
        return 3
    url, cookies, ffmpeg, _diretorio_exe = sys.argv[1:5]
    opcoes = {'quiet': True, 'no_warnings': False, 'noplaylist': True,
              'skip_download': True, 'socket_timeout': 20, 'retries': 1,
              'cachedir': False, 'format': 'all', 'ignore_no_formats_error': True}
    if cookies:
        opcoes['cookiefile'] = cookies
    if ffmpeg:
        opcoes['ffmpeg_location'] = ffmpeg
    # O Deno local está no PATH privado recebido do processo principal.
    try:
        with yt_dlp.YoutubeDL(opcoes) as ydl:
            resultado = ydl.extract_info(url, download=False) or {}
            # Nunca retornar URL de mídia, cabeçalhos ou dados pessoais.
            campos = ('format_id', 'ext', 'acodec', 'vcodec', 'abr', 'asr',
                      'audio_channels', 'filesize', 'filesize_approx', 'format_note',
                      'height', 'fps', 'vbr', 'tbr', 'resolution', 'language', 'protocol',
                      'audio_ext', 'dynamic_range', 'container', 'bits_per_sample', 'has_drm')
            formatos = [{k: f[k] for k in campos if k in f}
                        for f in resultado.get('formats') or [] if isinstance(f, dict)]
            print(json.dumps({'formats': formatos, '_versao_biblioteca': __version__}, ensure_ascii=False))
            return 0
    except Exception as exc:
        # O texto do erro do yt-dlp pode conter links temporários ou caminhos privados.
        print(f'Falha na consulta pela biblioteca ({type(exc).__name__})', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

"""Identificação local de MP3s do RiffLab, sem alterar os arquivos encontrados."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Sequence

from mutagen.id3 import ID3, ID3NoHeaderError

from .models import TrackResult
from .texto import normalizar

MARCA = 'RiffLab'
PREFIXO = 'RiffLab:'


def identidade(resultado: TrackResult) -> tuple[str, str]:
    fonte = str(resultado.fonte or '').strip()
    uid = str(resultado.uid or '').strip()
    if not fonte or not uid or uid.lower() in ('none', 'ytdlpid:none'):
        return '', ''
    return fonte, uid


def marcar(caminho: str | Path, resultado: TrackResult) -> None:
    """Marca somente o novo MP3, mantendo comentários e outras tags existentes."""
    from mutagen.id3 import COMM, TXXX
    try:
        tags = ID3(str(caminho))
    except ID3NoHeaderError:
        tags = ID3()
    # Se a origem já era MP3, remover apenas os nossos campos anteriores.
    for frame in list(tags.getall('TXXX')):
        if frame.desc.startswith(PREFIXO):
            tags.delall(frame.HashKey)
    # Comentário comum é mais visível em exploradores de arquivos. Não
    # sobrescrevemos o comentário pré-existente de um MP3 copiado.
    if not tags.get('COMM::eng'):
        tags.add(COMM(encoding=3, lang='eng', desc='', text=[MARCA]))
    tags.add(COMM(encoding=3, lang='eng', desc='RiffLab', text=[MARCA]))
    fonte, uid = identidade(resultado)
    for nome, valor in (('marca', MARCA), ('fonte', fonte), ('id', uid),
                        ('titulo original', resultado.titulo),
                        ('artista original', resultado.artista)):
        if valor:
            tags.add(TXXX(encoding=3, desc=PREFIXO + nome, text=[str(valor)]))
    tags.save(str(caminho), v2_version=3)


def _texto(tags: ID3, chave: str) -> str:
    frame = tags.get(chave)
    return str(frame.text[0]).strip() if frame and frame.text else ''


def _ler(caminho: str) -> Dict[str, str] | None:
    tags = ID3(caminho)
    marcada = _texto(tags, 'TXXX:RiffLab:marca').casefold() == 'rifflab'
    if not marcada:
        marcada = any(any(str(t).strip().casefold() == 'rifflab' for t in c.text)
                      for c in tags.getall('COMM'))
    if not marcada:
        return None
    return {'fonte': _texto(tags, 'TXXX:RiffLab:fonte'),
            'uid': _texto(tags, 'TXXX:RiffLab:id'),
            'titulo': _texto(tags, 'TIT2'), 'artista': _texto(tags, 'TPE1'),
            'titulo_original': _texto(tags, 'TXXX:RiffLab:titulo original'),
            'artista_original': _texto(tags, 'TXXX:RiffLab:artista original'),
            'caminho': caminho}


def conferir(resultados: Sequence[TrackResult], pastas: Sequence[str]) -> Dict[str, Any]:
    """Varre pastas e subpastas, sem seguir links de diretório. Nunca escreve."""
    por_id: Dict[tuple[str, str], str] = {}
    por_musica: Dict[tuple[str, str], str] = {}
    erros: List[str] = []
    arquivos = marcados = 0
    visitadas = set()
    for pasta in pastas:
        if not pasta:
            continue
        raiz = Path(pasta).expanduser()
        try:
            real = os.path.normcase(os.path.realpath(raiz))
            if real in visitadas:
                continue
            visitadas.add(real)
            if not raiz.is_dir():
                erros.append(f'Pasta indisponível: {raiz}')
                continue
            for diretorio, _, nomes in os.walk(raiz, followlinks=False,
                                                onerror=lambda e: erros.append(str(e))):
                for nome in nomes:
                    if not nome.lower().endswith('.mp3'):
                        continue
                    arquivos += 1
                    caminho = os.path.join(diretorio, nome)
                    try:
                        item = _ler(caminho)
                    except ID3NoHeaderError:
                        continue
                    except Exception as exc:
                        erros.append(f'{caminho}: {exc}')
                        continue
                    if not item:
                        continue
                    marcados += 1
                    if item['fonte'] and item['uid']:
                        por_id.setdefault((item['fonte'], item['uid']), caminho)
                    for a, t in ((item['artista'], item['titulo']),
                                 (item['artista_original'], item['titulo_original'])):
                        par = (normalizar(a), normalizar(t))
                        if all(par):
                            por_musica.setdefault(par, caminho)
        except OSError as exc:
            erros.append(f'{raiz}: {exc}')
    correspondencias = []
    for r in resultados:
        chave = identidade(r)
        caminho = por_id.get(chave) if all(chave) else None
        if caminho:
            correspondencias.append({'tipo': 'id', 'caminho': caminho})
            continue
        par = (normalizar(r.artista), normalizar(r.titulo))
        caminho = por_musica.get(par) if all(par) else None
        correspondencias.append({'tipo': 'possivel', 'caminho': caminho} if caminho else None)
    return {'correspondencias': correspondencias, 'arquivos': arquivos,
            'marcados': marcados, 'erros': erros}

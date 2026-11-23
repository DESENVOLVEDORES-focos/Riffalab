"""Inspeção somente de leitura de MP3s e imagens ID3/APIC existentes.

Não procura imagens na internet nem em arquivos de pasta e não altera tags.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from mutagen.id3 import ID3, ID3NoHeaderError

MAX_ARQUIVOS = 5000
MAX_IMAGEM = 20 * 1024 * 1024


def ler_mp3(caminho: str | Path, incluir_imagens: bool = False) -> dict[str, Any]:
    p = Path(caminho)
    item: dict[str, Any] = {'caminho': str(p), 'titulo': p.stem, 'artista': '',
                            'album': '', 'estado': '', 'quantidade': 0, 'imagens': []}
    try:
        tags = ID3(str(p))
    except ID3NoHeaderError:
        item['estado'] = 'Sem tags ID3'
        return item
    except Exception as exc:
        item['estado'] = 'Erro de leitura'
        item['erro'] = f'{type(exc).__name__}: {exc}'
        return item
    for campo, chave in (('titulo', 'TIT2'), ('artista', 'TPE1'), ('album', 'TALB')):
        frame = tags.get(chave)
        if frame is not None and getattr(frame, 'text', None):
            item[campo] = str(frame.text[0])
    if incluir_imagens:
        for campo, chave in (('genero', 'TCON'), ('ano', 'TDRC'),
                             ('faixa', 'TRCK'), ('artista_album', 'TPE2')):
            frame = tags.get(chave)
            item[campo] = str(frame.text[0]) if frame is not None and getattr(frame, 'text', None) else ''
        try:
            from mutagen.mp3 import MP3
            item['duracao_s'] = MP3(str(p)).info.length
        except Exception:
            item['duracao_s'] = None
    apics = tags.getall('APIC')
    # Mostrar a capa frontal primeiro, sem ocultar outras imagens APIC.
    apics.sort(key=lambda f: 0 if int(f.type) == 3 else 1)
    item['quantidade'] = len(apics)
    item['estado'] = 'Com imagem ID3' if apics else 'Sem imagem ID3'
    if incluir_imagens:
        for frame in apics:
            dados = bytes(frame.data)
            item['imagens'].append({'tipo': int(frame.type), 'descricao': str(frame.desc or ''),
                                    'mime': str(frame.mime or ''), 'tamanho': len(dados),
                                    'dados': dados if len(dados) <= MAX_IMAGEM else b''})
    return item


def listar_mp3(pasta: str | Path) -> dict[str, Any]:
    """Lista arquivos e lê suas tags em segundo plano, sem seguir pastas linkadas."""
    raiz = Path(pasta).expanduser()
    if not raiz.is_dir():
        raise ValueError(f'Pasta indisponível: {raiz}')
    caminhos: list[str] = []
    erros: list[str] = []
    truncado = False
    for diretorio, subpastas, nomes in os.walk(raiz, followlinks=False,
                                              onerror=lambda erro: erros.append(str(erro))):
        subpastas.sort(key=str.casefold)
        for nome in sorted(nomes, key=str.casefold):
            if nome.lower().endswith('.mp3'):
                if len(caminhos) >= MAX_ARQUIVOS:
                    truncado = True
                    break
                caminhos.append(os.path.join(diretorio, nome))
        if truncado:
            break
    itens = [ler_mp3(caminho) for caminho in caminhos]
    return {'pasta': str(raiz), 'itens': itens, 'erros': erros, 'truncado': truncado}

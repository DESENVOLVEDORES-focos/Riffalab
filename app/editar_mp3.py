"""Edição segura de tags de UM MP3 existente, sem recodificar seu áudio."""
from __future__ import annotations

import datetime
import hashlib
import os
import re
import shutil
import stat
import tempfile
from pathlib import Path
from typing import Any

from mutagen.id3 import APIC, ID3, ID3NoHeaderError, TALB, TCON, TDRC, TIT2, TPE1, TPE2, TRCK

CAMPOS = {'titulo': ('TIT2', TIT2), 'artista': ('TPE1', TPE1),
          'album': ('TALB', TALB), 'genero': ('TCON', TCON),
          'ano': ('TDRC', TDRC), 'faixa': ('TRCK', TRCK),
          'artista_album': ('TPE2', TPE2)}


def _arquivo(caminho: str | Path) -> Path:
    p = Path(caminho).expanduser().absolute()
    if p.suffix.lower() != '.mp3' or p.is_symlink():
        raise ValueError('Escolha um arquivo MP3 comum, não um link simbólico.')
    st = p.stat()
    if not stat.S_ISREG(st.st_mode):
        raise ValueError('O caminho não é um arquivo comum.')
    if st.st_nlink > 1:
        raise ValueError('Este arquivo tem links físicos. Faça uma cópia independente antes de editar.')
    return p


def _digest(p: Path) -> str:
    h = hashlib.sha256()
    with p.open('rb') as f:
        for bloco in iter(lambda: f.read(1024 * 1024), b''):
            h.update(bloco)
    return h.hexdigest()


def _stat(p: Path):
    s = p.stat()
    return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)


def _ler_id3(p: Path):
    try:
        return ID3(str(p), translate=False)
    except ID3NoHeaderError:
        return ID3()


def abrir(caminho: str | Path) -> dict[str, Any]:
    """Lê campos reais e calcula uma impressão para detectar alterações externas."""
    p = _arquivo(caminho)
    antes = _stat(p)
    tags = _ler_id3(p)
    if tags.version[0] != 1 and tags.version[1] not in (3, 4):
        raise ValueError('Esta versão de ID3 não pode ser editada com segurança; faça uma cópia e atualize as tags em outro editor.')
    campos = {}
    for nome, (chave, _) in CAMPOS.items():
        frame = tags.get(chave)
        campos[nome] = str(frame.text[0]) if frame and getattr(frame, 'text', None) else ''
    digest = _digest(p)
    if antes != _stat(p):
        raise RuntimeError('O arquivo mudou durante a leitura. Atualize e tente novamente.')
    return {'caminho': str(p), 'campos': campos, 'sha256': digest, 'stat': antes}


def validar_alteracoes(alteracoes: dict[str, str]) -> None:
    if not isinstance(alteracoes, dict) or any(k not in CAMPOS for k in alteracoes):
        raise ValueError('Campos de edição inválidos.')
    for nome, valor in alteracoes.items():
        if not isinstance(valor, str) or '\x00' in valor or len(valor) > 4096:
            raise ValueError(f'Valor inválido em {nome}.')
    data = alteracoes.get('ano', '')
    if data:
        if not re.fullmatch(r'\d{4}(?:-\d{2}(?:-\d{2})?)?', data) or int(data[:4]) < 1:
            raise ValueError('Informe o ano como AAAA, AAAA-MM ou AAAA-MM-DD.')
        try:
            if len(data) == 7:
                datetime.date(int(data[:4]), int(data[5:7]), 1)
            elif len(data) == 10:
                datetime.date.fromisoformat(data)
        except ValueError:
            raise ValueError('Informe uma data válida.') from None
    faixa = alteracoes.get('faixa', '')
    if faixa and (not re.fullmatch(r'\d{1,4}(?:/\d{1,4})?', faixa) or
                  any(int(n) < 1 for n in faixa.split('/'))):
        raise ValueError('Informe a faixa como número ou número/total.')


def _validar_capa(dados: bytes):
    from .metadata.capa_validacao import validar
    from .image_utils import extensao
    if not isinstance(dados, bytes) or len(dados) > 15 * 1024 * 1024:
        raise ValueError('Imagem inválida ou maior que 15 MB.')
    ext = extensao(dados)
    if ext not in ('.jpg', '.png'):
        raise ValueError('Use uma imagem JPEG ou PNG válida.')
    validacao = validar(dados, minimo_lado=300)
    if not validacao.ok:
        raise ValueError('Imagem inválida: ' + validacao.motivo)
    if max(validacao.largura, validacao.altura) > 6000:
        raise ValueError('Imagem maior que 6000 pixels por lado.')
    return 'image/jpeg' if ext == '.jpg' else 'image/png'


def _criar_backup(origem: Path, copia: Path) -> Path:
    """Nunca substitui outro backup. A cópia deve ser integral antes de continuar."""
    for i in range(10000):
        sufixo = '' if i == 0 else f'-{i}'
        destino = origem.with_name(origem.name + f'.rifflab-backup{sufixo}')
        try:
            with destino.open('xb') as out, copia.open('rb') as entrada:
                try:
                    shutil.copyfileobj(entrada, out, length=1024 * 1024)
                    out.flush()
                    os.fsync(out.fileno())
                except BaseException:
                    out.close()
                    destino.unlink(missing_ok=True)
                    raise
            shutil.copystat(origem, destino)
            return destino
        except FileExistsError:
            continue
    raise OSError('Não foi possível criar um nome livre para o backup.')


def salvar(snapshot: dict, alteracoes: dict[str, str], capa_acao: str = 'manter',
           capa_dados: bytes = b'') -> dict:
    """Trabalha numa cópia e só substitui o original após backup e verificação.

    A capa frontal é a única imagem trocada/removida; outras APIC são mantidas.
    """
    validar_alteracoes(alteracoes)
    if capa_acao not in ('manter', 'trocar', 'remover'):
        raise ValueError('Ação de capa inválida.')
    mime = _validar_capa(capa_dados) if capa_acao == 'trocar' else ''
    if not alteracoes and capa_acao == 'manter':
        return {'alterado': False, 'backup': ''}
    p = _arquivo(snapshot['caminho'])
    if _stat(p) != tuple(snapshot['stat']) or _digest(p) != snapshot['sha256']:
        raise RuntimeError('O MP3 mudou desde que foi aberto. Atualize a lista e reabra o editor; nada foi alterado.')
    descritor, nome_temp = tempfile.mkstemp(prefix='.rifflab-edicao-', suffix='.tmp', dir=str(p.parent))
    os.close(descritor)
    temp = Path(nome_temp)
    backup = None
    try:
        shutil.copy2(p, temp)
        if _digest(temp) != snapshot['sha256'] or _stat(p) != tuple(snapshot['stat']):
            raise RuntimeError('O MP3 mudou durante a cópia; nada foi alterado.')
        tags = _ler_id3(temp)
        versao = 4 if tags.version[0] == 1 else tags.version[1]
        if versao not in (3, 4):
            raise ValueError('Versão ID3 não suportada com segurança.')
        for nome, valor in alteracoes.items():
            chave, cls = CAMPOS[nome]
            tags.delall(chave)
            if nome == 'ano':
                tags.delall('TYER')
                tags.delall('TDAT')
            if valor:
                tags.add(cls(encoding=3, text=valor))
        if capa_acao != 'manter':
            outras = [imagem for imagem in tags.getall('APIC') if int(imagem.type) != 3]
            tags.delall('APIC')
            for imagem in outras:
                tags.add(imagem)
            if capa_acao == 'trocar':
                descricoes = {str(imagem.desc) for imagem in outras}
                descricao = 'RiffLab capa frontal'
                while descricao in descricoes:
                    descricao += '_'
                tags.add(APIC(encoding=3, mime=mime, type=3, desc=descricao, data=capa_dados))
        tags.save(str(temp), v2_version=versao, v1=1)
        # Não tocar no original até confirmar que a cópia editada é legível.
        verificacao = _ler_id3(temp)
        for nome, valor in alteracoes.items():
            frame = verificacao.get(CAMPOS[nome][0])
            lido = str(frame.text[0]) if frame and getattr(frame, 'text', None) else ''
            if lido != valor:
                raise RuntimeError(f'Não foi possível confirmar a gravação de {nome}.')
        if capa_acao == 'trocar' and not any(int(x.type) == 3 and bytes(x.data) == capa_dados for x in verificacao.getall('APIC')):
            raise RuntimeError('Não foi possível confirmar a nova capa.')
        if capa_acao == 'remover' and any(int(x.type) == 3 for x in verificacao.getall('APIC')):
            raise RuntimeError('Não foi possível remover a capa frontal.')
        if _stat(p) != tuple(snapshot['stat']) or _digest(p) != snapshot['sha256']:
            raise RuntimeError('O MP3 mudou durante a edição; nada foi substituído.')
        # Backup é da versão original exata, não da cópia já alterada.
        backup = _criar_backup(p, p)
        if _digest(backup) != snapshot['sha256'] or _stat(p) != tuple(snapshot['stat']) or _digest(p) != snapshot['sha256']:
            raise RuntimeError('O MP3 mudou durante o backup; nada foi substituído.')
        with temp.open('r+b') as arquivo:
            arquivo.flush()
            os.fsync(arquivo.fileno())
        os.replace(temp, p)
        return {'alterado': True, 'backup': str(backup)}
    finally:
        temp.unlink(missing_ok=True)

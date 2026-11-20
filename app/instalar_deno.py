"""Instala o Deno oficial em ferramentas/ no Windows, com SHA-256 fixo."""
from __future__ import annotations

import hashlib
import os
import platform
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PASTA = RAIZ / 'ferramentas'
VERSAO = 'v2.9.8'
BASE = 'https://github.com/denoland/deno/releases/download/' + VERSAO + '/'
ARQUIVOS = {
    'amd64': ('deno-x86_64-pc-windows-msvc.zip',
              'cba84b26e0df5ae7f74fc66b86a95b866872a86292ebd84fa1e959927edd93bf'),
    'arm64': ('deno-aarch64-pc-windows-msvc.zip',
              'b413b92b735b50c198e8fe3b85af1aa50e29d5f72e229aab701d132286e14cef'),
}
MAX_ZIP = 80 * 1024 * 1024
MAX_EXE = 200 * 1024 * 1024


def arquitetura() -> str:
    maquina = (os.environ.get('PROCESSOR_ARCHITEW6432') or
               os.environ.get('PROCESSOR_ARCHITECTURE') or platform.machine()).lower()
    if maquina in ('amd64', 'x86_64'):
        return 'amd64'
    if maquina in ('arm64', 'aarch64'):
        return 'arm64'
    return ''


def instalar(pasta: Path = PASTA) -> str:
    destino = pasta / 'deno.exe'
    if destino.exists():
        return 'Deno ja existe em ferramentas; arquivo preservado.'
    arch = arquitetura()
    if arch not in ARQUIVOS:
        raise RuntimeError('Arquitetura nao suportada; e necessario Windows 64 bits.')
    arquivo, esperado = ARQUIVOS[arch]
    pasta.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.deno-', dir=str(pasta)) as temp:
        pacote = Path(temp) / 'deno.zip'
        digest = hashlib.sha256()
        tamanho = 0
        request = urllib.request.Request(BASE + arquivo, headers={'User-Agent': 'RiffLab-Deno-Installer'})
        with urllib.request.urlopen(request, timeout=45) as resposta, pacote.open('wb') as saida:
            while True:
                parte = resposta.read(1024 * 1024)
                if not parte:
                    break
                tamanho += len(parte)
                if tamanho > MAX_ZIP:
                    raise RuntimeError('Download excedeu o tamanho esperado.')
                digest.update(parte)
                saida.write(parte)
        if digest.hexdigest() != esperado:
            raise RuntimeError('SHA-256 do download nao confere; instalacao cancelada.')
        with zipfile.ZipFile(pacote) as zipado:
            arquivos = [i for i in zipado.infolist() if i.filename == 'deno.exe' and not i.is_dir()]
            if len(arquivos) != 1 or not 0 < arquivos[0].file_size <= MAX_EXE:
                raise RuntimeError('O pacote nao contem um deno.exe valido.')
            temporario = Path(temp) / 'deno.exe'
            with zipado.open(arquivos[0]) as origem, temporario.open('wb') as saida:
                shutil.copyfileobj(origem, saida)
        # No Windows rename não sobrescreve um destino existente; o arquivo
        # só aparece quando estiver completo. Em outros sistemas, link evita
        # substituição (útil também para os testes).
        if sys.platform == 'win32':
            os.rename(temporario, destino)
        else:
            os.link(temporario, destino)
    return 'Deno ' + VERSAO + ' instalado em ferramentas\\deno.exe.'


def main() -> int:
    if sys.platform != 'win32':
        print('Este instalador e somente para Windows.')
        return 1
    try:
        print('Baixando Deno oficial do GitHub (aproximadamente 43 MB)...', flush=True)
        print(instalar())
        return 0
    except Exception as exc:
        print('Nao foi possivel instalar o Deno:', str(exc))
        print('O RiffLab ainda pode abrir. Tente INSTALAR_DENO.bat novamente.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

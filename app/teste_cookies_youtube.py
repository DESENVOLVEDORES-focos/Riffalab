"""Teste explícito de acesso à lista pessoal Assistir mais tarde do YouTube.

Não registra a resposta nem qualquer detalhe da conta. Uma resposta genérica
ou lista vazia não demonstra autenticação; nunca afirmar sucesso nesses casos.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path

from .config import CRIAR_SEM_JANELA
from .tools import ambiente_ferramentas, ytdlp

_URL = 'https://www.youtube.com/playlist?list=WL'
_INCONCLUSIVO = ('Não foi possível confirmar a sessão. Isso também pode ocorrer se a lista '
                 'Assistir mais tarde estiver vazia ou se o YouTube mudar a resposta. '
                 'O teste não confirma se o download de áudio vai funcionar.')


def _resultado(estado: str, mensagem: str) -> dict:
    return {'estado': estado, 'mensagem': mensagem}


def testar(caminho: str | Path) -> dict:
    """Consulta no máximo um item, somente após o usuário solicitar o teste.

    A única confirmação positiva é uma resposta de playlist pessoal WL com uma
    entrada de vídeo reconhecível. A saída privada nunca é retornada ou logada.
    """
    origem = Path(caminho)
    ferramenta = ytdlp()
    if not ferramenta.ok:
        return _resultado('indisponivel', 'yt-dlp não encontrado. Verifique Ferramentas externas.')
    try:
        conteudo = origem.read_bytes()
        if not conteudo:
            return _resultado('arquivo', 'O arquivo de cookies está vazio.')
        antes = hashlib.sha256(conteudo).digest()
        with tempfile.TemporaryDirectory(prefix='rifflab-cookies-') as pasta:
            copia = Path(pasta) / 'cookies.txt'
            copia.write_bytes(conteudo)
            # Sem configurações externas nem extração de cookies do navegador.
            comando = [ferramenta.caminho, '--ignore-config', '--no-color', '--no-cache-dir',
                       '--socket-timeout', '15', '--retries', '1', '--cookies', str(copia),
                       '--flat-playlist', '--playlist-items', '1', '--dump-single-json',
                       '--simulate', '--skip-download', '--', _URL]
            p = subprocess.run(comando, capture_output=True, text=True,
                               encoding='utf-8', errors='replace', timeout=90,
                               creationflags=CRIAR_SEM_JANELA, env=ambiente_ferramentas())
        # Não inferir o estado atual de um arquivo alterado durante o teste.
        if hashlib.sha256(origem.read_bytes()).digest() != antes:
            return _resultado('inconclusivo', 'O arquivo de cookies mudou durante o teste. Execute novamente.')
        if p.returncode:
            erro = (p.stderr or '').lower()
            if 'sign in' in erro or 'login required' in erro or 'requires authentication' in erro:
                return _resultado('login', 'O YouTube ou yt-dlp pediu autenticação. Os cookies podem estar '
                                  'expirados, incompletos ou não aceitos; o teste não identifica a causa exata.')
            if '403' in erro:
                return _resultado('recusado', 'O YouTube recusou a consulta (HTTP 403). Isso não prova '
                                  'que os cookies estejam inválidos.')
            if '429' in erro:
                return _resultado('limite', 'O YouTube limitou as consultas (HTTP 429). Aguarde e tente depois.')
            return _resultado('inconclusivo', _INCONCLUSIVO)
        try:
            dados = json.loads(p.stdout)
        except (ValueError, TypeError):
            return _resultado('inconclusivo', _INCONCLUSIVO)
        if not isinstance(dados, dict):
            return _resultado('inconclusivo', _INCONCLUSIVO)
        itens = dados.get('entries')
        confirmado = (dados.get('_type') == 'playlist' and dados.get('id') == 'WL'
                      and isinstance(itens, list) and any(
                          isinstance(i, dict) and re.fullmatch(r'[A-Za-z0-9_-]{11}', str(i.get('id') or ''))
                          for i in itens))
        if not confirmado:
            return _resultado('inconclusivo', _INCONCLUSIVO)
        return _resultado('confirmado', 'O YouTube retornou um item da lista pessoal Assistir mais tarde '
                          'usando a cópia dos cookies. A sessão funcionou nesta consulta; '
                          'isso não garante downloads nem acesso a todos os vídeos.')
    except subprocess.TimeoutExpired:
        return _resultado('tempo', 'O teste demorou demais. Não foi possível confirmar a sessão.')
    except (OSError, ValueError):
        return _resultado('arquivo', 'Não foi possível ler o arquivo, criar uma cópia temporária ou executar o yt-dlp.')

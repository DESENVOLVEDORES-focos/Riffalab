"""Instalação e integração do Deno sem rede, com pacote de teste simulado."""
import hashlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from app import instalar_deno, tools
from app.sources.ytdlp import FonteYtDlp


def pacote_simulado():
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('deno.exe', b'arquivo de teste, nao executavel')
        z.writestr('../nao_extrair.txt', b'nao deve ser extraido')
    return saida.getvalue()


class Deno(unittest.TestCase):
    def test_instala_somente_exe_validado_sem_sobrescrever(self):
        pacote = pacote_simulado()
        checksum = hashlib.sha256(pacote).hexdigest()
        with tempfile.TemporaryDirectory() as d:
            pasta = Path(d) / 'pasta com espacos' / 'ferramentas'
            with patch.object(instalar_deno, 'arquitetura', return_value='amd64'), \
                 patch.dict(instalar_deno.ARQUIVOS, {'amd64': ('teste.zip', checksum)}), \
                 patch.object(instalar_deno.urllib.request, 'urlopen', return_value=io.BytesIO(pacote)) as requisicao:
                instalar_deno.instalar(pasta)
                self.assertEqual((pasta / 'deno.exe').read_bytes(), b'arquivo de teste, nao executavel')
                self.assertFalse((pasta.parent / 'nao_extrair.txt').exists())
                self.assertEqual([p.name for p in pasta.iterdir()], ['deno.exe'])
                instalar_deno.instalar(pasta)
                self.assertEqual(requisicao.call_count, 1)

    def test_checksum_errado_nao_deixa_executavel(self):
        with tempfile.TemporaryDirectory() as d:
            pasta = Path(d) / 'ferramentas'
            with patch.object(instalar_deno, 'arquitetura', return_value='amd64'), \
                 patch.dict(instalar_deno.ARQUIVOS, {'amd64': ('teste.zip', '0' * 64)}), \
                 patch.object(instalar_deno.urllib.request, 'urlopen', return_value=io.BytesIO(pacote_simulado())):
                with self.assertRaisesRegex(RuntimeError, 'SHA-256'):
                    instalar_deno.instalar(pasta)
            self.assertFalse((pasta / 'deno.exe').exists())
            self.assertEqual(list(pasta.iterdir()), [])

    def test_arquitetura_nao_suportada_sem_download(self):
        with tempfile.TemporaryDirectory() as d, \
             patch.object(instalar_deno, 'arquitetura', return_value=''), \
             patch.object(instalar_deno.urllib.request, 'urlopen') as rede:
            with self.assertRaisesRegex(RuntimeError, 'Arquitetura'):
                instalar_deno.instalar(Path(d))
            rede.assert_not_called()

    def test_status_valida_deno_e_versao(self):
        resposta = subprocess.CompletedProcess([], 0, stdout='deno 2.9.8\nv8 14.0\n', stderr='')
        with patch.object(tools.subprocess, 'run', return_value=resposta) as executou:
            versao, erro = tools._versao('deno.exe')
        self.assertEqual((versao, erro), ('2.9.8', ''))
        self.assertEqual(executou.call_args.args[0], ['deno.exe', '--version'])

    def test_path_privado_herdado_pelo_yt_dlp_e_pela_biblioteca(self):
        with tempfile.TemporaryDirectory() as d:
            with patch.object(tools, 'PASTA_FERRAMENTAS', Path(d) / 'pasta com espacos'):
                env = tools.ambiente_ferramentas()
                self.assertEqual(env['PATH'].split(os.pathsep)[0], str(Path(d) / 'pasta com espacos'))
                self.assertNotEqual(env['PATH'], os.environ.get('PATH'))
                resposta = subprocess.CompletedProcess([], 0, stdout='', stderr='')
                with patch('app.sources.ytdlp.subprocess.run', return_value=resposta) as executou:
                    FonteYtDlp()._rodar(['yt-dlp', '-F'], timeout=1)
                self.assertEqual(executou.call_args.kwargs['env']['PATH'], env['PATH'])

    @unittest.skipUnless(os.name == 'posix' and shutil.which('yt-dlp'), 'Teste POSIX com yt-dlp instalado')
    def test_ytdlp_real_detecta_deno_local_simulado(self):
        # Um stub permite confirmar a descoberta de PATH sem executar JavaScript real.
        with tempfile.TemporaryDirectory() as d:
            pasta = Path(d) / 'ferramentas espacos'
            pasta.mkdir()
            deno = pasta / 'deno'
            deno.write_text('#!/bin/sh\necho "deno 2.9.8"\n')
            deno.chmod(0o755)
            with patch.object(tools, 'PASTA_FERRAMENTAS', pasta):
                # Use um arquivo
                # inexistente de info para inicializar o yt-dlp sem acesso à rede.
                processo = subprocess.run([shutil.which('yt-dlp'), '--ignore-config', '--verbose',
                                          '--load-info-json', str(pasta / 'nao-existe.json')],
                                          text=True, capture_output=True, env=tools.ambiente_ferramentas())
            self.assertIn('JS runtimes: deno-2.9.8', processo.stderr)
            with patch.object(tools, 'PASTA_FERRAMENTAS', pasta):
                biblioteca = subprocess.run([sys.executable, '-c',
                    'import yt_dlp; y=yt_dlp.YoutubeDL({"quiet":True}); print(y._js_runtimes["deno"].info.version)'],
                    text=True, capture_output=True, env=tools.ambiente_ferramentas())
            self.assertEqual(biblioteca.returncode, 0, biblioteca.stderr)
            self.assertEqual(biblioteca.stdout.strip(), '2.9.8')

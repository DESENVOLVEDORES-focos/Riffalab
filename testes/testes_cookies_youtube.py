"""Teste de sessão não deve vazar dados ou confundir resposta pública com login."""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.teste_cookies_youtube import testar


class TesteCookiesYouTube(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.original = Path(self.temp.name) / 'original.txt'
        self.original.write_bytes(b'credencial-super-secreta')
        self.tool = patch('app.teste_cookies_youtube.ytdlp',
                          return_value=SimpleNamespace(ok=True, caminho='yt-dlp'))
        self.tool.start(); self.addCleanup(self.tool.stop)

    def executar(self, payload=None, code=0, stderr=''):
        observado = {}
        def rodar(args, **kwargs):
            observado['args'] = args
            copia = Path(args[args.index('--cookies') + 1])
            observado['copia'] = copia
            self.assertNotEqual(copia, self.original)
            self.assertEqual(copia.read_bytes(), b'credencial-super-secreta')
            self.assertIn('--skip-download', args)
            self.assertIn('--flat-playlist', args)
            self.assertIn('--ignore-config', args)
            self.assertNotIn('--cookies-from-browser', args)
            copia.write_bytes(b'cookie modificado pelo yt-dlp')
            return SimpleNamespace(returncode=code, stdout=json.dumps(payload), stderr=stderr)
        with patch('app.teste_cookies_youtube.subprocess.run', side_effect=rodar):
            resultado = testar(self.original)
        self.assertEqual(self.original.read_bytes(), b'credencial-super-secreta')
        self.assertFalse(observado['copia'].exists())
        self.assertNotIn('credencial-super-secreta', str(resultado))
        return resultado

    def test_lista_pessoal_retornada(self):
        dados = {'_type': 'playlist', 'id': 'WL', 'entries': [{'id':'abcdefghijk', 'title':'nome privado'}]}
        resultado = self.executar(dados)
        self.assertEqual(resultado['estado'], 'confirmado')
        self.assertNotIn('nome privado', str(resultado))
        self.assertIn('não garante downloads', resultado['mensagem'])

    def test_publico_lista_vazia_saida_inesperada_nao_confirmam(self):
        for dados in ({'_type':'playlist', 'id':'WL', 'entries':[]},
                      {'_type':'playlist', 'id':'outra', 'entries':[{'id':'abcdefghijk'}]},
                      {'_type':'video', 'id':'WL', 'entries':[{'id':'abcdefghijk'}]},
                      {'_type':'playlist', 'id':'WL', 'entries':[{'id':'invalido'}]},
                      [], None):
            with self.subTest(dados=dados):
                self.assertEqual(self.executar(dados)['estado'], 'inconclusivo')

    def test_falhas_nao_exibem_saida_sensivel(self):
        for erro, esperado in [('ERROR HTTP 403 SECRET privado', 'recusado'),
                               ('Sign in to confirm SECRET privado', 'login'),
                               ('HTTP 429 SECRET privado', 'limite'),
                               ('outro SECRET privado', 'inconclusivo')]:
            resultado = self.executar(code=1, stderr=erro)
            self.assertEqual(resultado['estado'], esperado)
            self.assertNotIn('SECRET', str(resultado))

    def test_tempo_esgotado_remove_copia(self):
        copias = []
        def expirar(args, **kwargs):
            copias.append(Path(args[args.index('--cookies') + 1]))
            raise subprocess.TimeoutExpired(args, 90)
        with patch('app.teste_cookies_youtube.subprocess.run', side_effect=expirar):
            self.assertEqual(testar(self.original)['estado'], 'tempo')
        self.assertFalse(copias[0].exists())
        self.assertEqual(self.original.read_bytes(), b'credencial-super-secreta')

    def test_arquivo_alterado_durante_teste(self):
        def mudar(args, **kwargs):
            self.original.write_bytes(b'externamente alterado')
            return SimpleNamespace(returncode=0, stdout=json.dumps({'_type':'playlist', 'id':'WL',
                  'entries':[{'id':'abcdefghijk'}]}), stderr='')
        with patch('app.teste_cookies_youtube.subprocess.run', side_effect=mudar):
            self.assertEqual(testar(self.original)['estado'], 'inconclusivo')

    @unittest.skipIf(os.name == 'nt', 'executável fictício usa shebang Unix')
    def test_processo_externo_na_pratica(self):
        exe = Path(self.temp.name) / 'yt-dlp'
        exe.write_text("#!/usr/bin/env python3\n"
                       "import json,sys,pathlib\n"
                       "p=pathlib.Path(sys.argv[sys.argv.index('--cookies')+1])\n"
                       "p.write_text('mudado somente na copia')\n"
                       "print(json.dumps({'_type':'playlist','id':'WL',"
                       "'entries':[{'id':'abcdefghijk','title':'dado privado'}]}))\n")
        exe.chmod(0o700)
        with patch('app.teste_cookies_youtube.ytdlp', return_value=SimpleNamespace(ok=True, caminho=str(exe))):
            resultado = testar(self.original)
        self.assertEqual(resultado['estado'], 'confirmado')
        self.assertEqual(self.original.read_bytes(), b'credencial-super-secreta')
        self.assertNotIn('dado privado', str(resultado))

    def test_arquivo_inexistente_e_ferramenta_indisponivel(self):
        self.assertEqual(testar(Path(self.temp.name) / 'ausente')['estado'], 'arquivo')
        with patch('app.teste_cookies_youtube.ytdlp', return_value=SimpleNamespace(ok=False)):
            self.assertEqual(testar(self.original)['estado'], 'indisponivel')

if __name__ == '__main__':
    unittest.main()

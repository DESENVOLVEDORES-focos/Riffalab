"""Regressões da consulta isolada de formatos, sem usar YouTube externo."""
import functools
import http.server
import json
import importlib.util
import shutil
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from app.config import Config
from app.models import TrackResult
from app.sources.ytdlp import FonteYtDlp


def payload(formats):
    return json.dumps({'id': 'video', 'title': 'Música', 'formats': formats})


def audio(id='251', kbps=128):
    return {'format_id': id, 'acodec': 'opus', 'vcodec': 'none',
            'abr': kbps, 'ext': 'webm'}


class Listagem(unittest.TestCase):
    def setUp(self):
        self.fonte = FonteYtDlp()
        self.resultado = TrackResult('id', 'ytdlp', 'Música',
                                     pagina_url='https://www.youtube.com/watch?v=video')

    def test_tabela_e_json_sao_lidos_sem_escolher_formato(self):
        resposta = 'ID  EXT RESOLUTION | ACODEC ABR\n251 webm audio only | opus 128k\n' + payload([audio(), audio('140', 320)]) + '\n'
        with patch.object(self.fonte, '_args_base', return_value=['yt-dlp', '--ignore-config']), \
             patch.object(self.fonte, '_rodar', return_value=(0, resposta, '')) as rodar:
            self.fonte.detalhar(self.resultado)
        self.assertEqual(rodar.call_count, 4)
        argumentos = [c.args[0] for c in rodar.call_args_list]
        self.assertTrue(any('-F' in args and '--print-json' not in args for args in argumentos))
        self.assertTrue(any('-j' in args for args in argumentos))
        self.assertTrue(any('-F' in args and '--print-json' in args for args in argumentos))
        self.assertTrue(any('consulta_biblioteca_ytdlp.py' in ' '.join(args) for args in argumentos))
        self.assertTrue(all(self.resultado.pagina_url in args for args in argumentos))
        self.assertEqual({f.bitrate_kbps for f in self.resultado.formatos}, {128, 320})
        self.assertEqual(len(self.resultado.extra['metodos_consulta']), 4)

    def test_aviso_java_script_explicado_sem_expor_saida_sensivel(self):
        aviso = 'WARNING: No supported JavaScript runtime could be found. cookie segredo: XYZ'
        imagens = [{'format_id': 'sb', 'ext': 'mhtml', 'vcodec': 'none', 'acodec': 'none'}]
        with patch.object(self.fonte, '_args_base', return_value=['yt-dlp']), \
             patch.object(self.fonte, '_rodar', return_value=(0, payload(imagens), aviso)):
            self.fonte.detalhar(self.resultado)
        motivo = self.resultado.extra['erro_detalhe']
        self.assertIn('runtime JavaScript', motivo)
        self.assertNotIn('XYZ', motivo)
        self.assertFalse(self.resultado.formatos)

    def test_sem_audio_nao_inventa_320_e_tentativa_posterior_funciona(self):
        imagem = {'format_id': 'sb', 'acodec': 'none', 'vcodec': 'none', 'ext': 'mhtml'}
        fase = {'nova': False}
        def rodar(args, **kwargs):
            if not fase['nova']:
                return (0, payload([imagem]), 'WARNING: Only images are available for download')
            return (0, payload([audio()]), '')
        with patch.object(self.fonte, '_args_base', return_value=['yt-dlp']), \
             patch.object(self.fonte, '_rodar', side_effect=rodar) as chamada:
            self.fonte.detalhar(self.resultado)
            self.assertFalse(self.resultado.formatos)
            self.assertIn('somente imagens', self.resultado.extra['erro_detalhe'])
            fase['nova'] = True
            self.fonte.detalhar(self.resultado)
        self.assertEqual(chamada.call_count, 8)
        self.assertEqual(self.resultado.formatos[0].bitrate_kbps, 128)
        self.assertNotIn('erro_detalhe', self.resultado.extra)

    def test_config_antiga_ignorada_e_cookie_atual_explicito(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d); cookie = base / 'cookies.txt'; cookie.write_text('exemplo')
            config = Config(base / 'config.json')
            config.dados.update(caminho_cookies=str(cookie), usar_cookies=True)
            fonte = FonteYtDlp(config)
            with patch.object(fonte, '_exe', return_value=str(base / 'yt-dlp.exe')), \
                 patch('app.sources.ytdlp.ffmpeg') as ff:
                ff.return_value.ok = False
                args = fonte._args_base()
            self.assertIn('--ignore-config', args)
            self.assertNotIn('--no-warnings', args)
            self.assertEqual(args[args.index('--cookies') + 1], str(cookie))

    @unittest.skipUnless(shutil.which('yt-dlp'), 'yt-dlp necessário para o teste local')
    def test_ytdlp_real_lista_formato_de_http_local(self):
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header('Content-Type', 'audio/mpeg')
                self.send_header('Content-Length', '2048')
                self.end_headers()
                self.wfile.write(b'\x00' * 2048)
            def log_message(self, *args): pass
        servidor = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=servidor.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(servidor.server_close)
        self.addCleanup(thread.join)
        self.addCleanup(servidor.shutdown)
        r = TrackResult('local', 'ytdlp', 'Música', pagina_url=f'http://127.0.0.1:{servidor.server_port}/audio.mp3')
        with patch.object(self.fonte, '_args_base', return_value=[shutil.which('yt-dlp'), '--ignore-config', '--no-color']):
            self.fonte.detalhar(r)
        self.assertTrue(r.formatos, r.extra.get('erro_detalhe'))
        self.assertEqual(r.formatos[0].codec, 'mp3')
        self.assertEqual(len(r.extra['metodos_consulta']), 4)
        self.assertTrue(all(m['estado'] == 'ok' for m in r.extra['metodos_consulta'][:3]))
        if importlib.util.find_spec('yt_dlp'):
            self.assertEqual(r.extra['metodos_consulta'][3]['estado'], 'ok')

    @unittest.skipUnless(shutil.which('yt-dlp'), 'yt-dlp necessário para o teste local')
    def test_listagem_real_nao_exige_que_formato_seja_baixavel(self):
        with tempfile.TemporaryDirectory() as d:
            arquivo = Path(d) / 'informacao.json'
            arquivo.write_text(json.dumps({'id':'video', 'title':'Música', 'extractor':'youtube',
                               'extractor_key':'Youtube', 'formats':[{'format_id':'sb',
                               'url':'https://example.com/imagem', 'ext':'mhtml',
                               'acodec':'none', 'vcodec':'none', 'resolution':'48x27'}]}))
            cmd = [shutil.which('yt-dlp'), '--ignore-config', '--load-info-json', str(arquivo)]
            velho = subprocess.run(cmd + ['-J'], text=True, capture_output=True)
            novo = subprocess.run(cmd + ['-F', '--print-json'], text=True, capture_output=True)
            self.assertNotEqual(velho.returncode, 0)
            self.assertEqual(novo.returncode, 0, novo.stderr)
            self.assertTrue(any(line.startswith('{') for line in novo.stdout.splitlines()))

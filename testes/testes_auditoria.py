"""Auditoria de ferramentas, links e seleção de fontes sem acesso à rede."""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import search_service, tools
from app.config import Config
from app.models import AudioFormat, TrackResult
from app.pesquisa.preview import url_incorporada
from app.sources.ytdlp import FonteYtDlp


class Auditoria(unittest.TestCase):
    def tearDown(self):
        tools._cache.clear()

    def test_ferramenta_com_erro_nao_finge_estar_disponivel_e_usa_path(self):
        with tempfile.TemporaryDirectory(prefix='pasta com espaços ') as d:
            base = Path(d)
            quebrado, alternativa = base / 'yt-dlp.exe', base / 'yt-dlp'
            quebrado.write_text('inválido')
            alternativa.write_text('válido')
            def versao(caminho):
                return ('', 'falha ao executar') if caminho == str(quebrado) else ('2026.10.26', '')
            with patch.object(tools, '_candidatos', return_value=[quebrado]), \
                 patch.object(tools.shutil, 'which', return_value=str(alternativa)), \
                 patch.object(tools, '_versao', side_effect=versao):
                f = tools.localizar('yt-dlp', True)
                self.assertTrue(f.ok)
                self.assertEqual(f.caminho, str(alternativa))
                self.assertEqual(f.versao, '2026.10.26')

    def test_executavel_que_retorna_erro_nao_e_validado(self):
        resposta = subprocess.CompletedProcess([], 1, stdout='', stderr='arquivo inválido')
        with patch.object(tools.subprocess, 'run', return_value=resposta):
            versao, erro = tools._versao('yt-dlp.exe')
        self.assertFalse(versao)
        self.assertIn('código 1', erro)

    def test_nao_aceita_executavel_de_outro_programa_com_nome_ffmpeg(self):
        resposta = subprocess.CompletedProcess([], 0, stdout='Python 3.12.0', stderr='')
        with patch.object(tools.subprocess, 'run', return_value=resposta):
            versao, erro = tools._versao('ffmpeg.exe')
        self.assertFalse(versao)
        self.assertIn('não reconhecida', erro)

    def test_pode_rever_ferramenta_que_foi_adicionada(self):
        with tempfile.TemporaryDirectory() as d:
            arquivo = Path(d) / 'ffmpeg.exe'
            with patch.object(tools, '_candidatos', return_value=[arquivo]), \
                 patch.object(tools.shutil, 'which', return_value=None), \
                 patch.object(tools, '_versao', return_value=('7.0', '')):
                self.assertFalse(tools.localizar('ffmpeg', True).ok)
                arquivo.write_text('simulado')
                self.assertTrue(tools.localizar('ffmpeg', True).ok)

    def test_argumentos_yt_dlp_incluem_cookies_e_ffmpeg_com_espacos(self):
        with tempfile.TemporaryDirectory(prefix='caminho com espaços ') as d:
            base = Path(d)
            cookies = base / 'meus cookies.txt'
            cookies.write_text('# arquivo de teste')
            cfg = Config(base / 'config.json')
            cfg.dados.update(caminho_cookies=str(cookies), usar_cookies=True)
            fonte = FonteYtDlp(cfg)
            ff = tools.Ferramenta('ffmpeg', str(base / 'ffmpeg.exe'))
            with patch.object(fonte, '_exe', return_value=str(base / 'yt-dlp.exe')), \
                 patch('app.sources.ytdlp.ffmpeg', return_value=ff):
                args = fonte._args_base()
            self.assertEqual(args[0], str(base / 'yt-dlp.exe'))
            self.assertEqual(args[args.index('--cookies') + 1], str(cookies))
            self.assertEqual(args[args.index('--ffmpeg-location') + 1], ff.caminho)

    def test_link_youtube_pesquisado_diretamente_e_nao_como_texto(self):
        link = 'https://www.youtube.com/watch?v=abc123&list=xyz'
        payload = {'id': 'abc123', 'title': 'Artista - Canção', 'channel': 'Artista',
                   'webpage_url': link, 'formats': [{'format_id': '251', 'acodec': 'opus',
                                                    'abr': 128, 'vcodec': 'none', 'ext': 'webm'}]}
        fonte = FonteYtDlp()
        with patch.object(fonte, 'disponivel', return_value=(True, '')), \
             patch.object(fonte, '_args_base', return_value=['yt-dlp']), \
             patch.object(fonte, '_rodar', return_value=(0, json.dumps(payload), '')) as executar:
            resultado = fonte.buscar(link)[0]
        args = executar.call_args.args[0]
        self.assertEqual(args[-1], link)
        self.assertIn('--no-playlist', args)
        self.assertEqual(resultado.pagina_url, link)
        self.assertEqual(resultado.formatos[0].format_id, '251')
        self.assertIn('enablejsapi=1', url_incorporada(resultado))

    def test_link_de_outro_site_recebe_mensagem_clara(self):
        fonte = FonteYtDlp()
        with patch.object(fonte, 'disponivel', return_value=(True, '')):
            with self.assertRaisesRegex(ValueError, 'YouTube'):
                fonte.buscar('https://example.com/video')

    def test_fonte_escolhida_na_tela_e_respeitada_e_nao_ha_fallback_oculto(self):
        class Fonte:
            nome = 'Fonte de teste'
            def __init__(self, disponivel): self.ok = disponivel
            def disponivel(self): return self.ok, 'yt-dlp inválido'
            def buscar(self, consulta, limite):
                return [TrackResult('1', 'outra', 'Canção', 'Artista')]
        with tempfile.TemporaryDirectory() as d:
            cfg = Config(Path(d) / 'config.json')
            cfg.dados['verificar_automatico'] = 0
            with patch.object(search_service, 'todas_as_fontes',
                              return_value={'ytdlp': Fonte(False), 'outra': Fonte(True)}):
                falha = search_service.pesquisar('Canção', cfg, fontes_ids=['ytdlp'])
                self.assertFalse(falha['resultados'])
                self.assertIn('ytdlp', falha['erros'])
                sucesso = search_service.pesquisar('Canção', cfg, fontes_ids=['outra'])
                self.assertEqual(len(sucesso['resultados']), 1)

    def test_fallback_descarta_parcial_da_primeira_tentativa(self):
        with tempfile.TemporaryDirectory() as d:
            import io
            pasta = Path(d)
            class Processo:
                def __init__(self, args, **kwargs):
                    self.stdout = io.StringIO()
                    self.returncode = 1 if args[args.index('-f') + 1] == '251' else 0
                    arquivo = pasta / ('audio_orig.webm' if self.returncode else 'audio_orig.m4a')
                    arquivo.write_bytes(b'x' * (100 if self.returncode else 10))
                def wait(self): return self.returncode
            fonte = FonteYtDlp()
            r = TrackResult('id', 'ytdlp', 'Canção', pagina_url='https://www.youtube.com/watch?v=abc')
            with patch.object(fonte, '_args_base', return_value=['yt-dlp']), \
                 patch('app.sources.ytdlp.subprocess.Popen', Processo):
                arquivo = fonte.baixar(r, AudioFormat(format_id='251'), pasta / 'audio')
            self.assertEqual(arquivo.name, 'audio_orig.m4a')
            self.assertFalse((pasta / 'audio_orig.webm').exists())

    def test_conflito_de_mesmo_tamanho_nao_descarta_outra_musica(self):
        from app.organizer import resolver_conflito
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            original, novo = base / 'música.mp3', base / 'novo.mp3'
            original.write_bytes(b'12345678')
            novo.write_bytes(b'ABCDEFGH')
            caminho, situacao = resolver_conflito(original, 8, novo)
            self.assertEqual(situacao, 'renomeado')
            self.assertNotEqual(caminho, original)
            novo.write_bytes(b'12345678')
            caminho, situacao = resolver_conflito(original, 8, novo)
            self.assertEqual(situacao, 'duplicado')

    @unittest.skipUnless(shutil.which('yt-dlp') and shutil.which('ffmpeg'),
                         'yt-dlp e ffmpeg são necessários para o teste local real')
    def test_ytdlp_real_baixa_link_local_e_pipeline_converte(self):
        import functools
        import threading
        from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
        from app import pipeline
        from app.models import CoverResult, TrackMeta
        from mutagen.id3 import ID3

        class Handler(SimpleHTTPRequestHandler):
            def log_message(self, *args):
                pass

        with tempfile.TemporaryDirectory(prefix='Riff áudio com espaços ') as d:
            base = Path(d)
            audio = base / 'musica.wav'
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                            'sine=frequency=440:duration=1', str(audio)], check=True)
            servidor = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Handler, directory=d))
            thread = threading.Thread(target=servidor.serve_forever, daemon=True)
            thread.start()
            try:
                url = f'http://127.0.0.1:{servidor.server_port}/musica.wav'
                cfg = Config(base / 'config.json')
                cfg.dados['pasta_saida'] = str(base / 'saída')
                resultado = TrackResult('teste', 'ytdlp', 'Música', 'Artista', pagina_url=url)
                formato = AudioFormat(format_id='bestaudio')
                with patch.object(pipeline, 'PASTA_TEMP', base / 'temp'):
                    dados = pipeline.processar_resultado(resultado, cfg, formato,
                        fonte=FonteYtDlp(cfg), preparacao={'meta': TrackMeta(titulo='Música',
                        artista='Artista'), 'capa': CoverResult(), 'ident': None})
                self.assertTrue(dados['ok'], dados)
                self.assertEqual(str(ID3(dados['caminho'])['TIT2']), 'Música')
            finally:
                servidor.shutdown()
                servidor.server_close()
                thread.join()

if __name__ == '__main__':
    unittest.main()

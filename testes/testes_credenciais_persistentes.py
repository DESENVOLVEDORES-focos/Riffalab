"""Credenciais fictícias: cópias isoladas e configurações persistentes."""
import os
import subprocess
import shutil
import http.server
import threading
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication
from app import seguranca
from app.config import Config
from app.models import AudioFormat, TrackResult
from app.sources.ytdlp import FonteYtDlp
from app.ui.pages import settings_page


class CookiesPreservados(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.cookie = self.base / 'cookies.txt'
        self.cookie.write_text('# Netscape HTTP Cookie File\n.example.org\tTRUE\t/\tFALSE\t0\tname\tvalor-ficticio\n')
        self.conteudo = self.cookie.read_bytes()
        self.cfg = Config(self.base/'config.json')
        self.cfg.update(caminho_cookies=str(self.cookie), usar_cookies=True)
        self.fonte = FonteYtDlp(self.cfg)

    def test_cada_busca_utiliza_copia_e_original_fica_inalterado(self):
        vistos = []
        def executar(args, **kwargs):
            caminho = Path(args[args.index('--cookies')+1]); vistos.append(caminho)
            self.assertNotEqual(caminho, self.cookie)
            self.assertEqual(caminho.read_bytes(), self.conteudo)
            caminho.write_text('yt-dlp regravou a cópia')
            return SimpleNamespace(returncode=0,stdout='{}',stderr='')
        with patch('app.sources.ytdlp.subprocess.run', side_effect=executar):
            for _ in range(3): self.fonte._rodar(['yt-dlp','--cookies',str(self.cookie)])
        self.assertEqual(self.cookie.read_bytes(), self.conteudo)
        self.assertEqual(len(set(vistos)),3)
        self.assertTrue(all(not p.exists() for p in vistos))
        self.assertEqual(Config(self.base/'config.json').caminho_cookies, self.cookie)

    def test_falha_e_timeout_removem_copia_sem_tocar_original(self):
        caminhos = []
        def executar(args, **kwargs):
            p = Path(args[args.index('--cookies')+1]); caminhos.append(p); p.write_text('alterado')
            raise subprocess.TimeoutExpired(args, 3)
        with patch('app.sources.ytdlp.subprocess.run', side_effect=executar):
            with self.assertRaises(subprocess.TimeoutExpired):
                self.fonte._rodar(['yt-dlp','--cookies',str(self.cookie)])
        self.assertEqual(self.cookie.read_bytes(), self.conteudo)
        self.assertFalse(caminhos[0].exists())

    def test_download_usa_copia_e_preserva_formato(self):
        vistos = []
        class Processo:
            def __init__(self,args,**kwargs):
                caminho = Path(args[args.index('--cookies')+1]); vistos.append(caminho)
                self.assert_igual = caminho.read_bytes()
                caminho.write_text('reescrito durante download')
                self.args = args
                self.stdout = iter(['[download] 100%\n'])
                class Linhas:
                    def __iter__(self): return iter(['[download] 100%\n'])
                    def close(self): pass
                self.stdout = Linhas(); self.returncode = 0
                (self_base/'audio_orig.webm').write_bytes(b'audio')
            def wait(self): pass
        self_base = self.base
        with patch.object(self.fonte, '_args_base', return_value=['yt-dlp','--cookies',str(self.cookie)]), \
             patch('app.sources.ytdlp.subprocess.Popen', side_effect=Processo) as popen:
            arquivo = self.fonte.baixar(TrackResult('id','ytdlp','Música',pagina_url='https://example.com/v'),
                                        AudioFormat(format_id='251'), self.base/'destino')
        self.assertTrue(arquivo.is_file())
        self.assertEqual(popen.call_args.args[0][popen.call_args.args[0].index('-f')+1], '251')
        self.assertEqual(self.cookie.read_bytes(), self.conteudo)
        self.assertFalse(vistos[0].exists())

    @unittest.skipUnless(shutil.which('yt-dlp'), 'yt-dlp necessário')
    def test_ytdlp_real_consulta_http_local_sem_modificar_original(self):
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200); self.send_header('Content-Type','audio/mpeg')
                self.send_header('Content-Length','2048'); self.end_headers(); self.wfile.write(b'\0'*2048)
            def log_message(self, *args): pass
        servidor = http.server.ThreadingHTTPServer(('127.0.0.1',0), Handler)
        thread = threading.Thread(target=servidor.serve_forever, daemon=True); thread.start()
        try:
            url = f'http://127.0.0.1:{servidor.server_port}/audio.mp3'
            code, _, erro = self.fonte._rodar([shutil.which('yt-dlp'), '--ignore-config',
                                              '--cookies', str(self.cookie), '-j', '--', url])
            self.assertEqual(code, 0, erro)
            self.assertEqual(self.cookie.read_bytes(), self.conteudo)
        finally:
            servidor.shutdown(); servidor.server_close(); thread.join()

    def test_caminho_explicito_ausente_nao_desativa_silenciosamente(self):
        self.cookie.unlink()
        with patch.object(self.fonte, '_exe', return_value='yt-dlp'):
            with self.assertRaisesRegex(RuntimeError, 'cookies selecionado não foi encontrado'):
                self.fonte._args_base()
        self.assertTrue(self.cfg.get('usar_cookies'))
        self.assertEqual(self.cfg.caminho_cookies,self.cookie)


class ChavePersistente(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.cfg = Config(self.base/'config.json')
        self.patches = [patch.object(seguranca,'RAIZ',self.base),
                        patch.object(seguranca,'PASTA',self.base/'credenciais'),
                        patch.object(seguranca,'ARQ',self.base/'credenciais/groq.dat'),
                        patch.object(seguranca,'ARQ_API',self.base/'api.txt'),
                        patch.dict(os.environ, {'GROQ_API_KEY':''})]
        for p in self.patches: p.start(); self.addCleanup(p.stop)
        with patch.object(settings_page.SettingsPage, '_verificar_ferramentas'):
            self.tela = settings_page.SettingsPage(self.cfg)

    def tearDown(self):
        self.tela.close(); self.tela.deleteLater(); self.app.processEvents()

    def test_salvar_chave_liga_ia_e_persiste_sem_reinserir(self):
        self.tela.campo_chave.setText('gsk_chave_ficticia_123456')
        self.tela._salvar_chave()
        self.assertEqual(self.tela.campo_chave.text(), '')
        self.assertTrue(self.tela.chk_ia.isChecked())
        self.assertTrue(Config(self.base/'config.json').get('ia_ativa'))
        self.assertEqual(seguranca.ler(), 'gsk_chave_ficticia_123456')
        self.assertEqual(self.tela.chip_ia.text(),'chave carregada')
        self.assertIn('não confirma acesso',self.tela.lbl_ia.text())
        self.tela.chk_ia.setChecked(False)
        self.assertFalse(Config(self.base/'config.json').get('ia_ativa'))
        self.assertEqual(seguranca.ler(), 'gsk_chave_ficticia_123456')

    def test_erro_na_gravacao_nao_apaga_campo_nem_liga_ia(self):
        self.tela.campo_chave.setText('ficticia')
        with patch.object(seguranca, 'guardar', return_value=(False, 'falha')):
            self.tela._salvar_chave()
        self.assertEqual(self.tela.campo_chave.text(), 'ficticia')
        self.assertFalse(self.cfg.get('ia_ativa'))

    def test_status_nao_diz_chave_ok_quando_cofre_falha(self):
        seguranca.PASTA.mkdir(); seguranca.ARQ.write_bytes(b'DPAPI1ilegivel')
        with patch.object(seguranca,'_windows',return_value=True), \
             patch.object(seguranca,'_dpapi',side_effect=OSError('erro')):
            self.tela._atualizar_ia()
        self.assertEqual(self.tela.chip_ia.text(),'chave inacessível')
        self.assertIn('Não foi possível ler',self.tela.lbl_ia.text())

    def test_dpapi_mantem_buffer_vivo_e_libera_ponteiro_inteiro(self):
        import ctypes
        from ctypes import wintypes
        class Blob(ctypes.Structure):
            _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_char))]
        class Funcao:
            def __init__(self, f): self.f = f
            def __call__(self,*args): return self.f(*args)
        buffer_saida = ctypes.create_string_buffer(b'resultado')
        liberados = []
        def crypt(entrada, _descricao, _entropia, _reservado, _prompt, _flags, saida):
            dado = ctypes.cast(entrada, ctypes.POINTER(Blob)).contents
            self.assertEqual(ctypes.string_at(dado.pbData, dado.cbData), b'entrada')
            saida = ctypes.cast(saida, ctypes.POINTER(Blob)).contents
            saida.cbData = 9
            saida.pbData = ctypes.cast(buffer_saida, ctypes.POINTER(ctypes.c_char))
            return 1
        proteger = Funcao(crypt); liberar = Funcao(lambda p: liberados.append(p.value))
        windll = SimpleNamespace(crypt32=SimpleNamespace(CryptProtectData=proteger),
                                 kernel32=SimpleNamespace(LocalFree=liberar))
        with patch.object(ctypes, 'windll', windll, create=True):
            self.assertEqual(seguranca._dpapi(b'entrada', True), b'resultado')
        self.assertEqual(liberados, [ctypes.addressof(buffer_saida)])
        self.assertIs(liberar.argtypes[0], ctypes.c_void_p)

    def test_prioridade_de_ambiente_e_explicada_sem_expor_chave(self):
        mensagens=[]; self.tela.mensagem.connect(mensagens.append)
        with patch.dict(os.environ, {'GROQ_API_KEY':'gsk_ambiente_ficticia'}):
            self.tela.campo_chave.setText('gsk_ficticia_nova')
            self.tela._salvar_chave()
        self.assertIn('tem prioridade', mensagens[-1])
        self.assertNotIn('gsk_ambiente_ficticia', mensagens[-1])

if __name__ == '__main__': unittest.main()

"""Testes Qt offscreen dos botões principais; sem rede nem download real."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
try:
    from PySide6.QtWidgets import QApplication, QDialog, QMessageBox
    # Criar antes dos demais testes executarem QObjects, com referência viva.
    _app_testes = QApplication.instance() or QApplication([])
except ImportError:
    QApplication = None
    _app_testes = None


@unittest.skipIf(QApplication is None, 'Bibliotecas Qt do sistema não disponíveis')
class Interface(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = _app_testes

    def setUp(self):
        from app.config import Config
        from app.db import Banco
        from app.ui.main_window import MainWindow
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.cfg = Config(self.base / 'config.json')
        self.banco = Banco(self.base / 'banco.db')
        # Desliga apenas a consulta externa durante o teste de interface.
        with patch('app.ui.pages.settings_page.SettingsPage._verificar_ferramentas'), \
             patch('app.ui.main_window.MainWindow._atualizar_rodape_completo'):
            self.janela = MainWindow(self.cfg, self.banco)
        self.janela.show()
        self.app.processEvents()

    def tearDown(self):
        from app.workers import EXECUTOR_GLOBAL, EXECUTOR_FORMATOS
        EXECUTOR_GLOBAL.aguardar(30000)
        EXECUTOR_FORMATOS.aguardar(30000)
        self.app.processEvents()
        from PySide6.QtCore import QCoreApplication, QEvent
        self.janela.close()
        self.janela.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.app.processEvents()
        self.temp.cleanup()

    def test_telas_separadas_e_rolagem_vertical_de_todos_resultados(self):
        from app.models import AudioFormat, TrackResult
        from app.ui.pages import search_page
        self.janela.resize(1080, 680)
        normal = self.janela.pagina_busca
        varias = self.janela.pagina_varias
        self.assertIsNot(normal, varias)
        self.assertIsNot(normal.area, varias.area)
        normal.campo.setText('Busca normal guardada')
        self.janela.botoes['varias'].click()
        self.assertIs(self.janela.pilha.currentWidget(), varias)
        varias.campo_varias.setText('Primeira busca')
        varias.campos_extras[0][1].setText('Segunda busca')
        for i in range(8):
            varias._adicionar_campo()
        from PySide6.QtTest import QTest
        QTest.qWait(100)  # layout e barra são atualizados de forma assíncrona pelo Qt
        self.assertGreater(varias.area.verticalScrollBar().maximum(), 0)
        self.assertGreaterEqual(varias.area.viewport().height(), 450)
        respostas = []
        for nome in ('Primeira busca', 'Segunda busca'):
            resultados = [TrackResult(nome + str(i), 'ytdlp', f'Música {i}', 'Artista',
                           formatos=[AudioFormat(codec='opus', bitrate_kbps=128, format_id='251')],
                           extra={'metodos_consulta':[{'nome':'JSON', 'estado':'ok', 'quantidade':1}]})
                          for i in range(5)]
            respostas.append({'consulta':nome, 'resultados':resultados, 'filtrados':[],
                              'fontes':[], 'segundos':0, 'erros':{}})
        def executar(fn, *args, **kwargs):
            if fn is search_page.pesquisar_varias:
                kwargs['ao_resultado'](respostas)
        with patch.object(varias._fontes_obj['ytdlp'], 'disponivel', return_value=(True, '')), \
             patch.object(search_page.EXECUTOR_GLOBAL, 'rodar', side_effect=executar):
            varias.btn_buscar_varias.click()
        QTest.qWait(100)
        self.assertTrue(varias.paineis_busca.isHidden())
        self.assertEqual(len(varias.cards), 10)
        self.assertGreater(varias.area.verticalScrollBar().maximum(), 0)
        varias.area.verticalScrollBar().setValue(varias.area.verticalScrollBar().maximum())
        self.app.processEvents()
        ultimo = varias.cards[-1].mapTo(varias.area.viewport(), varias.cards[-1].rect().center())
        self.assertGreaterEqual(ultimo.y(), 0)
        self.assertLess(ultimo.y(), varias.area.viewport().height())
        self.assertEqual(len(normal.cards), 0)
        self.janela.botoes['buscar'].click()
        self.assertIs(self.janela.pilha.currentWidget(), normal)
        self.assertEqual(normal.campo.text(), 'Busca normal guardada')
        self.janela.botoes['varias'].click()
        self.assertEqual(len(varias.cards), 10)
        self.assertEqual(varias.campo_varias.text(), 'Primeira busca')
        self.assertEqual(varias.campos_extras[0][1].text(), 'Segunda busca')

    def test_marcacoes_e_formatos_sincronizados_entre_as_telas(self):
        from app.models import AudioFormat, TrackResult
        from app.ui.pages import search_page
        normal, varias = self.janela.pagina_busca, self.janela.pagina_varias
        fmts = [AudioFormat(codec='opus', bitrate_kbps=150, format_id='251'),
                AudioFormat(codec='aac', bitrate_kbps=120, format_id='140')]
        def dados():
            return {'resultados':[TrackResult('x','ytdlp','Música','Artista',formatos=fmts)],
                    'filtrados':[], 'consulta':'Música', 'fontes':[], 'segundos':0, 'erros':{}}
        with patch.object(search_page.EXECUTOR_GLOBAL, 'rodar'):
            normal._mostrar(dados())
            varias._mostrar(dados())
        c1, c2 = normal.cards[0], varias.cards[0]
        c1.check.setChecked(True)
        self.assertTrue(c2.check.isChecked())
        indice = next(i for i in range(c2.combo.count()) if c2.combo.itemData(i).format_id == '140')
        c2.combo.setCurrentIndex(indice)
        self.assertEqual(c1.combo.currentData().format_id, '140')
        self.assertIn('(1)', normal.btn_lote.text())
        self.assertIn('(1)', varias.btn_lote.text())
        self.assertEqual(self.banco.ler_estado('marcacoes')[0]['formato']['format_id'], '140')
        with patch.object(varias, '_transferir', return_value=True):
            varias._processar_lote()
        self.assertFalse(c1.check.isChecked())
        self.assertFalse(c2.check.isChecked())
        self.assertEqual(normal._marcados, {})

    def test_pesquisas_multiplas_formatos_yt_dlp_real_http_local(self):
        # Pesquisa simulada, mas extração de formatos usa processos reais yt-dlp
        # contra áudio gerado localmente, sem consultar o YouTube.
        import functools, shutil, threading, time, wave
        from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
        from app import search_service
        from app.models import TrackResult
        if not shutil.which('yt-dlp'):
            self.skipTest('yt-dlp não instalado para teste local')
        for nome in ('primeira.wav', 'segunda.wav'):
            with wave.open(str(self.base / nome), 'wb') as audio:
                audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(8000)
                audio.writeframes(b'\0\0' * 8000)
        class Handler(SimpleHTTPRequestHandler):
            def log_message(self, *args): pass
        servidor = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Handler, directory=str(self.base)))
        thread = threading.Thread(target=servidor.serve_forever, daemon=True); thread.start()
        busca = self.janela.pagina_varias
        self.janela.ir_para('varias')
        busca.campo_varias.setText('primeira'); busca.campos_extras[0][1].setText('segunda')
        def pesquisar_fake(termo, *args, **kwargs):
            url = f'http://127.0.0.1:{servidor.server_port}/{termo}.wav'
            r = TrackResult(termo, 'ytdlp', termo, 'Artista', pagina_url=url)
            return {'consulta':termo, 'resultados':[r], 'filtrados':[], 'fontes':[], 'segundos':0, 'erros':{}}
        try:
            with patch.object(busca._fontes_obj['ytdlp'], 'disponivel', return_value=(True, '')), \
                 patch.object(search_service, 'pesquisar', side_effect=pesquisar_fake), \
                 patch.object(busca, '_conferir_baixados'):
                busca.pesquisar()
                prazo = time.monotonic() + 25
                while (busca._buscando or len(busca.cards) < 2 or busca._verif_ativas or busca._fila_verif) and time.monotonic() < prazo:
                    self.app.processEvents(); time.sleep(.02)
                self.assertFalse(busca._buscando)
                self.assertEqual(len(busca.cards), 2)
                self.assertFalse(busca._verif_ativas)
                for card in busca.cards:
                    self.assertTrue(card.resultado.formatos, card.resultado.extra)
                    self.assertTrue(card.combo.currentData().format_id)
                    self.assertEqual(len(card.resultado.extra['metodos_consulta']), 4)
                    self.assertTrue(any(m['estado'] == 'ok' for m in card.resultado.extra['metodos_consulta']))
        finally:
            servidor.shutdown(); servidor.server_close(); thread.join(3)

    def test_consultas_de_formatos_nao_ocupam_pool_de_pesquisa(self):
        import threading, time
        from app.workers import EXECUTOR_GLOBAL, EXECUTOR_FORMATOS
        liberar = threading.Event(); comecaram = threading.Event(); resposta = []
        contador = []
        def tarefa_lenta():
            contador.append(1)
            if len(contador) == 3: comecaram.set()
            liberar.wait(5)
        try:
            for _ in range(3): EXECUTOR_FORMATOS.rodar(tarefa_lenta)
            self.assertTrue(comecaram.wait(3))
            EXECUTOR_GLOBAL.rodar(lambda: 'pesquisa terminou', ao_resultado=resposta.append)
            prazo = time.monotonic() + 2
            while not resposta and time.monotonic() < prazo:
                self.app.processEvents(); time.sleep(.01)
            self.assertEqual(resposta, ['pesquisa terminou'])
        finally:
            liberar.set()

    def test_previa_nao_redesenha_os_cartoes_e_aplica_resultado_mais_recente_ao_fechar(self):
        import time
        from app.models import AudioFormat, TrackResult
        from app.ui.widgets import preview_widget
        from app.ui.pages import search_page
        busca = self.janela.pagina_varias
        self.janela.ir_para('varias')
        r = TrackResult('id', 'ytdlp', 'Música', 'Artista', pagina_url='https://youtube.com/watch?v=123')
        dados = {'resultados':[r], 'filtrados':[], 'consulta':'Música', 'fontes':[], 'segundos':0, 'erros':{}}
        with patch.object(search_page.EXECUTOR_FORMATOS, 'rodar'), \
             patch.object(search_page.EXECUTOR_GLOBAL, 'rodar'), \
             patch.object(preview_widget, 'webengine_disponivel', return_value=False):
            busca._mostrar(dados)
            card = busca.cards[0]
            card.check.setChecked(True)
            busca.previa.mostrar(r)
            parcial = TrackResult('id', 'ytdlp', 'Música', 'Artista',
                      formatos=[AudioFormat(codec='opus', format_id='251')])
            final = TrackResult('id', 'ytdlp', 'Música', 'Artista',
                      formatos=[AudioFormat(codec='aac', format_id='140')])
            busca._aplicar_detalhe(card, parcial)
            busca._aplicar_detalhe(card, final)
            self.assertFalse(card.resultado.formatos)
            self.assertIs(busca._detalhes_adiados[card], final)
            self.assertTrue(card.check.isChecked())
            busca.previa.fechar()
            prazo = time.monotonic() + 2
            while busca._detalhes_adiados and time.monotonic() < prazo:
                self.app.processEvents(); time.sleep(.01)
            self.assertFalse(busca._detalhes_adiados)
            self.assertEqual(card.resultado.formatos[0].format_id, '140')
            self.assertTrue(card.check.isChecked())
            self.assertEqual(len(busca._marcados), 1)

    def test_formato_em_selecao_nao_e_atualizado_ate_fechar_lista(self):
        import time
        from app.models import AudioFormat, TrackResult
        from app.ui.pages import search_page
        busca = self.janela.pagina_busca
        antigo = TrackResult('id','ytdlp','Música',formatos=[AudioFormat(codec='opus',format_id='251')],
                            extra={'metodos_consulta':[{'estado':'ok'}]})
        novo = TrackResult('id','ytdlp','Música',formatos=[AudioFormat(codec='aac',format_id='140')])
        with patch.object(search_page.EXECUTOR_GLOBAL, 'rodar'), patch.object(search_page.EXECUTOR_FORMATOS, 'rodar'):
            busca._mostrar({'resultados':[antigo], 'filtrados':[], 'consulta':'x', 'fontes':[], 'segundos':0, 'erros':{}})
            card = busca.cards[0]
            with patch.object(card.combo.view(), 'isVisible', return_value=True):
                busca._aplicar_detalhe(card, novo)
                busca._drenar_detalhes_adiados()
                self.assertEqual(card.resultado.formatos[0].format_id, '251')
                self.assertIn(card, busca._detalhes_adiados)
            prazo = time.monotonic() + 2
            while busca._detalhes_adiados and time.monotonic() < prazo:
                self.app.processEvents(); time.sleep(.01)
            self.assertEqual(card.resultado.formatos[0].format_id, '140')

    def test_fontes_ativas_de_capa_sao_visiveis_e_busca_manual_pede_single(self):
        from app.models import CoverResult
        from app.ui.dialogos import DialogoCapas
        from PySide6.QtGui import QDesktopServices
        musica = {'titulo':'Paradise City', 'artista':'Guns N Roses', 'album':'Appetite',
                  'fontes_capa':['coverartarchive', 'itunes', 'deezer']}
        dialogo = DialogoCapas(self.janela, CoverResult(), musica)
        self.assertIn('Deezer', dialogo.lbl_fontes.text())
        self.assertIn('Apple', dialogo.lbl_fontes.text())
        self.assertIn('Cover Art Archive', dialogo.lbl_fontes.text())
        with patch.object(QDesktopServices, 'openUrl') as abrir:
            dialogo._pesquisar_google()
        url = abrir.call_args.args[0].toString().lower()
        self.assertIn('single', url)
        self.assertNotIn('appetite', url)
        dialogo.deleteLater()

    def test_fila_descarta_callbacks_de_card_antigo_e_continua_pesquisa_nova(self):
        from app.models import AudioFormat, TrackResult
        from app.ui.pages import search_page
        busca = self.janela.pagina_busca
        tarefas = []
        def agendar(fn, resultado, **kwargs):
            tarefas.append((fn, resultado, kwargs))
        def dados(nome):
            return {'resultados':[TrackResult(nome,'ytdlp',nome,'Artista')],
                    'filtrados':[], 'consulta':nome, 'fontes':[], 'segundos':0, 'erros':{}}
        class Fonte:
            def detalhar_primeiro(self, r): return r
            def detalhar(self, r, **kw): return r
        with patch.object(busca, '_fonte_de', return_value=Fonte()), \
             patch.object(search_page.EXECUTOR_FORMATOS, 'rodar', side_effect=agendar), \
             patch.object(busca, '_conferir_baixados'):
            busca._mostrar(dados('antiga'))
            velho = busca.cards[0]
            antiga = tarefas.pop(0)
            busca._mostrar(dados('nova'))
            novo = busca.cards[0]
            nova = tarefas.pop(0)
            antiga[1].formatos = [AudioFormat(codec='opus', format_id='251')]
            antiga[2]['ao_resultado'](antiga[1])
            self.assertNotIn(velho, busca.cards)
            self.assertEqual(novo.resultado.uid, 'nova')
            self.assertFalse(novo.resultado.formatos)
            nova[2]['ao_erro']('falhou')
            self.assertEqual(len(tarefas), 1)  # falha inicial ainda tenta os quatro métodos
            completa = tarefas.pop(0)
            completa[2]['ao_erro']('falhou de novo')
            self.assertEqual(busca._verif_ativas, 0)
            self.assertFalse(busca._fila_complementar)
            self.assertIn('Falha', novo.resultado.extra['erro_detalhe'])

    def test_filtrado_oculto_nao_recebe_callback_e_pode_ser_reexibido(self):
        from app.models import TrackResult
        from app.ui.pages import search_page
        busca = self.janela.pagina_busca
        tarefas = []
        class Fonte:
            def detalhar_primeiro(self, r): return r
            def detalhar(self, r, **kw): return r
        dados = {'resultados':[TrackResult('normal','ytdlp','Normal','Artista',
                     extra={'erro_detalhe':'já falhou'})],
                 'filtrados':[TrackResult('filtrado','ytdlp','Ao vivo','Artista')],
                 'consulta':'x','fontes':[],'segundos':0,'erros':{}}
        with patch.object(busca, '_fonte_de', return_value=Fonte()), \
             patch.object(search_page.EXECUTOR_FORMATOS, 'rodar', side_effect=lambda fn, r, **kw: tarefas.append((r,kw))), \
             patch.object(busca, '_conferir_baixados'):
            busca._mostrar(dados)
            busca._alternar_filtrados()
            velho = busca._cards_filtrados[0]
            busca._alternar_filtrados()
            busca._alternar_filtrados()
            novo = busca._cards_filtrados[0]
            self.assertIsNot(velho, novo)
            tarefas[0][1]['ao_resultado'](tarefas[0][0])
            self.assertNotIn(velho, busca.cards)
            self.assertNotIn(velho, [c for c, _ in busca._fila_complementar])
            self.assertIn(novo, busca.cards)

    def test_vinte_resultados_recebem_primeira_consulta_antes_de_comparacoes_lentas(self):
        import threading, time
        from app.models import AudioFormat, TrackResult
        busca = self.janela.pagina_varias
        self.janela.ir_para('varias')
        liberar = threading.Event()
        primeiras, completas = [], []
        class Fonte:
            def detalhar_primeiro(self, r):
                primeiras.append(r.uid)
                r.formatos = [AudioFormat(codec='opus', format_id='251')]
                r.extra['consulta_em_andamento'] = True
                r.extra['metodos_consulta'] = [{'nome':'JSON','estado':'ok','quantidade':1},
                                               {'nome':'Outro','estado':'aguardando','quantidade':0}]
                return r
            def detalhar(self, r, ao_parcial=None):
                completas.append((r.uid, len(primeiras)))
                liberar.wait(5)
                r.extra.pop('consulta_em_andamento', None)
                r.extra['metodos_consulta'] = [{'nome':'JSON','estado':'ok','quantidade':1}]
                return r
        resultados = [TrackResult(str(i), 'ytdlp', f'Música {i}', 'Artista') for i in range(20)]
        try:
            with patch.object(busca, '_fonte_de', return_value=Fonte()), patch.object(busca, '_conferir_baixados'):
                busca._mostrar({'resultados':resultados, 'filtrados':[], 'consulta':'teste',
                               'fontes':[], 'segundos':0, 'erros':{}})
                prazo = time.monotonic() + 4
                while (len(primeiras) < 20 or not busca.cards[-1].resultado.formatos) and time.monotonic() < prazo:
                    self.app.processEvents(); time.sleep(.01)
                self.assertEqual(len(primeiras), 20)
                self.assertTrue(busca.cards[-1].resultado.formatos)
                self.assertTrue(all(n >= 18 for _, n in completas))
                self.assertTrue(busca._verif_ativas or busca._fila_complementar)
                liberar.set()
                prazo = time.monotonic() + 5
                while (busca._verif_ativas or busca._fila_complementar or busca._fila_verif) and time.monotonic() < prazo:
                    self.app.processEvents(); time.sleep(.01)
                self.assertEqual(len(completas), 20)
                self.assertFalse(busca._fila_complementar)
        finally:
            liberar.set()

    def test_visualizador_mp3_mostra_capa_embutida_e_nao_altera_arquivos(self):
        import hashlib, time
        from PySide6.QtGui import QImage, QColor
        from mutagen.id3 import ID3, APIC, TIT2, TPE1
        pasta = self.base / 'musicas'; (pasta / 'Artista').mkdir(parents=True)
        imagem = self.base / 'imagem.png'
        foto = QImage(50, 50, QImage.Format_RGB32); foto.fill(QColor('red'))
        self.assertTrue(foto.save(str(imagem)))
        com = pasta / 'Artista' / 'com.mp3'; com.write_bytes(b'')
        tags = ID3(); tags.add(TIT2(encoding=3, text='Com capa')); tags.add(TPE1(encoding=3, text='Artista'))
        tags.add(APIC(encoding=3, mime='image/png', type=3, desc='frente', data=imagem.read_bytes())); tags.save(str(com))
        sem = pasta / 'Artista' / 'sem.mp3'; sem.write_bytes(b'')
        tags = ID3(); tags.add(TIT2(encoding=3, text='Sem capa')); tags.save(str(sem))
        antes = {p: hashlib.sha256(p.read_bytes()).digest() for p in (com, sem)}
        self.cfg.dados['pasta_saida'] = str(pasta)
        self.janela.ir_para('visualizar')
        self.assertIs(self.janela.pilha.currentWidget(), self.janela.pagina_visualizar)
        visor = self.janela.pagina_visualizar
        prazo = time.monotonic() + 5
        while (visor.tabela.rowCount() != 2 or not visor._imagens) and time.monotonic() < prazo:
            self.app.processEvents(); time.sleep(.01)
        self.assertEqual(visor.tabela.rowCount(), 2)
        self.assertTrue(visor._imagens)
        self.assertFalse(visor.lbl_capa.pixmap().isNull())
        self.assertIn('Imagem embutida', visor.lbl_estado.text())
        visor.filtro.setText('Sem capa')
        prazo = time.monotonic() + 5
        while visor.lbl_estado.text() != 'Sem imagem ID3. Nenhuma imagem APIC foi mostrada.' and time.monotonic() < prazo:
            self.app.processEvents(); time.sleep(.01)
        self.assertEqual(visor.tabela.rowCount(), 1)
        self.assertIn('Sem imagem ID3', visor.lbl_estado.text())
        self.assertEqual(antes, {p: hashlib.sha256(p.read_bytes()).digest() for p in (com, sem)})

    def test_visualizador_ignora_resultados_antigos_e_apos_fechar(self):
        visor = self.janela.pagina_visualizar
        visor._geracao = 8
        visor.resumo.setText('atual')
        visor._lista_pronta(7, {'itens':[], 'erros':[], 'truncado':False})
        self.assertEqual(visor.resumo.text(), 'atual')
        visor._encerrando = True
        visor._lista_pronta(8, {'itens':[], 'erros':[], 'truncado':False})
        self.assertEqual(visor.resumo.text(), 'atual')

    def test_formato_parcial_disponivel_e_escolha_preservada_ate_fim(self):
        import threading, time
        from copy import deepcopy
        from app.models import AudioFormat, TrackResult
        busca = self.janela.pagina_busca
        liberar = threading.Event()
        class Fonte:
            def detalhar(self, resultado, ao_parcial=None):
                resultado.formatos = [AudioFormat(codec='opus', bitrate_kbps=150, format_id='251'),
                                      AudioFormat(codec='aac', bitrate_kbps=128, format_id='140')]
                resultado.extra['metodos_consulta'] = [
                    {'nome':'JSON', 'estado':'ok', 'quantidade':2},
                    {'nome':'Lista', 'estado':'consultando'}]
                resultado.extra['consulta_em_andamento'] = True
                ao_parcial(deepcopy(resultado))
                liberar.wait(5)
                resultado.extra['metodos_consulta'][1]['estado'] = 'falhou'
                resultado.extra.pop('consulta_em_andamento')
                return resultado
        r = TrackResult('id', 'ytdlp', 'Música', 'Artista')
        try:
            with patch.object(busca, '_fonte_de', return_value=Fonte()), \
                 patch.object(busca, '_conferir_baixados'):
                busca._mostrar({'resultados':[r], 'filtrados':[], 'consulta':'Música',
                               'fontes':[], 'segundos':0, 'erros':{}})
                card = busca.cards[0]
                limite = time.monotonic() + 4
                while not card.resultado.formatos and time.monotonic() < limite:
                    self.app.processEvents(); time.sleep(.01)
                self.assertEqual(len(card.resultado.formatos), 2)
                self.assertTrue(card.btn_formatos.isEnabled())
                self.assertIn('1/2 métodos', card.lbl_metodos_qualidade.text())
                self.assertEqual(busca._verif_ativas, 1)
                i = next(i for i in range(card.combo.count()) if card.combo.itemData(i).format_id == '140')
                card.combo.setCurrentIndex(i)
                card.check.setChecked(True)
                liberar.set()
                limite = time.monotonic() + 4
                while busca._verif_ativas and time.monotonic() < limite:
                    self.app.processEvents(); time.sleep(.01)
                self.assertEqual(busca._verif_ativas, 0)
                self.assertEqual(card.combo.currentData().format_id, '140')
                self.assertEqual(next(iter(busca._marcados.values()))['formato'].format_id, '140')
                self.assertIn('2/2 métodos', card.lbl_metodos_qualidade.text())
                self.assertIn('falhou', card.lbl_metodos_qualidade.toolTip())
        finally:
            liberar.set()

    def test_comparador_real_de_codigo_publica_no_cartao_antes_do_fim(self):
        import json, threading, time
        from app.models import TrackResult
        from app.sources.ytdlp import FonteYtDlp
        busca = self.janela.pagina_busca
        liberar = threading.Event()
        fonte = FonteYtDlp(self.cfg)
        formatos = [{'format_id':'251', 'acodec':'opus', 'vcodec':'none', 'abr':160, 'ext':'webm'},
                    {'format_id':'140', 'acodec':'mp4a.40.2', 'vcodec':'none', 'abr':128, 'ext':'m4a'}]
        def rodar(args, timeout):
            if '-j' in args:
                return 0, json.dumps({'formats':formatos}), ''
            liberar.wait(5)
            return 1, '', 'ERROR: HTTP Error 403'
        r = TrackResult('id', 'ytdlp', 'Música', 'Artista', pagina_url='https://youtube.com/watch?v=123')
        try:
            with patch.object(busca, '_fonte_de', return_value=fonte), \
                 patch.object(busca, '_conferir_baixados'), \
                 patch.object(fonte, '_args_base', return_value=['yt-dlp']), \
                 patch.object(fonte, '_rodar', side_effect=rodar):
                busca._mostrar({'resultados':[r], 'filtrados':[], 'consulta':'Música',
                               'fontes':[], 'segundos':0, 'erros':{}})
                card = busca.cards[0]
                limite = time.monotonic() + 4
                while not card.resultado.formatos and time.monotonic() < limite:
                    self.app.processEvents(); time.sleep(.01)
                self.assertEqual({card.combo.itemData(i).format_id for i in range(card.combo.count())}, {'251','140'})
                self.assertTrue(card.btn_formatos.isEnabled())
                self.assertEqual(busca._verif_ativas, 1)
                liberar.set()
                limite = time.monotonic() + 4
                while busca._verif_ativas and time.monotonic() < limite:
                    self.app.processEvents(); time.sleep(.01)
                self.assertEqual(busca._verif_ativas, 0)
                self.assertEqual({f.format_id for f in card.resultado.formatos}, {'251','140'})
                self.assertIn('403', card.lbl_metodos_qualidade.toolTip())
        finally:
            liberar.set()

    def test_erro_apos_parcial_preserva_escolha_e_permite_nova_consulta(self):
        from app.models import AudioFormat, TrackResult
        from app.ui.pages import search_page
        busca = self.janela.pagina_busca
        formatos = [AudioFormat(codec='opus', bitrate_kbps=160, format_id='251'),
                    AudioFormat(codec='aac', bitrate_kbps=128, format_id='140')]
        r = TrackResult('id', 'ytdlp', 'Música', formatos=formatos,
                        extra={'consulta_em_andamento':True, 'metodos_consulta':[
                            {'nome':'JSON', 'estado':'ok', 'quantidade':2},
                            {'nome':'Lista', 'estado':'consultando'}]})
        with patch.object(search_page.EXECUTOR_GLOBAL, 'rodar'):
            busca._mostrar({'resultados':[r], 'filtrados':[], 'consulta':'Música',
                           'fontes':[], 'segundos':0, 'erros':{}})
            card = busca.cards[0]
            i = next(i for i in range(card.combo.count()) if card.combo.itemData(i).format_id == '140')
            card.combo.setCurrentIndex(i)
            card.check.setChecked(True)
            busca._detalhe_falhou(card, 'erro simulado')
            self.assertEqual(card.combo.currentData().format_id, '140')
            self.assertEqual(next(iter(busca._marcados.values()))['formato'].format_id, '140')
            self.assertIn('Consulta incompleta', card.lbl_erro_qualidade.text())
            self.assertEqual(card.resultado.extra['metodos_consulta'][1]['estado'], 'falhou')
            self.assertFalse(card.btn_verificar.isHidden())
            with patch.object(busca, '_verificar_proximo'):
                busca._detalhar(card)
            self.assertNotIn('metodos_consulta', card.resultado.extra)
            self.assertEqual(card.combo.currentData().format_id, '140')

    def test_verificacao_multipla_distribuida_entre_secoes(self):
        from app.models import TrackResult
        from app.ui.pages import search_page
        busca = self.janela.pagina_busca
        busca._buscando = True
        busca._geracao_busca += 1
        geracao = busca._geracao_busca
        busca._iniciar_grupos_parciais(['A', 'B'])
        with patch.object(search_page, 'PARALELAS', 0):
            for i, nome in enumerate(('A', 'B')):
                dados = {'consulta':nome, 'resultados':[TrackResult(nome+str(j), 'ytdlp', nome, 'Artista')
                                                         for j in range(3)], 'filtrados':[],
                         'fontes':[], 'segundos':0, 'erros':{}}
                busca._receber_parcial(geracao, i, dados)
        self.assertEqual([c.resultado.uid for c in busca._fila_verif],
                         ['A0', 'B0', 'A1', 'B1', 'A2', 'B2'])
        busca._buscando = False

    def test_pesquisa_selecao_navegacao_capas_e_inicio(self):
        from app.models import AudioFormat, CoverResult, TrackMeta, TrackResult
        from app.ui.pages import search_page, downloads_page
        r1 = TrackResult('1', 'ytdlp', 'Uma música', 'Artista',
                         pagina_url='https://www.youtube.com/watch?v=abc',
                         formatos=[AudioFormat(codec='opus', format_id='251')])
        r2 = TrackResult('2', 'ytdlp', 'Outra música', 'Artista',
                         pagina_url='https://www.youtube.com/watch?v=def',
                         formatos=[AudioFormat(codec='aac', format_id='140')])
        saida = {'resultados': [r1, r2], 'filtrados': [], 'consulta': 'Artista',
                 'fontes': ['yt-dlp'], 'segundos': 1, 'erros': {}}
        busca = self.janela.pagina_busca
        downloads = self.janela.pagina_downloads
        busca.campo.setText('Artista')
        busca.ordem.setCurrentIndex(1)
        rodadas = []

        def roda(fn, *args, **kwargs):
            rodadas.append((fn, args, kwargs))
            if fn is search_page.pesquisar:
                kwargs['ao_resultado'](saida)
            elif fn is downloads_page.preparar_musica:
                resultado = args[0]
                dados = {'meta': TrackMeta(titulo=resultado.titulo, artista=resultado.artista),
                         'ident': None, 'capa': CoverResult(observacao='nenhuma capa')}
                kwargs['ao_resultado'](dados)

        with patch.object(busca._fontes_obj['ytdlp'], 'disponivel', return_value=(True, '')), \
             patch.object(search_page.EXECUTOR_GLOBAL, 'rodar', side_effect=roda):
            busca.btn_buscar.click()
            self.assertEqual(len(busca.cards), 2)
            chamada = rodadas[0][2]
            self.assertEqual(chamada['ordenar_por'], 'qualidade')
            self.assertTrue(chamada['com_progresso'])
            busca.cards[0].check.setChecked(True)
            busca.cards[1].check.setChecked(True)
            self.assertTrue(busca.btn_lote.isEnabled())
            busca.btn_lote.click()
            self.assertEqual(self.janela.pilha.currentWidget(), downloads)
            self.assertEqual(len(downloads.selecoes), 2)
            self.assertEqual(len(self.janela.fila.jobs), 0)
            self.janela.ir_para('config')
            self.janela.ir_para('buscar')
            self.janela.ir_para('downloads')
            self.assertEqual(len(downloads.selecoes), 2)
            downloads.selecoes[1].check.setChecked(False)
            self.assertEqual(downloads.btn_baixar.isEnabled(), False)
            dialogo_sem_capa = Mock()
            dialogo_sem_capa.exec.return_value = QDialog.Accepted
            dialogo_sem_capa.recusou = True
            with patch.object(downloads_page, 'DialogoCapas', return_value=dialogo_sem_capa):
                downloads.btn_preparar.click()
            self.assertTrue(downloads.selecoes[0].preparacao is not None)
            self.assertIsNone(downloads.selecoes[1].preparacao)
            self.assertTrue(downloads.btn_baixar.isEnabled())
            with patch.object(self.janela.fila, 'adicionar', return_value=1) as adicionar:
                downloads.btn_baixar.click()
            adicionar.assert_called_once()
            self.assertEqual(adicionar.call_args.args[0].uid, '1')
            self.assertFalse(adicionar.call_args.kwargs['preparacao']['capa'].ok)
            self.assertEqual([x.pedido['resultado'].uid for x in downloads.selecoes], ['2'])
            downloads.selecoes[0].btn_remover.click()
            self.assertFalse(downloads.selecoes)

    def test_pasta_adicional_e_aviso_de_download_no_resultado(self):
        from app import arquivos_baixados
        from app.models import AudioFormat, TrackResult
        from app.ui.pages import search_page, settings_page
        from mutagen.id3 import ID3, TIT2, TPE1
        extra = self.base / 'colecao'
        extra.mkdir()
        arquivo = extra / 'sub' / 'musica.mp3'
        arquivo.parent.mkdir()
        tags = ID3()
        tags.add(TIT2(encoding=3, text='Música'))
        tags.add(TPE1(encoding=3, text='Artista'))
        tags.save(str(arquivo), v2_version=3)
        resultado = TrackResult('id-1', 'ytdlp', 'Música', 'Artista',
                                formatos=[AudioFormat(codec='mp3')])
        arquivos_baixados.marcar(arquivo, resultado)
        tela = self.janela.pagina_config
        with patch.object(settings_page.QFileDialog, 'getExistingDirectory', return_value=str(extra)):
            tela._escolher_pasta_baixados()
        tela.salvar()
        self.assertEqual(self.cfg.get('pasta_verificar_baixados'), str(extra))
        busca = self.janela.pagina_busca
        dados = {'resultados': [resultado], 'filtrados': [], 'consulta': 'Música',
                 'fontes': ['yt-dlp'], 'segundos': 1, 'erros': {}}
        with patch.object(search_page.EXECUTOR_GLOBAL, 'rodar') as rodar:
            busca._mostrar(dados)
            chamada = next(c for c in rodar.call_args_list if c.args[0] is arquivos_baixados.conferir)
            achados = chamada.args[0](*chamada.args[1:])
            chamada.kwargs['ao_resultado'](achados)
        card = busca.cards[0]
        self.assertIn('Já baixado', card.lbl_baixado.text())
        self.assertIn(str(arquivo), card.lbl_baixado.text())
        self.assertFalse(card.check.isChecked())
        novo = TrackResult('id-1', 'ytdlp', 'Música', 'Artista', formatos=[AudioFormat(codec='mp3')])
        card.aplicar_detalhes(novo)
        self.assertIn('Já baixado', card.lbl_baixado.text())
        # Resposta antiga não deve preencher cartões de uma nova pesquisa.
        busca._limpar()
        chamada.kwargs['ao_resultado'](achados)
        self.assertEqual(busca.status_baixados.text(), '')

    def test_marcacoes_e_formato_persistem_em_pesquisas_e_navegacao(self):
        from app.models import AudioFormat, TrackResult
        from app.ui.pages import search_page
        busca = self.janela.pagina_busca
        downloads = self.janela.pagina_downloads
        fmt1 = AudioFormat(codec='opus', bitrate_kbps=156, format_id='251')
        fmt2 = AudioFormat(codec='aac', bitrate_kbps=130, format_id='140')
        r1 = TrackResult('1','ytdlp','Primeira','Artista', formatos=[fmt1,fmt2])
        r2 = TrackResult('2','ytdlp','Segunda','Artista', formatos=[fmt1])
        def dados(resultados): return {'resultados':resultados,'filtrados':[],
            'consulta':'Busca', 'fontes':['yt-dlp'], 'segundos':1, 'erros':{}}
        with patch.object(search_page.EXECUTOR_GLOBAL, 'rodar'):
            busca._mostrar(dados([r1]))
            c1 = busca.cards[0]
            c1.combo.setCurrentIndex(1)
            c1.check.setChecked(True)
            self.assertEqual(c1.combo.currentData().format_id, '140')
            busca._mostrar(dados([r2]))
            self.assertIn('(1)', busca.btn_lote.text())
            busca.cards[0].check.setChecked(True)
            self.assertIn('(2)', busca.btn_lote.text())
            self.janela.ir_para('config')
            self.janela.ir_para('buscar')
            # Uma busca sem resultados não apaga os itens anteriores.
            busca._mostrar(dados([]))
            self.assertTrue(busca.btn_lote.isEnabled())
            busca._mostrar(dados([TrackResult('1','ytdlp','Primeira','Artista')]))
            self.assertTrue(busca.cards[0].check.isChecked())
            self.assertEqual(busca.cards[0].combo.currentData().format_id, '140')
            busca.btn_lote.click()
        self.assertEqual(len(downloads.selecoes), 2)
        self.assertEqual({x.pedido['resultado'].uid for x in downloads.selecoes}, {'1','2'})
        primeira = next(x for x in downloads.selecoes if x.pedido['resultado'].uid=='1')
        self.assertEqual(primeira.pedido['formato'].format_id, '140')
        self.assertFalse(busca._marcados)
        self.assertEqual(len(self.janela.fila.jobs), 0)

    def test_adicionar_um_nao_muda_pagina_e_notifica_sem_iniciar_download(self):
        from app.models import AudioFormat, TrackResult
        from app.ui.pages import search_page
        busca = self.janela.pagina_busca
        r = TrackResult('1','ytdlp','Música','Artista',
                        formatos=[AudioFormat(codec='opus', format_id='251')])
        dados = {'resultados':[r], 'filtrados':[], 'consulta':'Música',
                 'fontes':['yt-dlp'], 'segundos':1, 'erros':{}}
        with patch.object(search_page.EXECUTOR_GLOBAL, 'rodar'):
            busca._mostrar(dados)
            busca.cards[0].check.setChecked(True)
            with patch.object(self.janela.toast, 'mostrar') as toast:
                busca.cards[0].btn_processar.click()
                self.assertIn('Adicionada a Downloads', toast.call_args.args[0])
                self.assertIs(self.janela.pilha.currentWidget(), busca)
                self.assertEqual(len(self.janela.pagina_downloads.selecoes), 1)
                self.assertEqual(len(self.janela.fila.jobs), 0)
                self.assertEqual(len(busca._marcados), 0)
                busca.cards[0].btn_processar.click()
                self.assertIn('já está', toast.call_args.args[0])
                self.assertEqual(len(self.janela.pagina_downloads.selecoes), 1)

    def test_marcados_de_resultado_filtrado_e_limpar(self):
        from app.models import TrackResult
        from app.ui.pages import search_page
        busca = self.janela.pagina_busca
        dados = {'resultados':[TrackResult('1','ytdlp','Faixa')],
                 'filtrados':[TrackResult('2','ytdlp','Ao vivo')],
                 'consulta':'Faixa','fontes':['yt-dlp'],'segundos':1,'erros':{}}
        with patch.object(search_page.EXECUTOR_GLOBAL, 'rodar'):
            busca._mostrar(dados)
            busca._alternar_filtrados()
            busca._cards_filtrados[0].check.setChecked(True)
            busca._alternar_filtrados()
            self.assertEqual(len(busca._marcados), 1)
            self.assertTrue(busca.btn_lote.isEnabled())
            busca._alternar_filtrados()
            self.assertTrue(busca._cards_filtrados[0].check.isChecked())
            busca.btn_limpar_marcados.click()
            self.assertFalse(busca._marcados)
            self.assertFalse(busca._cards_filtrados[0].check.isChecked())
            self.assertFalse(busca.btn_lote.isEnabled())

    def test_cards_duplicados_sincronizam_marcacao_e_formato(self):
        from app.models import AudioFormat, TrackResult
        from app.ui.pages import search_page
        formatos = [AudioFormat(codec='opus', bitrate_kbps=150, format_id='251'),
                    AudioFormat(codec='aac', bitrate_kbps=120, format_id='140')]
        r = TrackResult('id', 'ytdlp', 'Música', 'Artista', formatos=formatos)
        busca = self.janela.pagina_busca
        with patch.object(search_page.EXECUTOR_GLOBAL, 'rodar'):
            busca._mostrar({'resultados': [r, r], 'filtrados': [], 'consulta': 'Música',
                            'fontes': ['yt-dlp'], 'segundos': 1, 'erros': {}})
        a, b = busca.cards
        a.check.setChecked(True)
        self.assertTrue(b.check.isChecked())
        b.combo.setCurrentIndex(1)
        self.assertEqual(a.combo.currentData().format_id, b.combo.currentData().format_id)
        self.assertEqual(next(iter(busca._marcados.values()))['formato'].format_id,
                         b.combo.currentData().format_id)
        a.check.setChecked(False)
        self.assertFalse(b.check.isChecked())
        self.assertFalse(busca._marcados)

    def test_pesquisa_multipla_campos_grupos_filtro_e_selecao(self):
        from app.models import AudioFormat, TrackResult
        from app.ui.pages import search_page
        busca = self.janela.pagina_varias
        self.janela.ir_para('varias')
        busca.campo_varias.setText("Guns")
        busca.campos_extras[0][1].setText("Pink Floyd")
        busca.btn_mais_campo.click()
        busca.campos_extras[-1][1].setText("Led Zeppelin")
        busca.btn_mais_campo.click()  # campo vazio não deve gerar pesquisa
        fmt = [AudioFormat(codec='opus', bitrate_kbps=128, format_id='251')]
        a = TrackResult('a', 'ytdlp', 'Primeira', 'Guns', formatos=fmt)
        b = TrackResult('b', 'ytdlp', 'Outra', 'Led', formatos=fmt)
        filtrada = TrackResult('f', 'ytdlp', 'Ao vivo', 'Guns', formatos=fmt)
        def dados(consulta, resultados, filtrados=(), erros=None):
            return {'consulta':consulta, 'resultados':list(resultados), 'filtrados':list(filtrados),
                    'fontes':['YouTube'], 'segundos':1, 'erros':erros or {}}
        retornos = [dados('Guns', [a], [filtrada]),
                    dados('Pink Floyd', [], erros={'yt': 'falhou'}), dados('Led Zeppelin', [b])]
        chamadas = []
        def rodar(fn, *args, **kwargs):
            chamadas.append((fn, args, kwargs))
            if fn is search_page.pesquisar_varias:
                kwargs['ao_resultado'](retornos)
        with patch.object(busca._fontes_obj['ytdlp'], 'disponivel', return_value=(True, '')), \
             patch.object(search_page.EXECUTOR_GLOBAL, 'rodar', side_effect=rodar):
            busca.btn_buscar_varias.click()
            self.assertEqual(chamadas[0][1][0], ['Guns', 'Pink Floyd', 'Led Zeppelin'])
            self.assertEqual([g['consulta'] for g in busca._grupos_busca], ['Guns', 'Pink Floyd', 'Led Zeppelin'])
            self.assertEqual(busca._grupos_busca[0]['cards'][0].resultado.uid, 'a')
            self.assertEqual(busca._grupos_busca[2]['cards'][0].resultado.uid, 'b')
            self.assertIn('falhou', busca._grupos_busca[1]['layout'].itemAt(1).widget().text())
            busca._grupos_busca[0]['cards'][0].check.setChecked(True)
            busca._grupos_busca[2]['cards'][0].check.setChecked(True)
            self.assertEqual(len(busca._marcados), 2)
            busca._alternar_filtrados()
            self.assertEqual(busca._grupos_busca[0]['cards_filtrados'][0].resultado.uid, 'f')
            busca._grupos_busca[0]['cards_filtrados'][0].check.setChecked(True)
            busca._alternar_filtrados()
            self.assertEqual(len(busca._marcados), 3)
            busca.ordem.setCurrentIndex(1)
            busca._fila_verif.clear()
            busca._verif_ativas = 0
            busca._status_verificacao()
            self.assertIs(busca._grupos_busca[0]['cards'][0].parentWidget(), busca._grupos_busca[0]['widget'])
            self.assertIs(busca._grupos_busca[2]['cards'][0].parentWidget(), busca._grupos_busca[2]['widget'])
            busca.btn_lote.click()
            self.assertEqual(len(self.janela.pagina_downloads.selecoes), 3)
            self.assertFalse(self.janela.fila.jobs)
        busca._limpar()
        self.assertEqual(busca._grupos_busca, [])
        self.assertEqual(busca.cards, [])

    def test_pesquisa_multipla_videos_repetidos_sincronizados(self):
        from app.models import AudioFormat, TrackResult
        from app.ui.pages import search_page
        busca = self.janela.pagina_varias
        self.janela.ir_para('varias')
        formatos = [AudioFormat(codec='opus', bitrate_kbps=150, format_id='251'),
                    AudioFormat(codec='aac', bitrate_kbps=120, format_id='140')]
        a = TrackResult('id', 'ytdlp', 'Música', 'Artista', formatos=formatos)
        b = TrackResult('id', 'ytdlp', 'Música', 'Artista', formatos=formatos)
        def dados(consulta, r):
            return {'consulta': consulta, 'resultados': [r], 'filtrados': [],
                    'fontes': [], 'segundos': 1, 'erros': {}}
        with patch.object(search_page.EXECUTOR_GLOBAL, 'rodar'):
            busca._mostrar_varias([dados('Música', a), dados('Artista', b)])
            c1, c2 = (g['cards'][0] for g in busca._grupos_busca)
            c1.check.setChecked(True)
            self.assertTrue(c2.check.isChecked())
            c2.combo.setCurrentIndex(1)
            self.assertEqual(c1.combo.currentData().format_id, c2.combo.currentData().format_id)
            self.assertEqual(len(busca._marcados), 1)
            c1.check.setChecked(False)
            self.assertFalse(c2.check.isChecked())
            self.assertFalse(busca._marcados)

    def test_pesquisa_multipla_assincrona_na_interface(self):
        import time
        from app import search_service
        from app.models import AudioFormat, TrackResult
        busca = self.janela.pagina_varias
        self.janela.ir_para('varias')
        busca.campo_varias.setText('Guns')
        busca.campos_extras[0][1].setText('Pink Floyd')
        def pesquisar_fake(termo, *args, **kwargs):
            if termo == 'Guns':
                time.sleep(0.05)
            r = TrackResult(termo, 'ytdlp', termo, 'Artista',
                            formatos=[AudioFormat(codec='opus', format_id='251')])
            return {'consulta': termo, 'resultados': [r], 'filtrados': [],
                    'fontes': ['Fonte'], 'segundos': 0, 'erros': {}}
        with patch.object(busca._fontes_obj['ytdlp'], 'disponivel', return_value=(True, '')), \
             patch.object(search_service, 'pesquisar', side_effect=pesquisar_fake), \
             patch.object(busca, '_agendar_verificacoes'), \
             patch.object(busca, '_conferir_baixados'):
            busca.pesquisar()
            limite = time.monotonic() + 5
            while busca._buscando and time.monotonic() < limite:
                self.app.processEvents()
                time.sleep(0.01)
            self.assertFalse(busca._buscando)
            self.assertEqual([g['consulta'] for g in busca._grupos_busca], ['Guns', 'Pink Floyd'])
            self.assertEqual([g['cards'][0].resultado.titulo for g in busca._grupos_busca], ['Guns', 'Pink Floyd'])
            self.assertFalse(busca.barra.isVisible())

    def test_campos_multiplos_remocao_modo_simples_e_primeiro_vazio(self):
        from app.ui.pages import search_page
        busca = self.janela.pagina_varias
        self.janela.ir_para('varias')
        busca.campos_extras[0][1].setText('Somente este')
        busca.btn_mais_campo.click()
        w = busca.campos_extras[-1][0]
        busca._remover_campo(w)
        self.assertEqual(len(busca.campos_extras), 1)
        chamadas = []
        with patch.object(busca._fontes_obj['ytdlp'], 'disponivel', return_value=(True, '')), \
             patch.object(search_page.EXECUTOR_GLOBAL, 'rodar', side_effect=lambda fn, *a, **k: chamadas.append((fn, a, k))):
            busca.pesquisar()
        self.assertIs(chamadas[0][0], search_page.pesquisar)
        self.assertEqual(chamadas[0][1][0], 'Somente este')
        busca._erro('teste')
        busca = self.janela.pagina_busca
        self.janela.ir_para('buscar')
        busca.campo.setText('Busca simples')
        chamadas.clear()
        with patch.object(busca._fontes_obj['ytdlp'], 'disponivel', return_value=(True, '')), \
             patch.object(search_page.EXECUTOR_GLOBAL, 'rodar', side_effect=lambda fn, *a, **k: chamadas.append((fn, a, k))):
            busca.pesquisar()
        self.assertIs(chamadas[0][0], search_page.pesquisar)
        self.assertEqual(chamadas[0][1][0], 'Busca simples')

    def test_reabrir_janela_recupera_marcas_e_downloads(self):
        from app.db import Banco
        from app.models import AudioFormat, TrackResult
        from app.ui.main_window import MainWindow
        from app.ui.pages import search_page
        busca = self.janela.pagina_busca
        fmt = AudioFormat(codec='opus', format_id='251')
        r1 = TrackResult('1', 'ytdlp', 'Uma', 'Artista', formatos=[fmt])
        r2 = TrackResult('2', 'ytdlp', 'Outra', 'Artista', formatos=[fmt])
        with patch.object(search_page.EXECUTOR_GLOBAL, 'rodar'):
            busca._mostrar({'resultados':[r1,r2], 'filtrados':[], 'consulta':'Artista',
                            'fontes':[], 'segundos':1, 'erros':{}})
            busca.cards[0].check.setChecked(True)
            self.janela.enfileirar({'resultado':r2, 'formato':fmt})
        busca._guardar_lista('Favoritas')
        self.janela.close()
        self.janela.deleteLater()
        self.app.processEvents()
        self.banco = Banco(self.base / 'banco.db')
        with patch('app.ui.pages.settings_page.SettingsPage._verificar_ferramentas'), \
             patch('app.ui.main_window.MainWindow._atualizar_rodape_completo'):
            self.janela = MainWindow(self.cfg, self.banco)
        self.janela.show()
        self.app.processEvents()
        self.assertEqual(len(self.janela.pagina_busca._marcados), 1)
        self.assertIs(self.janela.pagina_busca._marcados, self.janela.pagina_varias._marcados)
        self.assertIn('(1)', self.janela.pagina_varias.btn_lote.text())
        self.assertEqual(self.banco.nomes_listas(), ['Favoritas'])
        self.assertEqual(len(self.janela.pagina_downloads.selecoes), 1)
        self.assertEqual(self.janela.pagina_downloads.selecoes[0].pedido['resultado'].uid, '2')
        self.assertFalse(self.janela.fila.jobs)

    def test_resultados_tardios_ignorados_ao_fechar_as_duas_telas(self):
        from app.models import TrackResult
        for busca in (self.janela.pagina_busca, self.janela.pagina_varias):
            busca._encerrando = True
            r = TrackResult('1', 'ytdlp', 'Uma')
            with patch.object(busca, '_aplicar_detalhe') as aplicar, \
                 patch.object(busca, '_verificar_proximo') as proximo:
                busca._receber_formato_parcial(object(), object(), r)
                busca._detalhe_pronto(object(), r)
                busca._detalhe_falhou(object(), 'erro')
                busca._baixados_prontos(busca._geracao_baixados, [], {})
                busca._baixados_falharam(busca._geracao_baixados, 'erro')
                aplicar.assert_not_called(); proximo.assert_not_called()

    def test_estado_corrompido_nao_e_sobrescrito_na_inicializacao(self):
        from app.ui.pages.search_page import SearchPage
        from app.ui.pages.downloads_page import DownloadsPage
        self.banco.salvar_estado('marcacoes', [{'invalido': True}])
        self.banco.salvar_estado('downloads_selecionados', [{'invalido': True}])
        busca = SearchPage(self.cfg, self.banco, self.janela.carregador)
        downloads = DownloadsPage(self.cfg, self.janela.fila)
        self.assertTrue(busca._erro_estado_inicial)
        self.assertTrue(downloads._erro_recuperar)
        self.assertFalse(busca._gravar_marcacoes())
        self.assertFalse(downloads._persistir_selecoes())
        self.assertEqual(self.banco.ler_estado('marcacoes'), [{'invalido': True}])
        self.assertEqual(self.banco.ler_estado('downloads_selecionados'), [{'invalido': True}])
        busca.deleteLater()
        downloads.deleteLater()

    def test_marcas_listas_e_downloads_reabrem_sem_iniciar_download(self):
        from app.models import AudioFormat, CoverResult, TrackMeta, TrackResult
        from app.ui.pages.search_page import SearchPage
        from app.ui.pages.downloads_page import DownloadsPage
        from app.ui.pages import search_page
        busca = self.janela.pagina_busca
        fmt = AudioFormat(codec='opus', format_id='251')
        r = TrackResult('id', 'ytdlp', 'Música', 'Artista', formatos=[fmt])
        with patch.object(search_page.EXECUTOR_GLOBAL, 'rodar'):
            busca._mostrar({'resultados':[r], 'filtrados':[], 'consulta':'Música',
                            'fontes':[], 'segundos':1, 'erros':{}})
            busca.cards[0].check.setChecked(True)
        busca._guardar_lista('Carro')
        outra = SearchPage(self.cfg, self.banco, self.janela.carregador)
        self.assertEqual(len(outra._marcados), 1)
        self.assertEqual(next(iter(outra._marcados.values()))['formato'].format_id, '251')
        outra._limpar_marcados()
        self.assertEqual(outra._carregar_lista('Carro'), 1)
        self.assertEqual(len(outra._marcados), 1)
        self.assertEqual(self.banco.nomes_listas(), ['Carro'])
        d = self.janela.pagina_downloads
        d.adicionar_selecao({'resultado': r, 'formato': fmt, 'edicao': {'titulo':'Corrigida', 'artista':'Artista', 'album':'Disco'}})
        capa = self.base / 'capa.jpg'
        capa.write_bytes(b'imagem simulada')
        d.selecoes[0].definir_preparacao({'meta': TrackMeta(titulo='Corrigida', artista='Artista', album='Disco'),
                                           'capa': CoverResult(caminho=str(capa)), 'ident': None})
        d.selecoes[0].check.setChecked(False)
        outra_downloads = DownloadsPage(self.cfg, self.janela.fila)
        self.assertEqual(len(outra_downloads.selecoes), 1)
        linha = outra_downloads.selecoes[0]
        self.assertFalse(linha.check.isChecked())
        self.assertEqual(linha.preparacao['meta'].titulo, 'Corrigida')
        self.assertEqual(linha.preparacao['capa'].caminho, str(capa))
        self.assertFalse(self.janela.fila.jobs)
        capa.unlink()
        terceira = DownloadsPage(self.cfg, self.janela.fila)
        self.assertIsNone(terceira.selecoes[0].preparacao)
        self.assertFalse(terceira.btn_baixar.isEnabled())
        for w in (outra, outra_downloads, terceira):
            w.deleteLater()

    def test_falha_ao_salvar_download_nao_apaga_marcacao(self):
        from app.models import AudioFormat, TrackResult
        from app.ui.pages import search_page
        busca = self.janela.pagina_busca
        r = TrackResult('id', 'ytdlp', 'Música', 'Artista', formatos=[AudioFormat(format_id='251')])
        with patch.object(search_page.EXECUTOR_GLOBAL, 'rodar'):
            busca._mostrar({'resultados':[r], 'filtrados':[], 'consulta':'Música',
                            'fontes':[], 'segundos':1, 'erros':{}})
        busca.cards[0].check.setChecked(True)
        original = self.banco.salvar_estado
        def falha(chave, dados):
            if chave == 'downloads_selecionados':
                raise OSError('sem espaço')
            return original(chave, dados)
        with patch.object(self.banco, 'salvar_estado', side_effect=falha):
            busca.btn_lote.click()
        self.assertEqual(len(busca._marcados), 1)
        self.assertFalse(self.janela.pagina_downloads.selecoes)
        self.assertEqual(len(self.banco.ler_estado('marcacoes')), 1)

    def test_botao_tentar_novamente_cria_nova_tentativa(self):
        from app.models import AudioFormat, CoverResult, TrackMeta, TrackResult
        fila = self.janela.fila
        self.cfg.dados['pasta_saida'] = str(self.base / 'saida')
        r = TrackResult('id', 'ytdlp', 'Música', 'Artista')
        formato = AudioFormat(codec='opus', format_id='251')
        prep = {'meta':TrackMeta(titulo='Música', artista='Artista'), 'capa':CoverResult(), 'ident':None}
        iniciados = []
        with patch.object(fila, '_iniciar', side_effect=lambda item: iniciados.append(item)):
            jid = fila.adicionar(r, formato, preparacao=prep)
            fila._concluir(fila.jobs[jid], {'ok':False, 'erro':'falha simulada'})
            self.janela.ir_para('downloads')
            linha = self.janela.pagina_downloads.linhas[jid]
            self.assertFalse(linha.btn_tentar.isHidden())
            linha.btn_tentar.click()
            self.assertTrue(linha.btn_tentar.isHidden())
            self.assertEqual(len(iniciados), 2)
            self.assertIs(iniciados[1]['preparacao'], prep)
            self.assertEqual(iniciados[1]['formato'].format_id, '251')
            fila.jobs[iniciados[1]['job']['id']]['status'] = 'cancelado'
            fila._ativos = 0

    def test_fila_real_local_download_erro_e_tentativa(self):
        import functools
        import shutil
        import subprocess
        import threading
        import time
        from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
        from mutagen.id3 import ID3
        from app import pipeline
        from app.models import AudioFormat, CoverResult, TrackMeta, TrackResult
        if not shutil.which('ffmpeg') or not shutil.which('yt-dlp'):
            self.skipTest('ffmpeg e yt-dlp são necessários')
        class Handler(SimpleHTTPRequestHandler):
            def log_message(self, *args):
                pass
        origem = self.base / 'som.wav'
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
                        'sine=frequency=440:duration=0.5', str(origem)], check=True)
        servidor = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Handler, directory=str(self.base)))
        thread = threading.Thread(target=servidor.serve_forever, daemon=True)
        thread.start()
        pasta_saida = self.base / 'saída'
        self.cfg.dados.update(pasta_saida=str(pasta_saida), usar_cookies=False)
        pagina = self.janela.pagina_downloads
        self.janela.ir_para('downloads')
        base_url = f'http://127.0.0.1:{servidor.server_port}'
        try:
            for uid, nome, url in [('ok', 'Primeira', base_url + '/som.wav'),
                                    ('erro', 'Segunda', base_url + '/falta.wav')]:
                fmt = AudioFormat(format_id='bestaudio')
                r = TrackResult(uid, 'ytdlp', nome, 'Artista', pagina_url=url)
                self.assertTrue(pagina.adicionar_selecao({'resultado':r, 'formato':fmt}))
                pagina.selecoes[-1].definir_preparacao({'meta':TrackMeta(titulo=nome, artista='Artista', album='Disco'),
                                                         'capa':CoverResult(), 'ident':None})
            with patch.object(pipeline, 'PASTA_TEMP', self.base / 'temp'):
                pagina.btn_baixar.click()
                limite = time.monotonic() + 40
                while self.janela.fila.pendentes and time.monotonic() < limite:
                    self.app.processEvents()
                    time.sleep(.02)
                self.assertEqual(self.janela.fila.pendentes, 0)
                jobs = list(self.janela.fila.jobs.values())
                self.assertEqual([j['status'] for j in jobs], ['finalizado', 'erro'])
                self.assertTrue((pasta_saida / 'Artista' / 'Primeira.mp3').is_file())
                self.assertFalse((pasta_saida / 'Artista' / 'Segunda.mp3').exists())
                shutil.copyfile(origem, self.base / 'falta.wav')
                linha = pagina.linhas[jobs[1]['id']]
                self.assertFalse(linha.btn_tentar.isHidden())
                linha.btn_tentar.click()
                limite = time.monotonic() + 40
                while self.janela.fila.pendentes and time.monotonic() < limite:
                    self.app.processEvents()
                    time.sleep(.02)
                self.assertEqual(self.janela.fila.pendentes, 0)
                tentativa = list(self.janela.fila.jobs.values())[-1]
                self.assertEqual(tentativa['status'], 'finalizado', tentativa)
                destino = pasta_saida / 'Artista' / 'Segunda.mp3'
                self.assertTrue(destino.is_file())
                self.assertEqual(str(ID3(str(destino))['TALB']), 'Disco')
                self.assertFalse(ID3(str(destino)).getall('APIC'))
        finally:
            servidor.shutdown()
            servidor.server_close()
            thread.join()

    def test_editar_e_preparar_sem_capa_no_lote(self):
        from app.models import CoverResult, TrackMeta, TrackResult
        from app.ui.pages import downloads_page
        d = self.janela.pagina_downloads
        for i in range(2):
            d.adicionar_selecao({'resultado':TrackResult(str(i),'ytdlp', f'Música {i}', 'Artista')})
        dialogo = Mock()
        dialogo.exec.return_value = QDialog.Accepted
        dialogo.valores.return_value = {'titulo':'Título corrigido', 'artista':'Novo artista', 'album':'Álbum'}
        with patch.object(downloads_page, 'DialogoEditarDados', return_value=dialogo):
            d._editar_dados(d.selecoes[0])
        self.assertEqual(d.selecoes[0].pedido['edicao']['titulo'], 'Título corrigido')
        chamadas = []
        def rodar(fn, *args, **kwargs):
            chamadas.append(kwargs)
            r = args[0]
            ed = kwargs.get('edicao') or {}
            kwargs['ao_resultado']({'meta': TrackMeta(titulo=ed.get('titulo', r.titulo),
                artista=ed.get('artista', r.artista), album=ed.get('album', '')),
                'capa': CoverResult(), 'ident': None})
        with patch.object(downloads_page.QMessageBox, 'question', return_value=QMessageBox.Yes), \
             patch.object(downloads_page.EXECUTOR_GLOBAL, 'rodar', side_effect=rodar), \
             patch.object(downloads_page, 'DialogoCapas', side_effect=AssertionError('não deve abrir')):
            d.btn_sem_capa.click()
        self.assertEqual(len(chamadas), 2)
        self.assertTrue(all(c['sem_capa'] for c in chamadas))
        self.assertEqual(d.selecoes[0].preparacao['meta'].titulo, 'Título corrigido')
        self.assertTrue(all(not l.preparacao['capa'].ok for l in d.selecoes))
        self.assertTrue(d.btn_baixar.isEnabled())
        self.assertFalse(self.janela.fila.jobs)

    def test_pesquisa_multipla_exibe_primeiro_resultado_enquanto_outro_espera(self):
        import threading, time
        from app import search_service
        from app.models import AudioFormat, TrackResult
        busca = self.janela.pagina_varias
        self.janela.ir_para('varias')
        busca.campo_varias.setText('Lenta')
        busca.campos_extras[0][1].setText('Rápida')
        liberar = threading.Event()
        def pesquisar_fake(termo, *args, **kwargs):
            if termo == 'Lenta':
                if not liberar.wait(4):
                    raise RuntimeError('timeout de teste')
            r = TrackResult(termo, 'ytdlp', termo, 'Artista',
                formatos=[AudioFormat(codec='opus', format_id='251')], extra={'metodos_consulta':[{}]})
            return {'consulta':termo, 'resultados':[r], 'filtrados':[], 'fontes':[], 'segundos':0, 'erros':{}}
        try:
            with patch.object(busca._fontes_obj['ytdlp'], 'disponivel', return_value=(True, '')), \
                 patch.object(search_service, 'pesquisar', side_effect=pesquisar_fake), \
                 patch.object(busca, '_conferir_baixados'):
                busca.pesquisar()
                limite = time.monotonic() + 3
                while not busca._grupos_busca[1]['cards'] and time.monotonic() < limite:
                    self.app.processEvents()
                    time.sleep(.01)
                self.assertTrue(busca._buscando)
                self.assertTrue(busca._grupos_busca[1]['cards'])
                self.assertFalse(busca._grupos_busca[0]['cards'])
                busca._grupos_busca[1]['cards'][0].check.setChecked(True)
                liberar.set()
                limite = time.monotonic() + 3
                while busca._buscando and time.monotonic() < limite:
                    self.app.processEvents()
                    time.sleep(.01)
                self.assertFalse(busca._buscando)
                self.assertEqual([g['consulta'] for g in busca._grupos_busca], ['Lenta', 'Rápida'])
                self.assertTrue(busca._grupos_busca[1]['cards'][0].check.isChecked())
                self.assertEqual(len(busca._marcados), 1)
        finally:
            liberar.set()

    def test_formato_marcado_nao_e_trocado_por_consulta_incompleta(self):
        from app.models import AudioFormat, TrackResult
        from app.ui.pages import search_page
        busca = self.janela.pagina_busca
        f1 = AudioFormat(codec='opus', bitrate_kbps=150, format_id='251')
        f2 = AudioFormat(codec='aac', bitrate_kbps=120, format_id='140')
        r = TrackResult('id', 'ytdlp', 'Música', 'Artista', formatos=[f1, f2])
        with patch.object(search_page.EXECUTOR_GLOBAL, 'rodar'):
            busca._mostrar({'resultados':[r], 'filtrados':[], 'consulta':'Música',
                            'fontes':[], 'segundos':1, 'erros':{}})
            card = busca.cards[0]
            i = next(i for i in range(card.combo.count()) if card.combo.itemData(i).format_id == '140')
            card.combo.setCurrentIndex(i)
            card.check.setChecked(True)
            incompleto = TrackResult('id', 'ytdlp', 'Música', 'Artista', formatos=[f1],
                                     extra={'metodos_consulta':[{'nome':'teste','estado':'ok'}]})
            busca._detalhe_pronto(card, incompleto)
        self.assertEqual(card.combo.currentData().format_id, '140')
        self.assertIn('não confirmado', card.combo.currentText())
        self.assertEqual(next(iter(busca._marcados.values()))['formato'].format_id, '140')
        self.assertEqual(self.banco.ler_estado('marcacoes')[0]['formato']['format_id'], '140')

    def test_lista_restaura_formato_nao_confirmado_pelo_cartao(self):
        from app.models import AudioFormat, TrackResult
        from app.ui.pages import search_page
        busca = self.janela.pagina_busca
        f1 = AudioFormat(codec='opus', bitrate_kbps=150, format_id='251')
        f2 = AudioFormat(codec='aac', bitrate_kbps=120, format_id='140')
        r = TrackResult('id', 'ytdlp', 'Música', 'Artista', formatos=[f1, f2])
        with patch.object(search_page.EXECUTOR_GLOBAL, 'rodar'):
            busca._mostrar({'resultados':[r], 'filtrados':[], 'consulta':'Música',
                            'fontes':[], 'segundos':1, 'erros':{}})
            card = busca.cards[0]
            i = next(i for i in range(card.combo.count()) if card.combo.itemData(i).format_id == '140')
            card.combo.setCurrentIndex(i)
            card.check.setChecked(True)
            busca._guardar_lista('Teste')
            busca._limpar_marcados()
            incompleto = TrackResult('id', 'ytdlp', 'Música', 'Artista', formatos=[f1])
            busca._mostrar({'resultados':[incompleto], 'filtrados':[], 'consulta':'Música',
                            'fontes':[], 'segundos':1, 'erros':{}})
            busca._carregar_lista('Teste')
            self.assertEqual(busca.cards[0].combo.currentData().format_id, '140')
            self.assertIn('não confirmado', busca.cards[0].combo.currentText())

    def test_transferencia_duplicata_nao_apaga_marcacao_se_salvar_falha(self):
        from app.models import TrackResult
        from app.ui.pages import search_page
        busca = self.janela.pagina_busca
        r = TrackResult('id', 'ytdlp', 'Música', 'Artista')
        self.assertTrue(self.janela.enfileirar({'resultado':r}))
        with patch.object(search_page.EXECUTOR_GLOBAL, 'rodar'):
            busca._mostrar({'resultados':[r], 'filtrados':[], 'consulta':'Música',
                            'fontes':[], 'segundos':1, 'erros':{}})
            busca.cards[0].check.setChecked(True)
            with patch.object(self.janela.pagina_downloads, '_persistir_selecoes', return_value=False):
                busca._processar_lote()
        self.assertEqual(len(busca._marcados), 1)

    def test_falha_sincrona_ao_iniciar_fila_libera_job_e_permite_retry(self):
        from app.models import TrackResult
        from app import downloader
        fila = self.janela.fila
        r = TrackResult('id', 'ytdlp', 'Música', 'Artista')
        with patch.object(downloader.sources, 'por_id', side_effect=RuntimeError('falha ao iniciar')):
            jid = fila.adicionar(r)
        self.assertEqual(fila.jobs[jid]['status'], 'erro')
        self.assertEqual(fila.ativos, 0)
        self.assertEqual(fila.pendentes, 0)
        self.assertEqual(len(fila.fila), 0)
        with patch.object(downloader.EXECUTOR_GLOBAL, 'rodar') as rodar:
            outro = fila.tentar_novamente(jid)
        self.assertEqual(fila.jobs[outro]['status'], 'analisando')
        rodar.assert_called_once()
        fila.jobs[outro]['status'] = 'erro'

    def test_callback_da_fila_ignorado_apos_fechar(self):
        from app.models import TrackResult
        from app import downloader
        fila = self.janela.fila
        r = TrackResult('id', 'ytdlp', 'Música', 'Artista')
        with patch.object(downloader.EXECUTOR_GLOBAL, 'rodar') as rodar:
            jid = fila.adicionar(r)
        callbacks = rodar.call_args.kwargs
        fila.encerrar()
        self.banco.fechar()
        callbacks['ao_progresso'](20, 'baixando')
        callbacks['ao_resultado']({'ok':True})
        callbacks['ao_erro']('erro')
        self.assertEqual(fila.jobs[jid]['status'], 'analisando')
        fila.jobs[jid]['status'] = 'erro'

    def test_resultado_exibe_quatro_metodos_e_origem_do_formato(self):
        from app.models import AudioFormat, TrackResult
        from app.ui.pages import search_page
        formatos = [AudioFormat(codec='opus', bitrate_kbps=128, format_id='251',
                                extra={'metodos':['Lista -F','JSON -j']}),
                    AudioFormat(codec='aac', bitrate_kbps=128, format_id='140',
                                extra={'metodos':['Biblioteca Python']})]
        resultados = [{'nome': 'Lista -F', 'estado':'ok', 'quantidade':1},
                      {'nome': 'JSON -j', 'estado':'ok', 'quantidade':1},
                      {'nome': 'Lista + JSON', 'estado':'falhou', 'quantidade':0, 'motivo':'consulta falhou'},
                      {'nome': 'Biblioteca Python', 'estado':'ok', 'quantidade':1}]
        r = TrackResult('id', 'ytdlp', 'Música', 'Artista', formatos=formatos,
                        extra={'metodos_consulta':resultados})
        dados = {'resultados':[r], 'filtrados':[], 'consulta':'Música', 'fontes':['yt-dlp'],
                 'segundos':1, 'erros':{}}
        busca = self.janela.pagina_busca
        with patch.object(search_page.EXECUTOR_GLOBAL, 'rodar'):
            busca._mostrar(dados)
        card = busca.cards[0]
        for nome in ('Lista -F', 'JSON -j', 'Lista + JSON', 'Biblioteca Python'):
            self.assertIn(nome, card.lbl_metodos_qualidade.toolTip())
        self.assertIn('consulta falhou', card.lbl_metodos_qualidade.toolTip())
        self.assertIn('Lista -F', card.lbl_origem_formato.text())
        card.combo.setCurrentIndex(1)
        self.assertIn('Biblioteca Python', card.lbl_origem_formato.text())
        self.assertFalse(card.check.isChecked())

    def test_comparar_formatos_mostra_campos_e_seleciona_sem_baixar(self):
        from app.models import AudioFormat, TrackResult
        from app.ui.pages import search_page
        from app.ui.widgets.format_details import DialogoFormatos
        fmt1 = AudioFormat(codec='opus', bitrate_kbps=156, format_id='251',
            extra={'metodos':['JSON -j'], 'detalhes_audio':{'abr':155.8,'asr':48000,
                   'vcodec':'none','acodec':'opus','audio_channels':2}})
        fmt2 = AudioFormat(codec='aac', format_id='301',
            extra={'metodos':['Lista -F'], 'detalhes_audio':{'vcodec':'unknown','tbr':900}})
        r = TrackResult('id','ytdlp','Música',formatos=[fmt1,fmt2])
        dados = {'resultados':[r], 'filtrados':[], 'consulta':'Música',
                 'fontes':['yt-dlp'], 'segundos':1, 'erros':{}}
        with patch.object(search_page.EXECUTOR_GLOBAL, 'rodar'):
            self.janela.pagina_busca._mostrar(dados)
        card = self.janela.pagina_busca.cards[0]
        self.assertTrue(card.btn_formatos.isEnabled())
        dialogo = DialogoFormatos(r, fmt1, card)
        self.assertEqual(dialogo.tabela.rowCount(), 2)
        self.assertEqual(dialogo.tabela.item(0, 2).text(), '155.8 kbps')
        self.assertEqual(dialogo.tabela.item(1, 2).text(), 'não informado')
        dialogo.tabela.selectRow(1)
        self.assertIn('900 kbps', dialogo.detalhes.toPlainText())
        self.assertEqual(dialogo.formato_selecionado().format_id, '301')
        dialogo.close()
        def selecionar(dialogo):
            dialogo.tabela.selectRow(1)
            return QDialog.Accepted
        emissoes = []
        card.processar.connect(lambda dados: emissoes.append(dados))
        with patch.object(DialogoFormatos, 'exec', selecionar):
            card._comparar_formatos()
        self.assertEqual(emissoes, [])
        self.assertEqual(card.combo.currentData().format_id, '301')
        self.assertIn('bitrate não informado', card.combo.currentText())
        self.assertIn('Lista -F', card.lbl_origem_formato.text())
        with patch.object(DialogoFormatos, 'exec', return_value=QDialog.Rejected):
            card._comparar_formatos()
        self.assertEqual(card.combo.currentData().format_id, '301')

    def test_todos_resultados_na_fila_e_ordem_por_qualidade_preserva_selecao(self):
        from app.models import AudioFormat, TrackResult
        from app.ui.pages import search_page
        resultados = [TrackResult(str(i), 'ytdlp', 'Música', 'Artista',
                                  pagina_url='https://example.com/' + str(i)) for i in range(13)]
        dados = {'resultados':resultados, 'filtrados':[], 'consulta':'Música',
                 'fontes':['yt-dlp'], 'segundos':1, 'erros':{}}
        busca = self.janela.pagina_busca
        busca.ordem.setCurrentIndex(1)
        with patch.object(search_page.EXECUTOR_GLOBAL, 'rodar'):
            busca._mostrar(dados)
        self.assertEqual(busca._verif_ativas + len(busca._fila_verif), 13)
        card = busca.cards[-1]
        card.marcar(True)
        card.resultado.formatos = [AudioFormat(codec='opus', bitrate_kbps=160, format_id='251')]
        busca._fila_verif.clear()
        busca._verif_ativas = 0
        busca._status_verificacao()
        self.assertIs(busca.cards[0], card)
        self.assertTrue(card.check.isChecked())

    def test_falha_qualidade_mostra_motivo_sem_repeticao_automatica(self):
        from app.models import TrackResult
        from app.ui.pages import search_page
        r = TrackResult('id', 'ytdlp', 'Música', 'Artista',
                        extra={'erro_detalhe': 'O yt-dlp encontrou somente imagens'})
        busca = self.janela.pagina_busca
        dados = {'resultados': [r], 'filtrados': [], 'consulta': 'Música',
                 'fontes': ['yt-dlp'], 'segundos': 1, 'erros': {}}
        with patch.object(search_page.EXECUTOR_GLOBAL, 'rodar') as rodar:
            busca._mostrar(dados)
            self.assertFalse(any(getattr(c.args[0], '__name__', '') == 'detalhar'
                                 for c in rodar.call_args_list))
            card = busca.cards[0]
            self.assertIn('somente imagens', card.lbl_erro_qualidade.text())
            with patch.object(busca, '_verificar_proximo') as tentar:
                busca._detalhar(card)
            tentar.assert_called_once()
            self.assertNotIn('erro_detalhe', r.extra)

    def test_fontes_capa_salvas_e_desativadas(self):
        tela = self.janela.pagina_config
        self.assertIn('deezer', self.cfg.get('fontes_capa'))
        for chk in tela.fontes_capas_visiveis.values():
            chk.setChecked(False)
        tela.salvar()
        self.assertEqual(self.cfg.get('fontes_capa'), [])
        tela.fontes_capas_visiveis['deezer'].setChecked(True)
        tela.salvar()
        self.assertEqual(self.cfg.get('fontes_capa'), ['deezer'])
        from app.config import Config
        self.assertEqual(Config(self.cfg.caminho).get('fontes_capa'), ['deezer'])

    def test_escolher_capa_alternativa_e_cancelar(self):
        from app.models import CoverResult, TrackMeta, TrackResult
        from app.ui.pages import downloads_page
        d = self.janela.pagina_downloads
        r = TrackResult('1', 'ytdlp', 'Música', 'Artista')
        d.adicionar_selecao({'resultado': r})
        linha = d.selecoes[0]
        primeira = CoverResult(caminho=str(self.base / 'a.jpg'))
        outra = CoverResult(caminho=str(self.base / 'b.jpg'))
        primeira.alternativas = [outra]
        dados = {'meta': TrackMeta(titulo='Música', artista='Artista'), 'capa': primeira, 'ident': None}
        def rodar(fn, *args, **kwargs): kwargs['ao_resultado'](dados)
        dialogo = Mock()
        dialogo.exec.return_value = QDialog.Accepted
        dialogo.escolhida = outra
        dialogo.recusou = False
        with patch.object(downloads_page.EXECUTOR_GLOBAL, 'rodar', side_effect=rodar), \
             patch.object(downloads_page, 'DialogoCapas', return_value=dialogo):
            linha.btn_capa.click()
        self.assertIs(linha.preparacao['capa'], outra)
        anterior = linha.preparacao
        dialogo.exec.return_value = QDialog.Rejected
        with patch.object(downloads_page.EXECUTOR_GLOBAL, 'rodar', side_effect=rodar), \
             patch.object(downloads_page, 'DialogoCapas', return_value=dialogo):
            linha.btn_capa.click()
        self.assertIs(linha.preparacao, anterior)
        self.assertFalse(d._preparando)

    def test_aviso_inicial_sem_widget_de_versao_anterior_e_timer_real(self):
        import sys
        from PySide6.QtTest import QTest
        from app.ui.main_window import MainWindow
        # Reproduz uma página antiga sem o atributo citado no traceback.
        self.cfg.dados['pasta_saida'] = str(self.base / 'pasta-ausente')
        erros = []
        with patch('app.ui.pages.settings_page.SettingsPage._verificar_ferramentas'), \
             patch('app.ui.main_window.MainWindow._atualizar_rodape_completo'), \
             patch.object(sys, 'excepthook', side_effect=lambda *args: erros.append(args)):
            janela = MainWindow(self.cfg, self.banco)
            try:
                del janela.pagina_config.aviso_pasta_saida
                janela.show()
                QTest.qWait(500)  # dispara o QTimer de 350 ms de verdade
                self.assertEqual(erros, [])
                self.assertIn('Pasta de saída indisponível', janela.statusBar().currentMessage())
                self.assertFalse((self.base / 'pasta-ausente').exists())
                self.assertEqual(self.cfg.get('pasta_saida'), str(self.base / 'pasta-ausente'))
            finally:
                janela.close()
                janela.deleteLater()

    def test_aviso_inicial_com_pasta_valida_nao_mostra_erro(self):
        self.cfg.dados['pasta_saida'] = str(self.base)
        with patch.object(self.janela.toast, 'mostrar') as toast:
            self.janela._avisar_pasta_saida_inicial()
        toast.assert_not_called()

    def test_janela_abre_com_pasta_invalida_e_usuario_escolhe_outro_destino(self):
        from app.ui.main_window import MainWindow
        from app.ui.pages import settings_page
        pasta_indisponivel = self.base / 'arquivo-nao-e-pasta'
        pasta_indisponivel.write_text('não modificar')
        self.cfg.dados['pasta_saida'] = str(pasta_indisponivel / 'músicas')
        caminho_original = self.cfg.get('pasta_saida')
        with patch('app.ui.pages.settings_page.SettingsPage._verificar_ferramentas'), \
             patch('app.ui.main_window.MainWindow._atualizar_rodape_completo'):
            janela = MainWindow(self.cfg, self.banco)
        try:
            janela.show()
            janela._avisar_pasta_saida_inicial()
            self.assertIn('Pasta de saída indisponível', janela.statusBar().currentMessage())
            tela = janela.pagina_config
            self.assertEqual(tela.campo_saida.text(), caminho_original)
            self.assertIn('indisponível', tela.aviso_pasta_saida.text())
            self.assertEqual(self.cfg.get('pasta_saida'), caminho_original)
            with patch.object(settings_page.QFileDialog, 'getExistingDirectory', return_value=str(self.base)):
                tela._escolher_saida()
            self.assertEqual(tela.aviso_pasta_saida.text(), '')
            self.assertEqual(self.cfg.get('pasta_saida'), caminho_original)  # só salva a pedido
            tela.salvar()
            self.assertEqual(self.cfg.get('pasta_saida'), str(self.base))
            from app.config import Config
            self.assertEqual(Config(self.cfg.caminho).get('pasta_saida'), str(self.base))
            self.assertEqual(pasta_indisponivel.read_text(), 'não modificar')
        finally:
            janela.close()
            janela.deleteLater()

    def test_lote_com_destino_invalido_avisado_sem_baixar_ou_perder_selecao(self):
        from app.models import CoverResult, TrackMeta, TrackResult
        from app.ui.pages import downloads_page
        invalido = self.base / 'arquivo'
        invalido.write_text('arquivo intocado')
        self.cfg.dados['pasta_saida'] = str(invalido / 'músicas')
        d = self.janela.pagina_downloads
        r = TrackResult('1', 'ytdlp', 'Música', 'Artista')
        d.adicionar_selecao({'resultado': r})
        linha = d.selecoes[0]
        linha.definir_preparacao({'meta': TrackMeta(titulo='Música'), 'capa': CoverResult(), 'ident':None})
        with patch.object(downloads_page.QMessageBox, 'warning') as aviso, \
             patch.object(d.fila, 'adicionar') as adicionar:
            d._baixar_selecionadas()
        aviso.assert_called_once()
        self.assertIn('Pasta de saída indisponível', aviso.call_args.args[2])
        adicionar.assert_not_called()
        self.assertIn(linha, d.selecoes)
        self.assertEqual(invalido.read_text(), 'arquivo intocado')

    def test_configuracoes_saida_cookies_groq_e_verificacao_de_ferramentas(self):
        from app import tools
        from app.ui.pages import settings_page
        tela = self.janela.pagina_config
        self.cfg.dados['ytdlp_consentido'] = True
        with patch.object(settings_page.QFileDialog, 'getExistingDirectory', return_value=str(self.base)):
            tela._escolher_saida()
        self.assertEqual(tela.campo_saida.text(), str(self.base))
        cookies = self.base / 'meus cookies.txt'
        cookies.write_text('# Netscape HTTP Cookie File\n')
        with patch.object(settings_page.QFileDialog, 'getOpenFileName', return_value=(str(cookies), '')):
            tela.btn_escolher_cookies.click()
        self.assertEqual(str(self.cfg.caminho_cookies), str(cookies))
        with patch.object(settings_page.seguranca, 'guardar', return_value=(True, 'ok')) as guardar:
            tela.campo_chave.setText('chave-de-teste')
            tela.btn_salvar_chave.click()
            guardar.assert_called_once_with('chave-de-teste')
            self.assertEqual(tela.campo_chave.text(), '')
        busca = self.janela.pagina_busca
        busca.chk_filtro.setChecked(False)
        busca.checks['archive_org'].setChecked(True)
        with patch.object(settings_page.seguranca, 'existe', return_value=True), \
             patch.object(tela, '_atualizar_ia'):
            tela.chk_ia.setChecked(True)
            tela.btn_salvar.click()
        self.assertFalse(self.cfg.get('evitar_ao_vivo'))
        self.assertTrue(busca.checks['archive_org'].isChecked())
        self.assertTrue(self.cfg.get('ia_ativa'))
        self.assertEqual(str(self.cfg.pasta_saida), str(self.base))
        dados = {'ffmpeg': tools.Ferramenta('ffmpeg', '/teste/ffmpeg', '7.0'),
                 'ffprobe': tools.Ferramenta('ffprobe', erro='ausente'),
                 'yt-dlp': tools.Ferramenta('yt-dlp', erro='inválido')}
        def rodar(fn, *args, **kwargs):
            kwargs['ao_resultado'](dados)
        with patch.object(settings_page.EXECUTOR_GLOBAL, 'rodar', side_effect=rodar):
            tela._verificar_ferramentas()
        self.assertEqual(tela.chips_ferr['ffmpeg'].text(), 'ok')
        self.assertEqual(tela.chips_ferr['yt-dlp'].text(), 'indisponível')
        self.assertIn('indisponível', self.janela.pagina_busca.checks['ytdlp'].text())
        def conexao_simulada(fn, *args, **kwargs):
            kwargs['ao_resultado']({'ok': True, 'mensagem': 'Conexão simulada OK', 'modelos': []})
        with patch.object(settings_page.EXECUTOR_GLOBAL, 'rodar', side_effect=conexao_simulada):
            tela.btn_testar_ia.click()
        self.assertEqual(tela.lbl_ia.text(), 'Conexão simulada OK')
        self.assertTrue(tela.btn_testar_ia.isEnabled())

    def test_filtrados_visiveis(self):
        from app.models import TrackResult
        busca = self.janela.pagina_busca
        r = TrackResult('3', 'ytdlp', 'Show ao vivo', 'Artista', ao_vivo=True)
        busca._mostrar({'resultados': [], 'filtrados': [r], 'consulta': 'Artista',
                        'fontes': [], 'segundos': 0, 'erros': {}})
        self.assertTrue(busca.btn_filtrados.isEnabled())
        busca.btn_filtrados.click()
        self.assertEqual(len(busca.cards), 1)
        self.assertTrue(busca.btn_melhores.isEnabled())
        self.assertFalse(busca.vazio.isVisible())
        busca.btn_filtrados.click()
        self.assertEqual(len(busca.cards), 0)
        self.assertTrue(busca.vazio.isVisible())

    def test_botao_cancelar_so_para_fila(self):
        from app.ui.pages.downloads_page import LinhaJob
        self.janela.ir_para('downloads')
        linha = LinhaJob({'id': 1, 'status': 'na fila'}, self.janela.pagina_downloads)
        linha.show()
        self.assertTrue(linha.btn_cancelar.isVisible())
        linha.atualizar({'id': 1, 'status': 'baixando'})
        self.assertFalse(linha.btn_cancelar.isVisible())
        linha.close()

    def test_fecha_com_aviso_quando_ha_trabalho_em_andamento(self):
        from app.ui import main_window
        self.janela.pagina_downloads._preparando = True
        evento = Mock()
        with patch.object(main_window.QMessageBox, 'warning', return_value=QMessageBox.No):
            self.janela.closeEvent(evento)
        evento.ignore.assert_called_once()
        self.janela.pagina_downloads._preparando = False

    def test_previa_com_fallback_abre_url_e_fecha(self):
        from app.models import TrackResult
        from app.ui.widgets import preview_widget
        resultado = TrackResult('1', 'ytdlp', 'Música', 'Artista',
                                pagina_url='https://www.youtube.com/watch?v=abc', extra={'id': 'abc'})
        previa = self.janela.pagina_busca.previa
        with patch.object(preview_widget, 'webengine_disponivel', return_value=False):
            previa.mostrar(resultado)
        self.assertTrue(previa.isVisible())
        self.assertFalse(previa.btn_tocar.isEnabled())
        with patch.object(preview_widget.QDesktopServices, 'openUrl', return_value=True) as abrir:
            previa.btn_original.click()
        self.assertEqual(abrir.call_args.args[0].toString(), resultado.pagina_url)
        previa.btn_fechar.click()
        self.assertFalse(previa.isVisible())

if __name__ == '__main__':
    unittest.main()

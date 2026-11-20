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
        from app.workers import EXECUTOR_GLOBAL
        EXECUTOR_GLOBAL.aguardar(30000)
        self.app.processEvents()
        from PySide6.QtCore import QCoreApplication, QEvent
        self.janela.close()
        self.janela.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.app.processEvents()
        self.temp.cleanup()

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
            self.assertIn(nome, card.lbl_metodos_qualidade.text())
        self.assertIn('consulta falhou', card.lbl_metodos_qualidade.text())
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

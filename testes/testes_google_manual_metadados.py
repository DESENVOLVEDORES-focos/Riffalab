"""Fluxo manual de capas e regressões para dados de uma música."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtGui import QImage, QDesktopServices
from PySide6.QtWidgets import QApplication, QFileDialog
from app import pipeline, preparacao
from app.config import Config
from app.metadata import covers, itunes, musicbrainz
from app.models import CoverResult, TrackResult
from app.ui.dialogos import DialogoCapas


class GoogleManual(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.cfg = Config(self.base / 'config.json')

    def test_preparacao_nunca_consulta_apis_de_capa_nem_baixa_audio(self):
        r = TrackResult('id', 'ytdlp', 'November Rain', "Guns N' Roses")
        with patch.object(pipeline.covers, 'metadados_completos', return_value={}), \
             patch.object(pipeline.covers, 'encontrar_capa', side_effect=AssertionError('busca de capa')), \
             patch.object(pipeline, 'processar_resultado', side_effect=AssertionError('download')):
            dados = preparacao.preparar_musica(r, self.cfg)
        self.assertEqual((dados['consulta_capa']['titulo'], dados['consulta_capa']['artista']),
                         ('November Rain', "Guns N' Roses"))
        self.assertFalse(dados['capa'].ok)

    def test_ao_abrir_nao_pesquisa_ate_apertar_botao(self):
        pasta = self.base/'Download de Capas'
        musica = {'artista':"Guns N' Roses", 'titulo':'November Rain', 'album':'Possível álbum incorreto',
                  'abrir_google_automaticamente':True, 'metadados':{'album':'Álbum sugerido', 'faixa':10}}
        with patch('app.config.PASTA_DOWNLOAD_CAPAS', pasta), \
             patch.object(QDesktopServices, 'openUrl', return_value=True) as abrir:
            dlg = DialogoCapas(None, CoverResult(), musica)
            dlg.show(); self.app.processEvents()
            self.assertFalse(hasattr(dlg, 'btn_arquivo'))
            self.assertTrue(pasta.is_dir())
            abrir.assert_not_called()
            dlg.btn_google.click()
            self.assertEqual(abrir.call_count, 1)
            url = abrir.call_args.args[0].toString()
            q = parse_qs(urlparse(url).query)['q'][0]
            self.assertIn("Guns N' Roses", q); self.assertIn('November Rain', q)
            self.assertNotIn('Possível álbum incorreto', q)
            self.assertIn('Álbum sugerido', dlg.lbl_metadados.text())
            dlg.hide(); dlg.show(); self.app.processEvents()
            self.assertEqual(abrir.call_count, 1)
            dlg.close(); dlg.deleteLater()

    def test_seletor_abre_pasta_e_preserva_arq_existente(self):
        pasta = self.base/'Download de Capas'
        with patch('app.config.PASTA_DOWNLOAD_CAPAS', pasta):
            dlg = DialogoCapas(None, CoverResult())
            with patch.object(QFileDialog, 'getOpenFileName', return_value=('', '')) as escolher:
                dlg._escolher_arquivo()
            self.assertEqual(escolher.call_args.args[2], str(pasta))
            self.assertTrue(pasta.is_dir())
            dlg.close(); dlg.deleteLater()

    def test_colar_salva_na_pasta_sem_sobrescrever_e_exige_confirmacao(self):
        pasta = self.base/'Download de Capas'
        origem = QImage(str(Path(__file__).resolve().parents[1]/'docs'/'tela-pesquisa.png')).copy(0,0,320,320)
        QApplication.clipboard().setImage(origem)
        with patch('app.config.PASTA_DOWNLOAD_CAPAS', pasta):
            dlg = DialogoCapas(None, CoverResult())
            dlg._colar_imagem(); primeiro = Path(dlg.escolhida.caminho)
            antigo = primeiro.read_bytes()
            dlg._colar_imagem(); segundo = Path(dlg.escolhida.caminho)
            self.assertEqual(primeiro.parent, pasta); self.assertNotEqual(primeiro, segundo)
            self.assertEqual(primeiro.read_bytes(), antigo); self.assertTrue(segundo.exists())
            self.assertNotEqual(dlg.result(), dlg.DialogCode.Accepted)
            dlg.close(); dlg.deleteLater()
        QApplication.clipboard().clear()

    def test_webp_e_convertido_para_png_para_gravar_no_mp3(self):
        imagem = QImage(str(Path(__file__).resolve().parents[1]/'docs'/'tela-pesquisa.png')).copy(0,0,320,320)
        caminho = self.base/'capa.webp'
        self.assertTrue(imagem.save(str(caminho), 'WEBP'))
        with patch('app.config.PASTA_DOWNLOAD_CAPAS', self.base/'capas'), \
             patch.object(covers, 'PASTA_CACHE_CAPAS', self.base/'cache'), \
             patch.object(QFileDialog, 'getOpenFileName', return_value=(str(caminho), '')):
            dlg = DialogoCapas(None, CoverResult()); dlg._escolher_arquivo()
            self.assertTrue(dlg.escolhida.ok)
            self.assertEqual(Path(dlg.escolhida.caminho).suffix, '.png')
            self.assertTrue(Path(dlg.escolhida.caminho).read_bytes().startswith(b'\x89PNG'))
            dlg.close(); dlg.deleteLater()

    def test_titulo_do_video_com_artista_repetido_e_ajustado_sem_alterar_origem(self):
        r = TrackResult('id', 'ytdlp', "Guns N' Roses - November Rain (Official Music Video)", "Guns N' Roses")
        item = {'trackName':'November Rain', 'artistName':"Guns N' Roses", 'collectionName':'Use Your Illusion I',
                'trackNumber':10, 'trackCount':16, 'primaryGenreName':'Rock', 'releaseDate':'1991-09-17'}
        confirmado = {'titulo':'November Rain', 'artista':"Guns N' Roses", 'album':'Use Your Illusion I',
                      'ano':1991, 'faixa':10, 'fonte':'musicbrainz'}
        with patch.object(itunes, 'buscar', return_value=[item]), \
             patch('app.metadata.album_original.encontrar', return_value=confirmado):
            meta = pipeline.montar_metadados(r, self.cfg)
        self.assertEqual((meta.titulo,meta.artista,meta.album,meta.faixa),
                         ('November Rain',"Guns N' Roses",'Use Your Illusion I',10))
        self.assertIn('Official Music Video', r.titulo)

    def test_rejeita_tags_de_artista_e_titulo_parecidos(self):
        item = {'trackName':'One More Time', 'artistName':'Queens', 'collectionName':'Outro',
                'trackNumber':99, 'primaryGenreName':'Outro'}
        with patch.object(itunes, 'buscar', return_value=[item]), patch.object(musicbrainz, 'buscar_gravacao', return_value=[]):
            dados = covers.metadados_completos('One','Queen')
        self.assertEqual(dados['titulo'],'One'); self.assertEqual(dados['artista'],'Queen')
        self.assertFalse(dados['album']); self.assertIsNone(dados['faixa'])

    def test_corrigir_album_nao_herda_numero_ano_e_creditos_de_outra_edicao(self):
        from app.models import TrackMeta
        meta = TrackMeta(titulo='November Rain', artista="Guns N' Roses", album='Coletânea',
                         ano=2004, faixa=2, total_faixas=20, disco=1,
                         genero='Pop', artista_album='Vários', data_lancamento='2004-01-01')
        preparacao.aplicar_edicao(meta, {'album':'Use Your Illusion I'})
        self.assertEqual(meta.album, 'Use Your Illusion I')
        self.assertIsNone(meta.ano); self.assertIsNone(meta.faixa); self.assertIsNone(meta.total_faixas)
        self.assertIsNone(meta.disco); self.assertEqual(meta.data_lancamento, '')
        self.assertEqual(meta.artista_album, ''); self.assertEqual(meta.genero, '')
        preparacao.aplicar_edicao(meta, {'album':'Outra edição', 'faixa':'10', 'ano':'1991'})
        self.assertEqual((meta.faixa, meta.ano), (10, 1991))

    @unittest.skipUnless(__import__('shutil').which('ffmpeg'), 'ffmpeg não disponível')
    def test_novo_mp3_nao_herda_disco_de_album_anterior(self):
        import subprocess
        from mutagen.id3 import ID3, TPOS
        from app.sources.local_library import FonteBibliotecaLocal
        from app.models import AudioFormat
        origem = self.base/'origem.mp3'
        subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i',
                        'sine=frequency=440:duration=0.4',str(origem)],check=True)
        tags=ID3(str(origem)); tags.add(TPOS(encoding=3,text='2')); tags.save(str(origem))
        antes=origem.read_bytes()
        self.cfg.dados.update(pasta_saida=str(self.base/'saida'), ia_ativa=False)
        fmt=AudioFormat(codec='mp3',container='mp3',url=str(origem))
        r=TrackResult('local','biblioteca_local','November Rain',"Guns N' Roses",formatos=[fmt])
        with patch.object(covers,'metadados_completos',return_value={}), \
             patch.object(pipeline,'PASTA_TEMP',self.base/'temp'):
            prep=preparacao.preparar_musica(r,self.cfg,edicao={'album':'Use Your Illusion I'},sem_capa=True)
            saida=pipeline.processar_resultado(r,self.cfg,fmt,fonte=FonteBibliotecaLocal(self.cfg),preparacao=prep)
        self.assertTrue(saida['ok'],saida)
        self.assertFalse(ID3(saida['caminho']).getall('TPOS'))
        self.assertEqual(origem.read_bytes(),antes)

    def test_nao_remove_hifen_de_titulo_nem_sobrescreve_edicao(self):
        r = TrackResult('id', 'ytdlp', 'One - Live', 'Queen')
        with patch.object(covers, 'metadados_completos', return_value={}):
            self.assertEqual(pipeline.montar_metadados(r, self.cfg).titulo, 'One - Live')
            editada = preparacao.preparar_musica(r, self.cfg,
                edicao={'titulo':"Queen - Título manual", 'artista':'Queen'}, sem_capa=True)
        self.assertEqual(editada['meta'].titulo, 'Queen - Título manual')

if __name__ == '__main__': unittest.main()

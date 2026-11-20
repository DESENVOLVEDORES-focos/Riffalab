"""Regressões da busca e escolha de capas, sem chamadas externas."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.config import Config
from app.metadata import busca_capas, correspondencia, itunes, provedores
from app.metadata.provedores import Capa


class BuscaCapas(unittest.TestCase):
    def test_config_nova_e_preferencia_anterior(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'config.json'
            self.assertIn('deezer', Config(p).get('fontes_capa'))
            p.write_text(json.dumps({'fontes_capa': ['itunes']}))
            self.assertEqual(Config(p).get('fontes_capa'), ['itunes'])
            p.write_text(json.dumps({'fontes_capa': []}))
            self.assertEqual(Config(p).get('fontes_capa'), [])

    def test_pontuacao_sem_album_e_recusa_diferencas(self):
        bom = {'titulo': 'Bohemian Rhapsody', 'artista': 'Queen', 'album': 'A Night at the Opera'}
        self.assertTrue(correspondencia.pontuar('Bohemian Rhapsody', 'Queen', cand=bom).aprovado)
        self.assertFalse(correspondencia.pontuar('Bohemian Rhapsody', 'Queen', 'Outro Álbum', cand=bom).aprovado)
        self.assertFalse(correspondencia.pontuar('Bohemian Rhapsody', 'Queen', cand=dict(bom, artista='Outro')).aprovado)
        self.assertFalse(correspondencia.pontuar('Bohemian Rhapsody', 'Queen', cand=dict(bom, titulo='')).aprovado)
        self.assertFalse(correspondencia.pontuar('Bohemian Rhapsody', 'Queen', cand=dict(bom, titulo='Bohemian Rhapsody (Live)')).aprovado)
        self.assertFalse(correspondencia.pontuar('Bohemian Rhapsody', cand=bom).aprovado)

    def test_avaliar_compara_album_esperado_e_nao_fabrica_titulo(self):
        class Valida:
            ok = True; largura = 500; altura = 500; hash = 'mesma'; motivo = ''
        contexto = {'titulo': 'Canção', 'artista': 'Pessoa', 'album': 'Álbum certo'}
        with patch.object(busca_capas, '_obter_imagem', return_value=('imagem.jpg', b'imagem')), \
             patch.object(busca_capas.capa_validacao, 'validar', return_value=Valida()):
            c = Capa(url='https://exemplo/a', titulo='Canção', artista='Pessoa', album='Álbum errado', confirmada=True)
            self.assertFalse(busca_capas.avaliar(c, contexto).aprovada)
            c.album = 'Álbum certo'; c.titulo = ''
            self.assertFalse(busca_capas.avaliar(c, contexto).aprovada)
            c.titulo = 'Canção'
            self.assertTrue(busca_capas.avaliar(c, contexto).aprovada)
            outro = Capa(url='https://exemplo/b', titulo=c.titulo, artista=c.artista, album=c.album)
            aprovadas, _ = busca_capas._avaliar_lista([c, outro], contexto, 300, False)
            self.assertEqual(len(aprovadas), 1)

    def test_apple_retorna_alternativas_e_descarta_faixas_diferentes(self):
        def item(album, track='Canção', artista='Pessoa'):
            return {'trackName': track, 'artistName': artista, 'collectionName': album,
                    'artworkUrl100': f'https://example.com/{album}/100x100bb.jpg'}
        with patch.object(itunes, 'buscar', return_value=[item('Um'), item('Dois'), item('Três', 'Outra')]):
            capas = provedores.apple_music('Canção', 'Pessoa')
        self.assertEqual([c.album for c in capas], ['Um', 'Dois'])
        self.assertTrue(all(c.titulo == 'Canção' for c in capas))

    def test_deezer_dados_reais_nao_inventados(self):
        data = {'data': [{'title': 'Canção', 'artist': {'name': 'Pessoa'},
                          'album': {'title': 'Disco', 'cover_xl': 'https://example.com/a'}}]}
        with patch.object(provedores, '_get_json', return_value=data):
            capas = provedores.deezer('Canção', 'Pessoa', ano=2000)
        self.assertEqual(capas[0].titulo, 'Canção')
        self.assertIsNone(capas[0].ano)

    def test_falha_fonte_nao_impede_outra_e_lista_vazia_desliga_tudo(self):
        c = Capa(url='x', titulo='Canção', artista='Pessoa')
        with patch.object(provedores, 'apple_music', side_effect=RuntimeError('falha')), \
             patch.object(provedores, 'deezer', return_value=[c]) as dz, \
             patch.object(busca_capas, '_avaliar_lista', return_value=([], [])):
            busca_capas.coletar('Canção', 'Pessoa', fontes=['itunes', 'deezer'])
            self.assertTrue(dz.called)
            dz.reset_mock()
            busca_capas.coletar('Canção', 'Pessoa', fontes=[])
            dz.assert_not_called()

    def test_nao_usa_capa_de_album_como_reserva_nem_miniatura(self):
        album = Capa(url='https://example.com/album', titulo='Canção', artista='Pessoa', album='Disco')
        with patch.object(provedores, 'apple_music', return_value=[album]), \
             patch.object(provedores, 'miniatura') as miniatura, \
             patch.object(busca_capas, '_obter_imagem') as baixar:
            aprovadas, reprovadas = busca_capas.coletar('Canção', 'Pessoa', 'Disco',
                fontes=['itunes'], thumb_extra='https://example.com/thumb', usar_miniatura=True)
        self.assertEqual(aprovadas, [])
        self.assertEqual(len(reprovadas), 1)
        miniatura.assert_not_called()
        baixar.assert_not_called()
        self.assertIn('single', reprovadas[0].motivo)

    def test_single_e_buscado_sem_restringir_pelo_album(self):
        c = Capa(url='x', titulo='Canção', artista='Pessoa', album='Canção - Single',
                 extra={'tipo_lancamento':'single'})
        a = busca_capas.Avaliacao(capa=c, aprovada=True, score=0.95)
        with patch.object(provedores, 'apple_music', return_value=[c]) as apple, \
             patch.object(busca_capas, '_avaliar_lista', return_value=([a], [])) as avaliar:
            aprovadas, _ = busca_capas.coletar('Canção', 'Pessoa', 'Disco', fontes=['itunes'])
        self.assertEqual(aprovadas, [a])
        apple.assert_called_once_with('Canção', 'Pessoa', '', None)
        self.assertEqual(avaliar.call_args.args[1]['album'], '')


    def test_discogs_nao_simula_confirmacao_de_faixa(self):
        with patch.object(provedores, '_get_json') as get:
            self.assertEqual(provedores.discogs('Canção', 'Pessoa', 'Disco'), [])
            get.assert_not_called()

try:
    from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
    QT_OK = True
except ImportError:
    QT_OK = False


@unittest.skipUnless(QT_OK, 'PySide6 indisponível')
class EscolhaManual(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_imagem_local_mesmo_sem_capa_automatica_e_google(self):
        from app.models import CoverResult
        from app.ui.dialogos import DialogoCapas
        from app.metadata import covers
        from PySide6.QtGui import QDesktopServices
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'capa.png'
            import struct, zlib
            def chunk(tipo, dados):
                return struct.pack('>I', len(dados)) + tipo + dados + struct.pack('>I', zlib.crc32(tipo + dados))
            pixels = b''.join(b'\0' + b''.join(bytes((x % 256, y % 256, (x*y) % 256)) for x in range(400)) for y in range(400))
            path.write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 400, 400, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(pixels)) + chunk(b'IEND', b''))
            dialogo = DialogoCapas(None, CoverResult(observacao='nada'), {'titulo': 'Canção', 'artista': 'Pessoa'})
            self.assertFalse(dialogo.btn_usar.isEnabled())
            with patch.object(QDesktopServices, 'openUrl', return_value=True) as abrir:
                dialogo._pesquisar_google()
                self.assertIn('google.com/search', abrir.call_args.args[0].toString())
            with patch.object(QFileDialog, 'getOpenFileName', return_value=(str(path), '')), \
                 patch.object(covers, 'PASTA_CACHE_CAPAS', Path(d) / 'cache'):
                dialogo._escolher_arquivo()
            self.assertEqual(dialogo.escolhida.fonte, 'arquivo local')
            self.assertTrue(Path(dialogo.escolhida.caminho).is_file())
            self.assertTrue(dialogo.btn_usar.isEnabled())
            self.assertIn('direitos', dialogo.lbl_motivo.text())
            dialogo._usar()
            self.assertFalse(dialogo.recusou)
            dialogo.close()

    def test_arquivo_invalido_nao_e_aceito(self):
        from app.models import CoverResult
        from app.ui.dialogos import DialogoCapas
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'falso.png'; p.write_text('não é imagem')
            dialogo = DialogoCapas(None, CoverResult(), {})
            with patch.object(QFileDialog, 'getOpenFileName', return_value=(str(p), '')), \
                 patch.object(QMessageBox, 'warning') as aviso:
                dialogo._escolher_arquivo()
            aviso.assert_called_once()
            self.assertIsNone(dialogo.escolhida)
            dialogo.close()

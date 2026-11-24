"""Revisão por identidade e catálogo, com editor e respostas assíncronas."""
import io
import json
import os
import tempfile
import threading
import time
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication, QDialog
from app.config import Config
from app.db import Banco
from app.downloader import GerenciadorFila
from app.ia import identificador, revisao
from app.models import TrackResult, TrackMeta, Identificacao, CoverResult
from app.ui.pages import downloads_page


def ident(**kwargs):
    return Identificacao(ok=True, confianca=.99, titulo=kwargs.pop('titulo', 'Canção'),
                         artista=kwargs.pop('artista', 'Pessoa'), **kwargs)


def catalogo(**kwargs):
    return dict({'titulo': 'Canção', 'artista': 'Pessoa', 'album': 'Disco', 'ano': 2001,
                 'faixa': 3, 'artista_album': 'Pessoa', 'fonte': 'musicbrainz'}, **kwargs)


class ConsultaRevisao(unittest.TestCase):
    def setUp(self):
        self.r = TrackResult('id', 'ytdlp', 'Chicago', 'Michael Jackson')
        self.rev = {'dados_atuais': {'titulo': 'Michael Jackson - Chicago (4K)',
                                     'artista': 'Michael Jackson', 'album': 'Antigo'},
                    'observacao': 'confira o álbum'}

    def test_usa_titulo_e_artista_juntos_sem_confiar_na_ia(self):
        mb = {'titulo':'Chicago', 'artista':'Michael Jackson', 'album':'Xscape', 'ano':2014}
        with patch.object(identificador, 'identificar', return_value=ident(titulo='Chicago', artista='Outra Pessoa')) as ia, \
             patch.object(revisao.album_original, 'encontrar', return_value=mb) as busca, \
             patch.object(revisao.itunes, 'melhor_faixa') as it:
            res = revisao.reavaliar(self.r, object(), self.rev)
        busca.assert_called_once_with('Chicago', 'Michael Jackson'); it.assert_not_called()
        self.assertEqual(res['catalogo']['album'], 'Xscape')
        self.assertEqual(ia.call_args.kwargs['revisao']['dados_atuais']['artista'], 'Michael Jackson')
        self.assertEqual(ia.call_args.kwargs['revisao']['dados_atuais']['album'], 'Antigo')
        self.assertEqual(ia.call_args.kwargs['revisao']['observacao'], 'confira o álbum')

    def test_recusa_homonimos_e_fallback_validado(self):
        mb = {'titulo':'Chicago', 'artista':'Sufjan Stevens', 'album':'Illinois'}
        it = {'titulo':'Chicago', 'artista':'Michael Jackson', 'album':'Xscape', 'ano':2014, 'faixa':2}
        with patch.object(revisao.album_original, 'encontrar', return_value=mb), \
             patch.object(revisao.itunes, 'melhor_faixa', return_value=it), \
             patch.object(identificador, 'identificar', return_value=ident()):
            res = revisao.reavaliar(self.r, object(), self.rev)
        self.assertEqual((res['catalogo']['fonte'], res['catalogo']['album']), ('itunes', 'Xscape'))

    def test_artist_names_approximate_and_versions_rejected(self):
        for candidate in [
            {'titulo':'Chicago', 'artista':'Michael Jacksen', 'album':'Errado'},
            {'titulo':'Chicago (Original Version)', 'artista':'Michael Jackson', 'album':'Errado'},
            {'titulo':'Chicago (Live)', 'artista':'Michael Jackson', 'album':'Errado'},
        ]:
            with self.subTest(candidate=candidate), \
                 patch.object(revisao.album_original, 'encontrar', return_value=candidate), \
                 patch.object(revisao.itunes, 'melhor_faixa', return_value=candidate), \
                 patch.object(identificador, 'identificar', return_value=ident()):
                self.assertEqual(revisao.reavaliar(self.r, object(), self.rev)['catalogo'], {})

    def test_syd_matters_e_variacao_de_titulo(self):
        self.rev['dados_atuais'].update(titulo='Obstacles', artista='Syd Matters')
        dado = {'titulo':'Obstacles', 'artista':'Syd Matters',
                'album':'Someday We Will Foresee Obstacles', 'ano':2005}
        with patch.object(revisao.album_original, 'encontrar', return_value=dado) as mb, \
             patch.object(identificador, 'identificar', return_value=ident()):
            res = revisao.reavaliar(self.r, object(), self.rev)
        mb.assert_called_once_with('Obstacles', 'Syd Matters')
        self.assertEqual(res['catalogo']['album'], dado['album'])

    def test_respostas_musicbrainz_realistas_do_inicio_ao_fim(self):
        from app.metadata import musicbrainz
        exemplos = [('Chicago', 'Michael Jackson', 'Xscape', 2014),
                    ('Obstacles', 'Syd Matters', 'Someday We Will Foresee Obstacles', 2005)]
        for titulo, artista, album, ano in exemplos:
            with self.subTest(titulo=titulo):
                rel = {'id':'release-a', 'title':album, 'date':f'{ano}-05-09', 'status':'Official',
                       'release-group':{'id':'grupo-a','primary-type':'Album'}}
                resposta = {'recordings':[{'title':titulo,'score':100,
                            'artist-credit':[{'name':artista}], 'releases':[rel]}]}
                grupo = {'title':album,'primary-type':'Album','secondary-types':[],
                         'first-release-date':f'{ano}-05-09'}
                detalhes = {'title':album,'date':f'{ano}-05-09',
                            'artist-credit':[{'name':artista}],
                            'media':[{'position':1,'track-count':8,
                                      'tracks':[{'title':titulo,'number':'2'}]}]}
                def get(url):
                    if '/recording/' in url: return resposta
                    if '/release-group/' in url: return grupo
                    return detalhes
                self.rev['dados_atuais'].update(titulo=titulo, artista=artista)
                musicbrainz.detalhes_grupo.cache_clear()
                with patch.object(musicbrainz, '_get', side_effect=get), \
                     patch.object(identificador, 'identificar', return_value=ident(titulo=titulo, artista=artista)):
                    resultado = revisao.reavaliar(self.r, object(), self.rev)
                self.assertEqual((resultado['catalogo']['album'], resultado['catalogo']['ano'],
                                  resultado['catalogo']['faixa']), (album, ano, 2))
        musicbrainz.detalhes_grupo.cache_clear()

    def test_falha_de_catalogos_preserva_vazio_e_nome_do_canal(self):
        self.rev['dados_atuais'].update(titulo='Michael Jackson - Chicago', artista='Canal Music')
        with patch.object(revisao.album_original, 'encontrar', side_effect=TimeoutError), \
             patch.object(revisao.itunes, 'melhor_faixa', return_value=None), \
             patch.object(identificador, 'identificar', return_value=ident()):
            res = revisao.reavaliar(self.r, object(), self.rev)
        self.assertEqual(res['catalogo'], {})
        self.assertEqual(res['consulta']['artista'], 'Canal Music')
        self.assertEqual(res['consulta']['titulo'], 'Michael Jackson - Chicago')


class RevisaoEditor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.cfg = Config(Path(self.tmp.name)/'config.json'); self.cfg.dados['ia_ativa'] = True
        self.banco = Banco(Path(self.tmp.name)/'banco.db')
        self.fila = GerenciadorFila(self.cfg, self.banco)
        self.page = downloads_page.DownloadsPage(self.cfg, self.fila)
        self.r = TrackResult('id', 'ytdlp', 'Canção (4K)', 'Pessoa')
        self.page.adicionar_selecao({'resultado':self.r}); self.linha = self.page.selecoes[0]
        self.dlg = downloads_page.DialogoEditarDados(self.linha, self.page)
        self.chamadas = []
        self.mock = patch.object(downloads_page.EXECUTOR_GLOBAL, 'rodar',
                                 side_effect=lambda *a, **kw:self.chamadas.append((a,kw)))
        self.mock.start(); self.addCleanup(self.mock.stop)

    def tearDown(self):
        self.dlg.close(); self.page.close(); self.fila.encerrar()
        self.dlg.deleteLater(); self.page.deleteLater(); self.app.processEvents(); self.banco.fechar()

    def pedir(self):
        self.dlg.btn_rever_ia.click(); return self.chamadas[-1][1]

    def responder(self, callback, ia=None, cat=None):
        callback['ao_resultado']({'ident': ia or ident(), 'catalogo': cat or {},
                                  'consulta': {'titulo':'Canção', 'artista':'Pessoa'}})

    def test_catalogo_nao_ia_define_album_e_artista(self):
        cb = self.pedir()
        self.assertEqual(cb['revisao']['dados_atuais']['titulo'], 'Canção (4K)')
        self.responder(cb, ident(titulo='Canção', artista='Outro', album='Inventado', ano=1999), catalogo())
        self.assertEqual(self.dlg.campos['artista'].text(), 'Pessoa')
        self.assertEqual(self.dlg.campos['album'].text(), 'Disco')
        self.assertEqual(self.dlg.campos['ano'].text(), '2001')
        self.assertIn('MusicBrainz', self.dlg.lbl_revisao_ia.text())
        self.assertIn('IA não confirmou', self.dlg.lbl_revisao_ia.text())
        self.assertNotIn('edicao', self.linha.pedido)
        self.dlg.reject(); self.assertNotIn('edicao', self.linha.pedido)

    def test_catalogo_ausente_preserva_tudo_mesmo_ia_confiante(self):
        self.dlg.campos['album'].setText('Meu álbum')
        cb = self.pedir(); self.responder(cb, ident(album='Inventado'), {})
        self.assertEqual(self.dlg.campos['album'].text(), 'Meu álbum')
        self.assertEqual(self.dlg.campos['titulo'].text(), 'Canção (4K)')
        self.assertIn('indisponíveis', self.dlg.lbl_revisao_ia.text())

    def test_album_incompleto_nao_mistura_e_nao_apaga(self):
        self.dlg.campos['album'].setText('Antigo'); self.dlg.campos['ano'].setText('1990')
        self.dlg.campos['faixa'].setText('8')
        cat = catalogo(); cat.pop('faixa')
        self.responder(self.pedir(), cat=cat)
        self.assertEqual([self.dlg.campos[k].text() for k in ('album','ano','faixa')], ['Antigo','1990','8'])
        self.assertIn('faltam dados', self.dlg.lbl_revisao_ia.text())

    def test_campos_alterados_durante_consulta_sao_preservados(self):
        cb = self.pedir(); self.dlg.campos['album'].setText('Manual')
        self.responder(cb, cat=catalogo())
        self.assertEqual(self.dlg.campos['album'].text(), 'Manual')
        self.assertEqual(self.dlg.campos['ano'].text(), '')
        self.assertIn('preservados', self.dlg.lbl_revisao_ia.text())
        cb = self.pedir(); self.dlg.campos['artista'].setText('Alterado')
        self.responder(cb, cat=catalogo()); self.assertIn('Nenhuma sugestão', self.dlg.lbl_revisao_ia.text())

    def test_cancelamento_e_erro(self):
        cb = self.pedir(); cb['ao_erro']('sem rede')
        self.assertIn('sem rede', self.dlg.lbl_revisao_ia.text())
        cb = self.pedir(); self.dlg.reject(); self.responder(cb, cat=catalogo())
        self.assertEqual(self.dlg.campos['titulo'].text(), 'Canção (4K)')

    def test_salvar_resultado_persiste_na_preparacao(self):
        self.responder(self.pedir(), cat=catalogo())
        self.dlg.exec = lambda: QDialog.Accepted
        with patch.object(downloads_page, 'DialogoEditarDados', return_value=self.dlg):
            self.page._editar_dados(self.linha)
        ed = self.linha.pedido['edicao']; self.assertEqual((ed['album'], ed['faixa']), ('Disco','3'))
        from app import preparacao, pipeline
        with patch.object(preparacao.identificador, 'identificar', return_value=Identificacao(ok=False)), \
             patch.object(pipeline.covers, 'metadados_completos', return_value={}):
            dados = preparacao.preparar_musica(self.r, self.cfg, edicao=ed, sem_capa=True)
        self.assertEqual((dados['meta'].album, dados['meta'].faixa), ('Disco',3))

    def test_assincrono_nao_bloqueia_editor(self):
        from app.workers import EXECUTOR_GLOBAL
        self.mock.stop(); entrou = threading.Event(); liberar = threading.Event()
        def lenta(*args, **kwargs):
            entrou.set(); liberar.wait(3); return catalogo()
        try:
            with patch.object(revisao.album_original, 'encontrar', side_effect=lenta), \
                 patch.object(identificador, 'identificar', return_value=ident()):
                self.dlg.btn_rever_ia.click(); self.assertTrue(entrou.wait(1))
                self.assertFalse(self.dlg.btn_rever_ia.isEnabled())
                self.dlg.campos['genero'].setText('Manual'); liberar.set()
                limite = time.monotonic()+3
                while not self.dlg.btn_rever_ia.isEnabled() and time.monotonic()<limite:
                    self.app.processEvents(); time.sleep(.01)
                self.assertTrue(self.dlg.btn_rever_ia.isEnabled())
                self.assertEqual(self.dlg.campos['album'].text(), 'Disco')
                self.assertEqual(self.dlg.campos['genero'].text(), 'Manual')
        finally:
            liberar.set(); EXECUTOR_GLOBAL.aguardar(5000)

    def test_botao_recupera_http_400_com_catalogo(self):
        from app import seguranca
        class Resp:
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def read(self):
                dados = {'identificado':True,'confianca':.95,'titulo':'Canção','artista':'Pessoa',
                         'album':'Inventado','ano':1999,'faixa':9,'artistas_participantes':[], 'campos_incertos':[]}
                return json.dumps({'model':'teste','choices':[{'finish_reason':'stop',
                                  'message':{'content':json.dumps(dados)}}]}).encode()
        def err():
            return urllib.error.HTTPError('https://api.groq.com',400,'erro',{},
                io.BytesIO(json.dumps({'error':{'message':'Failed to generate JSON','code':'json_validate_failed'}}).encode()))
        def executar(fn,*args,**kwargs):
            kwargs['ao_resultado'](fn(*args,revisao=kwargs['revisao']))
        self.mock.stop()
        with patch.object(downloads_page.EXECUTOR_GLOBAL,'rodar',side_effect=executar), \
             patch.object(seguranca,'existe',return_value=True), patch.object(seguranca,'ler',return_value='ficticia'), \
             patch.object(revisao.album_original, 'encontrar',return_value=catalogo()), \
             patch('urllib.request.urlopen',side_effect=[err(),err(),Resp()]) as chamadas:
            self.dlg.btn_rever_ia.click()
        self.assertEqual(chamadas.call_count,3)
        self.assertEqual(self.dlg.campos['album'].text(),'Disco')
        self.assertEqual(self.dlg.campos['faixa'].text(),'3')

if __name__ == '__main__': unittest.main()

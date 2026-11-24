"""Nova consulta à IA: fluxo revisável, respostas tardias e preservação dos dados."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox
from app.config import Config
from app.db import Banco
from app.downloader import GerenciadorFila
from app.ia import identificador, cliente_groq
from app.models import TrackResult, TrackMeta, Identificacao, CoverResult
from app.ui.pages import downloads_page


class RevisaoIA(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.cfg=Config(Path(self.tmp.name)/'config.json'); self.cfg.dados['ia_ativa']=True
        self.banco=Banco(Path(self.tmp.name)/'banco.db')
        self.fila=GerenciadorFila(self.cfg,self.banco)
        self.page=downloads_page.DownloadsPage(self.cfg,self.fila)
        self.r=TrackResult('id','ytdlp','Canção (4K)', 'Pessoa',pagina_url='https://example.com/video')
        self.page.adicionar_selecao({'resultado':self.r})
        self.linha=self.page.selecoes[0]
        self.dlg=downloads_page.DialogoEditarDados(self.linha,self.page)
        self.chamadas=[]
        self.mock=patch.object(downloads_page.EXECUTOR_GLOBAL,'rodar', side_effect=lambda *a,**kw:self.chamadas.append((a,kw)))
        self.mock.start(); self.addCleanup(self.mock.stop)

    def tearDown(self):
        self.dlg.close(); self.page.close(); self.fila.encerrar()
        self.dlg.deleteLater(); self.page.deleteLater()
        self.app.processEvents()
        self.banco.fechar()

    def pedir(self):
        self.dlg.btn_rever_ia.click()
        return self.chamadas[-1][1]

    def test_consulta_nova_com_contexto_e_correcoes_aguardam_salvar(self):
        self.dlg.campo_pedido_ia.setText('o álbum anterior estava errado')
        callback=self.pedir()
        self.assertFalse(self.dlg.btn_rever_ia.isEnabled())
        self.assertEqual(self.chamadas[0][0][1],self.r)
        self.assertEqual(callback['revisao']['dados_atuais']['titulo'],'Canção (4K)')
        self.assertEqual(callback['revisao']['observacao'],'o álbum anterior estava errado')
        ident=Identificacao(ok=True,confianca=.95,titulo='Canção (Remastered 2022)', artista='Pessoa',
              artistas_participantes=['Convidada'], album='Appetite for Destruction', genero='Rock',
              ano=1987, faixa=5, artista_album='Pessoa')
        callback['ao_resultado'](ident)
        self.assertEqual(self.dlg.campos['titulo'].text(),'Canção')
        self.assertEqual(self.dlg.campos['artistas_participantes'].text(),'Convidada')
        self.assertEqual(self.dlg.campos['album'].text(),'Appetite for Destruction')
        self.assertEqual(self.dlg.campos['ano'].text(),'1987')
        self.assertIn('não foi confirmado',self.dlg.lbl_revisao_ia.text())
        self.assertNotIn('edicao',self.linha.pedido)
        self.dlg.reject()
        self.assertIsNone(self.linha.preparacao)
        self.assertNotIn('edicao',self.linha.pedido)

    def test_salvar_sugestoes_sobrevive_preparacao_sem_reescrever_origem(self):
        callback=self.pedir()
        callback['ao_resultado'](Identificacao(ok=True,confianca=.95,titulo='Canção',artista='Pessoa',
            album='Disco',genero='Rock',ano=2001,faixa=3,artista_album='Pessoa'))
        self.dlg.exec=lambda: QDialog.Accepted
        with patch.object(downloads_page,'DialogoEditarDados',return_value=self.dlg):
            self.page._editar_dados(self.linha)
        ed=self.linha.pedido['edicao']
        self.assertEqual((ed['album'],ed['faixa'],ed['genero']),('Disco','3','Rock'))
        from app import preparacao, pipeline
        with patch.object(preparacao.identificador,'identificar',return_value=Identificacao(ok=False)), \
             patch.object(pipeline.covers,'metadados_completos',return_value={}):
            dados=preparacao.preparar_musica(self.r,self.cfg,edicao=ed,sem_capa=True)
        self.assertEqual((dados['meta'].titulo,dados['meta'].album,dados['meta'].faixa),('Canção','Disco',3))
        self.assertEqual(self.r.titulo,'Canção (4K)')

    def test_album_corrigido_sem_ano_nao_mistura_dados_da_edicao_antiga(self):
        self.linha.definir_preparacao({'meta':TrackMeta(titulo='Canção',artista='Pessoa',album='Antigo',
            ano=2000,faixa=7,genero='Rock',artista_album='Banda'), 'capa':CoverResult(), 'ident':None})
        self.dlg.close(); self.dlg.deleteLater()
        self.dlg=downloads_page.DialogoEditarDados(self.linha,self.page)
        callback=self.pedir()
        callback['ao_resultado'](Identificacao(ok=True,confianca=.95,titulo='Canção',artista='Pessoa',
                                               album='Novo',campos_incertos=['ano','faixa','genero']))
        self.assertEqual(self.dlg.campos['album'].text(),'Novo')
        for k in ('ano','faixa','genero','artista_album'): self.assertEqual(self.dlg.campos[k].text(),'')
        self.dlg.exec=lambda: QDialog.Accepted
        with patch.object(downloads_page,'DialogoEditarDados',return_value=self.dlg):
            self.page._editar_dados(self.linha)
        self.assertIsNone(self.linha.preparacao)
        self.assertEqual(self.linha.pedido['edicao']['ano'],'')
        self.assertEqual(self.linha.pedido['edicao']['faixa'],'')

    def test_reavaliacao_de_album_conserva_valores_reafirmados_pela_ia(self):
        self.linha.definir_preparacao({'meta':TrackMeta(titulo='Canção',artista='Pessoa',album='Antigo',
            ano=2000,faixa=7,genero='Rock',artista_album='Pessoa'), 'capa':CoverResult(), 'ident':None})
        self.dlg.close(); self.dlg.deleteLater()
        self.dlg=downloads_page.DialogoEditarDados(self.linha,self.page)
        callback=self.pedir()
        callback['ao_resultado'](Identificacao(ok=True,confianca=.95,titulo='Canção',artista='Pessoa',
            album='Novo',ano=2000,faixa=7,genero='Rock',artista_album='Pessoa'))
        self.dlg.exec=lambda: QDialog.Accepted
        with patch.object(downloads_page,'DialogoEditarDados',return_value=self.dlg):
            self.page._editar_dados(self.linha)
        ed=self.linha.pedido['edicao']
        self.assertEqual((ed['album'],ed['ano'],ed['faixa'],ed['genero']),('Novo','2000','7','Rock'))

    def test_album_editado_durante_pedido_nao_recebe_faixa_de_outra_edicao(self):
        callback=self.pedir(); self.dlg.campos['album'].setText('Meu álbum')
        callback['ao_resultado'](Identificacao(ok=True,confianca=.99,titulo='Canção',artista='Pessoa',
                                               album='Outro',ano=2000,faixa=7,artista_album='Outro'))
        self.assertEqual(self.dlg.campos['album'].text(),'Meu álbum')
        self.assertEqual(self.dlg.campos['faixa'].text(),'')
        self.assertEqual(self.dlg.campos['ano'].text(),'')
        self.assertEqual(self.dlg.campos['artista_album'].text(),'')

    def test_campo_manual_durante_consulta_e_preservado(self):
        callback=self.pedir()
        self.dlg.campos['genero'].setText('Samba')
        callback['ao_resultado'](Identificacao(ok=True,confianca=.99,titulo='Canção',artista='Pessoa',genero='Rock'))
        self.assertEqual(self.dlg.campos['genero'].text(),'Samba')
        self.assertIn('preservados',self.dlg.lbl_revisao_ia.text())

    def test_mudar_artista_durante_consulta_descarta_sugestao(self):
        callback=self.pedir(); self.dlg.campos['artista'].setText('Correção manual')
        callback['ao_resultado'](Identificacao(ok=True,confianca=.99,titulo='Outro',artista='IA',album='Outro'))
        self.assertEqual(self.dlg.campos['artista'].text(),'Correção manual')
        self.assertEqual(self.dlg.campos['titulo'].text(),'Canção (4K)')
        self.assertIn('Nenhuma sugestão',self.dlg.lbl_revisao_ia.text())

    def test_falhas_e_baixa_confianca_nao_apagam_campos_e_aceitam_nova_tentativa(self):
        self.dlg.campos['album'].setText('Meu álbum')
        callback=self.pedir(); callback['ao_resultado'](Identificacao(ok=False,erro='IA desligada'))
        self.assertEqual(self.dlg.campos['album'].text(),'Meu álbum')
        self.assertIn('IA desligada',self.dlg.lbl_revisao_ia.text()); self.assertTrue(self.dlg.btn_rever_ia.isEnabled())
        callback=self.pedir(); callback['ao_resultado'](Identificacao(ok=True,confianca=.2,titulo='Outra',artista='Outro'))
        self.assertEqual(self.dlg.campos['album'].text(),'Meu álbum')
        self.assertIn('baixa confiança',self.dlg.lbl_revisao_ia.text())
        callback=self.pedir(); callback['ao_erro']('sem rede')
        self.assertEqual(self.dlg.campos['album'].text(),'Meu álbum')
        self.assertIn('sem rede',self.dlg.lbl_revisao_ia.text())

    def test_cancelar_durante_pedido_ignora_resposta_tardia(self):
        callback=self.pedir(); self.dlg.reject()
        callback['ao_resultado'](Identificacao(ok=True,confianca=.99,titulo='Outro',artista='Outro'))
        self.assertEqual(self.dlg.campos['titulo'].text(),'Canção (4K)')
        self.assertNotIn('edicao',self.linha.pedido)

    def test_consulta_assincrona_real_nao_bloqueia_editor(self):
        import threading, time
        from app.workers import EXECUTOR_GLOBAL
        self.mock.stop()
        entrou=threading.Event(); liberar=threading.Event()
        def lenta(*args, **kwargs):
            entrou.set()
            if not liberar.wait(3): raise RuntimeError('timeout no teste')
            return Identificacao(ok=True,confianca=.95,titulo='Canção',artista='Pessoa',album='Disco')
        try:
            self.dlg.show()
            with patch.object(identificador,'identificar',side_effect=lenta):
                self.dlg.btn_rever_ia.click()
                self.assertTrue(entrou.wait(1))
                self.assertFalse(self.dlg.btn_rever_ia.isEnabled())
                self.dlg.campos['genero'].setText('Edição manual')
                liberar.set()
                limite=time.monotonic()+3
                while not self.dlg.btn_rever_ia.isEnabled() and time.monotonic()<limite:
                    self.app.processEvents(); time.sleep(.01)
                self.assertTrue(self.dlg.btn_rever_ia.isEnabled())
                self.assertEqual(self.dlg.campos['album'].text(),'Disco')
                self.assertEqual(self.dlg.campos['genero'].text(),'Edição manual')
        finally:
            liberar.set(); EXECUTOR_GLOBAL.aguardar(5000)

    def test_botao_real_recupera_400_e_atualiza_editor(self):
        import json, io, urllib.error
        from app import seguranca
        class Resp:
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def read(self):
                dados={'identificado':True,'confianca':.95,'titulo':'Canção',
                       'artista':'Pessoa','album':'Disco','genero':'Rock',
                       'ano':2001,'faixa':3,'artista_album':'Pessoa',
                       'artistas_participantes':[],'campos_incertos':[]}
                return json.dumps({'model':'teste','choices':[{'finish_reason':'stop',
                                  'message':{'content':json.dumps(dados)}}]}).encode()
        def err():
            dados={'error':{'message':'Failed to generate JSON','code':'json_validate_failed'}}
            return urllib.error.HTTPError('https://api.groq.com',400,'erro',{},io.BytesIO(json.dumps(dados).encode()))
        def executar(fn,*args,**kwargs):
            dados=fn(*args,revisao=kwargs['revisao'])
            kwargs['ao_resultado'](dados)
        self.mock.stop()
        with patch.object(downloads_page.EXECUTOR_GLOBAL,'rodar',side_effect=executar), \
             patch.object(seguranca,'existe',return_value=True), \
             patch.object(seguranca,'ler',return_value='chave-ficticia'), \
             patch('urllib.request.urlopen',side_effect=[err(),err(),Resp()]) as chamadas:
            self.dlg.btn_rever_ia.click()
        self.assertEqual(chamadas.call_count,3)
        self.assertEqual(self.dlg.campos['album'].text(),'Disco')
        self.assertEqual(self.dlg.campos['faixa'].text(),'3')
        self.assertIn('Sugestão recebida',self.dlg.lbl_revisao_ia.text())
        self.assertIsNone(self.linha.preparacao)

    def test_composicao_do_pedido_torna_dados_do_usuario_contexto_nao_verdade(self):
        revisao={'dados_atuais':{'album':'errado'},'observacao':'faixa errada'}
        bruto={'identificado':True,'confianca':.9,'titulo':'Canção','artista':'Pessoa'}
        with patch.object(cliente_groq,'disponivel',return_value=(True,'')), \
             patch.object(cliente_groq,'completar_json',return_value=(bruto,'modelo')) as completar:
            ident=identificador.identificar(self.r,self.cfg,revisao=revisao)
        self.assertTrue(ident.ok)
        pedido=completar.call_args.args[2]
        self.assertIn('podem estar errados',pedido); self.assertIn('faixa errada',pedido)
        self.assertIn('Canção (4K)',pedido); self.assertIn('não copie valores sem certeza',pedido)
        self.assertNotIn('api_key',pedido)

if __name__ == '__main__': unittest.main()

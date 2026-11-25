"""Capas escolhidas sobrevivem à edição e à revisão/reinicialização."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QDialog
from app import estado_musicas
from app.config import Config
from app.db import Banco
from app.downloader import GerenciadorFila
from app.models import CoverResult, Identificacao, TrackMeta, TrackResult
from app.ui.pages import downloads_page
from app.ui.dialogos import DialogoCapas


class CapaPreservada(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.pasta = Path(self.tmp.name)
        self.cfg = Config(self.pasta / 'config.json')
        self.banco = Banco(self.pasta / 'banco.db')
        self.fila = GerenciadorFila(self.cfg, self.banco)
        self.page = downloads_page.DownloadsPage(self.cfg, self.fila)
        self.r = TrackResult('id', 'ytdlp', 'Música', 'Pessoa')
        self.page.adicionar_selecao({'resultado': self.r}); self.linha = self.page.selecoes[0]
        arquivo = self.pasta / 'capa.png'
        imagem = QImage(320, 320, QImage.Format_RGB32); imagem.fill(0xff226699)
        self.assertTrue(imagem.save(str(arquivo)))
        self.capa = CoverResult(caminho=str(arquivo), fonte='imagem colada', largura=320, altura=320)
        self.meta = TrackMeta(titulo='Música', artista='Pessoa', album='Antigo', ano=1999,
                              faixa=8, genero='Rock', artista_album='Pessoa', isrc='ANTIGO')
        self.prep = {'meta':self.meta, 'ident':Identificacao(ok=True, titulo='Música', artista='Pessoa'),
                     'capa':self.capa, 'consulta_capa': {'titulo':'Música', 'artista':'Pessoa'}}
        self.linha.definir_preparacao(self.prep)

    def tearDown(self):
        self.page.close(); self.fila.encerrar(); self.page.deleteLater()
        self.app.processEvents(); self.banco.fechar()

    def editar(self, alteracoes, aceitar=True):
        dialogo = downloads_page.DialogoEditarDados(self.linha, self.page)
        for chave, valor in alteracoes.items(): dialogo.campos[chave].setText(valor)
        dialogo.exec = lambda: QDialog.Accepted if aceitar else QDialog.Rejected
        with patch.object(downloads_page, 'DialogoEditarDados', return_value=dialogo):
            self.page._editar_dados(self.linha)
        dialogo.close(); dialogo.deleteLater()

    def test_editar_campos_sem_mudar_identidade_nao_perde_capa(self):
        self.editar({'genero':'Jazz','faixa':'3'})
        self.assertIs(self.linha.preparacao, self.prep)
        self.assertIs(self.linha.preparacao['capa'], self.capa)
        self.assertEqual(self.meta.genero, 'Jazz')
        self.assertFalse(self.linha.preparacao.get('revisao_pendente'))
        self.assertTrue(self.page.btn_baixar.isEnabled())

    def test_cancelar_editor_nao_altera_capa_ou_dados(self):
        self.editar({'album':'Outro'}, aceitar=False)
        self.assertIs(self.linha.preparacao, self.prep)
        self.assertEqual(self.meta.album, 'Antigo')
        self.assertIs(self.linha.preparacao['capa'], self.capa)

    def test_editar_album_preserva_capa_e_restauracao_pede_confirmacao(self):
        self.editar({'album':'Novo'})
        prep = self.linha.preparacao
        self.assertIs(prep['capa'], self.capa)
        self.assertEqual(prep['meta'].album, 'Novo')
        self.assertIsNone(prep['meta'].faixa); self.assertIsNone(prep['meta'].ano)
        self.assertEqual(prep['meta'].isrc, '')
        self.assertIsNone(prep['ident'])
        self.assertTrue(prep['revisao_pendente'])
        self.assertFalse(self.page.btn_baixar.isEnabled())
        self.assertIn('revise', self.linha.detalhes.text())
        self.assertEqual(self.linha.btn_capa.text(), 'Revisar capa')
        _, _, restaurada = estado_musicas.desserializar_selecao(
            self.banco.ler_estado('downloads_selecionados')[-1])
        self.assertEqual(restaurada['capa'].caminho, self.capa.caminho)
        self.assertTrue(restaurada['revisao_pendente'])
        self.linha.definir_preparacao(restaurada)
        self.assertFalse(self.page.btn_baixar.isEnabled())
        # Até chamadas diretas são bloqueadas, mesmo com o botão desativado.
        with patch.object(self.fila, 'adicionar') as adicionar:
            self.page._baixar_selecionadas(); adicionar.assert_not_called()

    def test_titulo_e_artista_tambem_guardam_a_imagem(self):
        self.editar({'titulo':'Outra música', 'artista':'Outra pessoa', 'faixa':'2'})
        prep = self.linha.preparacao
        self.assertEqual((prep['meta'].titulo, prep['meta'].artista, prep['meta'].faixa),
                         ('Outra música', 'Outra pessoa', 2))
        self.assertIs(prep['capa'], self.capa)
        self.assertTrue(prep['revisao_pendente'])

    def test_dialogo_mostra_capa_anterior_enquanto_identificacao_acontece(self):
        self.editar({'album':'Novo'})
        dialogo = DialogoCapas(self.page, self.linha.preparacao['capa'],
                               self.page._musica_dialogo(self.linha.preparacao))
        self.assertIs(dialogo.escolhida, self.capa)
        self.assertFalse(dialogo.lbl_imagem.pixmap().isNull())
        dialogo.definir_pendente(True)
        self.assertFalse(dialogo.btn_usar.isEnabled())
        dialogo.definir_pendente(False)
        self.assertTrue(dialogo.btn_usar.isEnabled())
        dialogo.close(); dialogo.deleteLater()

    def test_revisar_permite_confirmar_a_mesma_capa_sem_recolar(self):
        self.editar({'album':'Novo'})
        visto = {}
        class Janela:
            recusou = False
            def __init__(self, pai, capa, musica):
                self.escolhida = capa; visto['capa'] = capa; visto['musica'] = musica
            def definir_pendente(self, pendente): visto['pendente'] = pendente
            def show(self): pass
            def atualizar_musica(self, dados): visto['atualizado'] = dados
            def exec(self): return QDialog.Accepted
            def close(self): pass
        nova = {'meta':TrackMeta(titulo='Música', artista='Pessoa', album='Novo', faixa=2),
                'capa':CoverResult(), 'ident':None, 'consulta_capa': {'titulo':'Música','artista':'Pessoa'}}
        def rodar(fn,*args,**kwargs):
            visto['edicao'] = kwargs['edicao']; kwargs['ao_resultado'](nova)
        with patch.object(downloads_page, 'DialogoCapas', Janela), \
             patch.object(downloads_page.EXECUTOR_GLOBAL, 'rodar', side_effect=rodar):
            self.page._preparar_uma(self.linha)
        self.assertIs(visto['capa'], self.capa)
        self.assertEqual(visto['musica']['album'], 'Novo')
        self.assertEqual(visto['edicao']['album'], 'Novo')
        self.assertTrue(visto['pendente'])
        self.assertIs(self.linha.preparacao['capa'], self.capa)
        self.assertEqual(self.linha.preparacao['meta'].faixa, 2)
        self.assertFalse(self.linha.preparacao['revisao_pendente'])
        self.assertTrue(self.page.btn_baixar.isEnabled())

    def test_dialogo_real_reconfirma_capa_e_fila_recebe_mesmo_arquivo(self):
        from PySide6.QtCore import QTimer
        self.editar({'album':'Novo'})
        visto = {}
        class JanelaReal(DialogoCapas):
            def show(self):
                super().show()
                visto['caminho'] = self.escolhida.caminho
                visto['aguardando'] = not self.btn_usar.isEnabled()
                QTimer.singleShot(0, self._usar)
        nova = {'meta':TrackMeta(titulo='Música', artista='Pessoa', album='Novo'),
                'capa':CoverResult(), 'ident':None, 'consulta_capa': {'titulo':'Música','artista':'Pessoa'}}
        def rodar(fn, *args, **kwargs): kwargs['ao_resultado'](nova)
        with patch.object(downloads_page, 'DialogoCapas', JanelaReal), \
             patch.object(downloads_page.EXECUTOR_GLOBAL, 'rodar', side_effect=rodar):
            self.page._preparar_uma(self.linha)
        self.assertTrue(visto['aguardando'])
        self.assertEqual(visto['caminho'], self.capa.caminho)
        with patch.object(self.cfg, 'garantir_pasta_saida'), \
             patch.object(self.fila, 'adicionar', return_value=42) as adicionar:
            self.page._baixar_selecionadas()
        enviado = adicionar.call_args.kwargs['preparacao']
        self.assertEqual(enviado['capa'].caminho, self.capa.caminho)
        self.assertEqual(enviado['meta'].album, 'Novo')

    def test_revisao_com_erro_mantem_capa_e_permite_nova_tentativa(self):
        self.editar({'album':'Novo'})
        class Janela:
            recusou = False
            def __init__(self, pai, capa, musica): self.escolhida = capa
            def definir_pendente(self, p): pass
            def show(self): pass
            def reject(self): pass
            def close(self): pass
        def rodar(fn,*args,**kwargs): kwargs['ao_erro']('sem rede')
        with patch.object(downloads_page, 'DialogoCapas', Janela), \
             patch.object(downloads_page.EXECUTOR_GLOBAL, 'rodar', side_effect=rodar), \
             patch.object(downloads_page.QMessageBox, 'warning'):
            self.page._preparar_uma(self.linha)
        self.assertIs(self.linha.preparacao['capa'], self.capa)
        self.assertTrue(self.linha.preparacao['revisao_pendente'])
        self.assertFalse(self.page._preparando)

    def test_sem_capa_continua_sem_capa_ao_editar(self):
        self.prep['capa'] = CoverResult(observacao='Não usar capa')
        self.editar({'album':'Novo'})
        self.assertFalse(self.linha.preparacao['capa'].ok)
        self.assertTrue(self.linha.preparacao['revisao_pendente'])

    def test_cancelar_revisao_e_resposta_tardia_preservam_capa(self):
        self.editar({'artista':'Novo artista'})
        cb = {}
        class Janela:
            def __init__(self, pai, capa, musica):
                self.escolhida = capa; self.recusou = False
            def definir_pendente(self, p): pass
            def show(self): pass
            def exec(self): return QDialog.Rejected
            def close(self): pass
        def rodar(fn,*args,**kwargs): cb.update(kwargs)
        with patch.object(downloads_page, 'DialogoCapas', Janela), \
             patch.object(downloads_page.EXECUTOR_GLOBAL, 'rodar', side_effect=rodar):
            self.page._preparar_uma(self.linha)
        cb['ao_resultado']({'meta':TrackMeta(titulo='Retorno tardio'), 'capa':CoverResult(), 'ident':None})
        self.assertEqual(self.linha.preparacao['meta'].artista, 'Novo artista')
        self.assertIs(self.linha.preparacao['capa'], self.capa)
        self.assertTrue(self.linha.preparacao['revisao_pendente'])

if __name__ == '__main__': unittest.main()

"""Fluxo gráfico de revisão, confirmação e escrita de um MP3 local."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox, QPushButton
from mutagen.id3 import ID3, APIC
from app.config import Config
from app import editar_mp3
from app.ui.pages import mp3_viewer_page, editar_mp3_dialog
from app.models import Identificacao
from testes.testes_editar_mp3 import criar_mp3, imagem_png

_app = QApplication.instance() or QApplication([])


def imediato(fn, *args, **kw):
    try:
        saida = fn(*args)
    except Exception as exc:
        kw['ao_erro'](str(exc))
    else:
        kw['ao_resultado'](saida)


class EditorMP3UI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.arquivo = self.base / 'a.mp3'; criar_mp3(self.arquivo)
        self.outro = self.base / 'b.mp3'; criar_mp3(self.outro)
        self.page = mp3_viewer_page.MP3ViewerPage(Config(self.base / 'config.json'))
        self.page._local = str(self.base)
        self.page.show()
        self.patcher = patch.object(mp3_viewer_page.EXECUTOR_GLOBAL, 'rodar', side_effect=imediato)
        self.patcher.start()
        self.page.atualizar()
        _app.processEvents()

    def tearDown(self):
        self.patcher.stop()
        self.page._encerrando = True
        self.page.close(); self.page.deleteLater(); _app.processEvents()
        self.tmp.cleanup()

    def test_edicao_cancela_sem_modificar_e_preserva_selecao(self):
        pagina = self.page
        pagina.tabela.selectRow(1)
        self.assertEqual(pagina._caminho_atual, str(self.outro))
        antes = self.outro.read_bytes()
        with patch.object(editar_mp3_dialog.DialogoEditarMP3, 'exec', return_value=QDialog.Rejected):
            pagina.btn_editar.click()
        self.assertEqual(self.outro.read_bytes(), antes)
        self.assertEqual(pagina._caminho_atual, str(self.outro))
        self.assertFalse(list(self.base.glob('*.rifflab-backup*')))

    def test_salvar_musica_escolhida_com_capa_e_recarrega_mesma_musica(self):
        pagina = self.page
        pagina.tabela.selectRow(1)
        original, outro = self.outro.read_bytes(), self.arquivo.read_bytes()
        capa = imagem_png()
        def editar(dialogo):
            dialogo.campos['album'].setText('Appetite for Destruction')
            dialogo.campos['genero'].setText('Hard Rock')
            dialogo.capa_acao, dialogo.capa_dados = 'trocar', capa
            self.assertEqual(self.outro.read_bytes(), original)
            dialogo._validar()
            return dialogo.result()
        with patch.object(editar_mp3_dialog.DialogoEditarMP3, 'exec', editar), \
             patch.object(mp3_viewer_page.QMessageBox, 'question', return_value=QMessageBox.Yes), \
             patch.object(mp3_viewer_page.QMessageBox, 'information'):
            pagina.btn_editar.click()
        self.assertEqual(self.arquivo.read_bytes(), outro)
        self.assertEqual(Path(str(self.outro) + '.rifflab-backup').read_bytes(), original)
        tags = ID3(self.outro)
        self.assertEqual(str(tags['TALB']), 'Appetite for Destruction')
        self.assertEqual(str(tags['TCON']), 'Hard Rock')
        self.assertEqual(str(tags['TDRC']), '1987-07-21')
        self.assertEqual(str(tags['TRCK']), '1/12')
        self.assertTrue(any(int(x.type) == 3 and x.data == capa for x in tags.getall('APIC')))
        self.assertTrue(any(int(x.type) == 4 and x.data == b'contracapa' for x in tags.getall('APIC')))
        self.assertEqual(pagina._caminho_atual, str(self.outro))
        self.assertIn('Appetite for Destruction', pagina.lbl_album.text())

    def test_conflito_externo_nao_substitui_arquivo(self):
        antes = self.arquivo.read_bytes()
        def editar(dialogo):
            dialogo.campos['genero'].setText('Rock')
            self.arquivo.write_bytes(antes + b'alterado por outro app')
            return QDialog.Accepted
        with patch.object(editar_mp3_dialog.DialogoEditarMP3, 'exec', editar), \
             patch.object(mp3_viewer_page.QMessageBox, 'question', return_value=QMessageBox.Yes), \
             patch.object(mp3_viewer_page.QMessageBox, 'warning') as aviso:
            self.page.btn_editar.click()
        self.assertEqual(self.arquivo.read_bytes(), antes + b'alterado por outro app')
        self.assertIn('mudou', aviso.call_args.args[2])
        self.assertFalse(list(self.base.glob('*.rifflab-backup*')))

    def test_ia_usa_tags_sem_enviar_caminho_nem_gravar_automaticamente(self):
        snap = editar_mp3.abrir(self.arquivo)
        dialogo = editar_mp3_dialog.DialogoEditarMP3(snap, self.page)
        antes = self.arquivo.read_bytes()
        ident = Identificacao(ok=True, titulo='Welcome to the Jungle', artista="Guns N' Roses", confianca=.95)
        catalogo = {'titulo': ident.titulo, 'artista': ident.artista, 'album':'Appetite for Destruction',
                    'ano':1987, 'faixa':1, 'artista_album':ident.artista, 'genero':'Hard Rock',
                    'fonte':'musicbrainz'}
        resposta = {'ident':ident, 'catalogo':catalogo, 'consulta':{'titulo':ident.titulo, 'artista':ident.artista}}
        def agendar(fn, *args, **kw):
            self.assertEqual(args[0].pagina_url, '')
            self.assertNotIn(str(self.arquivo), str(args[0]))
            kw['ao_resultado'](resposta)
        with patch.object(mp3_viewer_page.EXECUTOR_GLOBAL, 'rodar', side_effect=agendar):
            dialogo.btn_rever_ia.click()
        self.assertEqual(dialogo.campos['album'].text(), 'Appetite for Destruction')
        self.assertEqual(dialogo.campos['genero'].text(), 'Hard Rock')
        self.assertEqual(self.arquivo.read_bytes(), antes)
        dialogo.reject()
        self.assertEqual(self.arquivo.read_bytes(), antes)

    def test_sugestao_na_mesma_edicao_preserva_data_e_total_de_faixas(self):
        dialogo = editar_mp3_dialog.DialogoEditarMP3(editar_mp3.abrir(self.arquivo), self.page)
        ident = Identificacao(ok=True, titulo='Welcome to the Jungle', artista="Guns N' Roses", confianca=.95)
        catalogo = {'titulo': ident.titulo, 'artista': ident.artista, 'album':'Álbum errado',
                    'ano':1987, 'faixa':1, 'artista_album':ident.artista, 'genero':'Rock', 'fonte':'musicbrainz'}
        resposta = {'ident':ident, 'catalogo':catalogo, 'consulta':{'titulo':ident.titulo, 'artista':ident.artista}}
        with patch.object(mp3_viewer_page.EXECUTOR_GLOBAL, 'rodar', side_effect=lambda fn, *a, **kw: kw['ao_resultado'](resposta)):
            dialogo.btn_rever_ia.click()
        self.assertEqual(dialogo.campos['ano'].text(), '1987-07-21')
        self.assertEqual(dialogo.campos['faixa'].text(), '1/12')
        self.assertNotIn('ano', dialogo.alteracoes())
        self.assertNotIn('faixa', dialogo.alteracoes())

    def test_retorno_tardio_de_abertura_nao_edita_musica_errada(self):
        pendentes = []
        def agendar(fn, *args, **kwargs):
            if fn is editar_mp3.abrir:
                pendentes.append((args, kwargs))
            else:
                imediato(fn, *args, **kwargs)
        with patch.object(mp3_viewer_page.EXECUTOR_GLOBAL, 'rodar', side_effect=agendar), \
             patch.object(mp3_viewer_page, 'DialogoEditarMP3') as dialogo:
            self.page.btn_editar.click()
            self.assertFalse(self.page.btn_editar.isEnabled())
            self.page.tabela.selectRow(1)
            pendentes[0][1]['ao_resultado'](editar_mp3.abrir(pendentes[0][0][0]))
            self.assertTrue(self.page.btn_editar.isEnabled())
            self.assertEqual(self.page._caminho_atual, str(self.outro))
            dialogo.assert_not_called()

    def test_janela_real_de_capa_oferece_arquivo_e_nao_remove_sem_confirmacao(self):
        dialogo = editar_mp3_dialog.DialogoEditarMP3(editar_mp3.abrir(self.arquivo), self.page)
        antes = self.arquivo.read_bytes()
        def conferir(capa):
            self.assertEqual(capa.btn_sem.text(), 'Remover capa frontal')
            self.assertTrue(any(c.text() == 'Escolher imagem do computador'
                                for c in capa.findChildren(QPushButton)))
            return QDialog.Rejected
        with patch.object(editar_mp3_dialog.DialogoCapas, 'exec', conferir):
            dialogo._escolher_capa_existente()
        self.assertEqual(dialogo.capa_acao, 'manter')
        self.assertEqual(self.arquivo.read_bytes(), antes)

    def test_troca_capa_ou_cancelar_ignoram_acoes_ate_salvar(self):
        dialogo = editar_mp3_dialog.DialogoEditarMP3(editar_mp3.abrir(self.arquivo), self.page)
        img = self.base / 'nova.png'; img.write_bytes(imagem_png())
        falso = Mock()
        falso.exec.return_value = QDialog.Accepted
        falso.recusou = False
        falso.escolhida.caminho = str(img)
        with patch.object(editar_mp3_dialog, 'DialogoCapas', return_value=falso):
            dialogo._escolher_capa_existente()
        self.assertEqual(dialogo.capa_acao, 'trocar')
        dialogo._manter_capa()
        self.assertEqual(dialogo.capa_acao, 'manter')
        self.assertTrue(any(int(x.type)==3 and x.data==b'capa antiga' for x in ID3(self.arquivo).getall('APIC')))

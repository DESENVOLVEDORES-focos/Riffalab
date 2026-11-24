"""Revisão das opções e imagem copiada, sem editar músicas existentes."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtGui import QImage, QDesktopServices
from PySide6.QtWidgets import QApplication, QMessageBox, QDialog
from app.models import CoverResult
from app.ui.dialogos import DialogoCapas


class CapasUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_mostra_tipo_album_e_single(self):
        album = CoverResult(caminho='a.png', fonte='itunes', album='Álbum', tipo_lancamento='album')
        album.alternativas = [CoverResult(caminho='b.png', fonte='itunes', album='Música', tipo_lancamento='single')]
        dlg = DialogoCapas(None, album)
        self.assertIn('Álbum', dlg.lista.item(0).text())
        self.assertIn('Single', dlg.lista.item(1).text())
        dlg.close(); dlg.deleteLater()

    def test_copia_imagem_e_exige_confirmacao_usuario(self):
        origem = QImage(str(Path(__file__).resolve().parents[1] / 'docs' / 'tela-pesquisa.png'))
        self.assertGreaterEqual(min(origem.width(), origem.height()), 320)
        imagem = origem.copy(0, 0, 320, 320)
        QApplication.clipboard().setImage(imagem)
        with tempfile.TemporaryDirectory() as d:
            with patch('app.config.PASTA_DOWNLOAD_CAPAS', Path(d)):
                dlg = DialogoCapas(None, CoverResult())
                dlg._colar_imagem()
                self.assertEqual(len(dlg.opcoes), 1)
                self.assertTrue(dlg.escolhida.ok)
                self.assertEqual(dlg.escolhida.fonte, 'imagem colada')
                self.assertTrue(Path(dlg.escolhida.caminho).read_bytes().startswith(b'\x89PNG'))
                self.assertNotEqual(dlg.result(), QDialog.Accepted)
                dlg._usar()
                self.assertEqual(dlg.result(), QDialog.Accepted)
                dlg.close(); dlg.deleteLater()
        QApplication.clipboard().clear()

    def test_rejeita_miniatura_sem_gravar(self):
        img = QImage(50, 50, QImage.Format_RGB32); img.fill(0xff00ff00)
        QApplication.clipboard().setImage(img)
        dlg = DialogoCapas(None, CoverResult())
        with patch.object(QMessageBox,'warning') as aviso, patch.object(dlg, '_salvar_imagem_colada') as salvar:
            dlg._colar_imagem()
        aviso.assert_called_once(); salvar.assert_not_called()
        self.assertEqual(len(dlg.opcoes),0)
        dlg.close(); dlg.deleteLater(); QApplication.clipboard().clear()

    def test_google_abre_pesquisa_nao_usa_api(self):
        dlg = DialogoCapas(None, CoverResult(), {'titulo':'Música', 'artista':'Queen','album':'Disco'})
        with patch.object(QDesktopServices, 'openUrl') as abrir:
            dlg._pesquisar_google()
        url = abrir.call_args.args[0]
        self.assertEqual(url.host(), 'www.google.com')
        self.assertIn('queen', url.toString().lower())
        self.assertIn('album', url.toString().lower())
        dlg.close(); dlg.deleteLater()

if __name__ == '__main__': unittest.main()

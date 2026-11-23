"""A revisão precisa mostrar qual identidade realmente foi usada na busca."""
import os
import unittest
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication
from app.models import CoverResult
from app.ui.dialogos import DialogoCapas


class IdentidadeCapaUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_mostra_termos_origem_e_aviso_na_revisao(self):
        consulta = {'artista':'Artista IA','titulo':'Título IA','origem':'IA',
                    'aviso':'Confira os metadados.'}
        dialogo = DialogoCapas(None, CoverResult(), {'consulta_capa': consulta})
        texto = dialogo.lbl_consulta.text()
        self.assertIn('Artista IA', texto)
        self.assertIn('Título IA', texto)
        self.assertIn('IA', texto)
        self.assertIn('Confira os metadados.', texto)
        dialogo.close(); dialogo.deleteLater()

if __name__ == '__main__': unittest.main()

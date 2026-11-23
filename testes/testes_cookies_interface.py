"""Botão do teste online não executa implicitamente e descarta resultado antigo."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication
from app.config import Config
from app.ui.pages.settings_page import SettingsPage


class InterfaceCookies(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_botao_mostra_progresso_e_resultado_sem_travar(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = Config(Path(d) / 'config.json')
            cfg.dados['caminho_cookies'] = str(Path(d) / 'cookies.txt')
            with patch.object(SettingsPage, '_verificar_ferramentas'), \
                 patch('app.ui.pages.settings_page.EXECUTOR_GLOBAL.rodar') as rodar:
                page = SettingsPage(cfg)
                self.assertEqual(rodar.call_count, 0)
                page.btn_testar_cookies.click()
                self.assertEqual(rodar.call_count, 1)
                self.assertFalse(page.btn_testar_cookies.isEnabled())
                self.assertIn('Consultando', page.lbl_teste_cookies.text())
                rodar.call_args.kwargs['ao_resultado']({'estado':'confirmado', 'mensagem':'teste concluído'})
                self.assertTrue(page.btn_testar_cookies.isEnabled())
                self.assertEqual(page.lbl_teste_cookies.text(), 'teste concluído')
                page.btn_testar_cookies.click()
                cfg.dados['caminho_cookies'] = str(Path(d) / 'outro.txt')
                rodar.call_args.kwargs['ao_resultado']({'estado':'confirmado', 'mensagem':'resultado antigo'})
                self.assertNotIn('resultado antigo', page.lbl_teste_cookies.text())
                self.assertIn('mudou', page.lbl_teste_cookies.text())
                page.close(); page.deleteLater()

if __name__ == '__main__': unittest.main()

"""Personalização da interface: prévia, persistência e segurança."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QColorDialog
from app.config import Config
from app.db import Banco
from app.ui.main_window import MainWindow
from app.ui.theme import (CHAVES_CORES, PALETA, aplicar_tema, cores_do_config,
                          paleta_personalizada, qss, validar_cor)


class PersonalizacaoCores(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.cfg = Config(self.base/'config.json')
        self.cfg.dados.update(pasta_saida=str(self.base/'musicas'), ia_ativa=True,
                              ia_modelo='modelo-escolhido', usar_cookies=False)
        self.banco = Banco(self.base/'banco.db')
        with patch('app.ui.pages.settings_page.SettingsPage._verificar_ferramentas'), \
             patch('app.ui.main_window.MainWindow._atualizar_rodape_completo'):
            self.janela = MainWindow(self.cfg, self.banco)
        self.janela.show(); self.app.processEvents()
        self.pagina = self.janela.pagina_config

    def tearDown(self):
        self.janela.close(); self.janela.deleteLater()
        from app.workers import EXECUTOR_GLOBAL, EXECUTOR_FORMATOS
        EXECUTOR_GLOBAL.aguardar(30000); EXECUTOR_FORMATOS.aguardar(30000)
        from PySide6.QtCore import QCoreApplication, QEvent
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        aplicar_tema(self.app); self.app.processEvents()

    def escolher(self, chave, valor):
        with patch.object(QColorDialog, 'getColor', return_value=QColor(valor)) as seletor:
            self.pagina.botoes_cores[chave].click()
            seletor.assert_called_once()

    def test_previa_imediata_e_persistencia_ao_salvar_e_reabrir(self):
        cores = {'cor_fundo':'#152039', 'cor_lateral':'#F4E4B4', 'cor_cartoes':'#243E59',
                 'cor_botoes':'#F5BD40', 'cor_texto':'#FFFFFF'}
        for chave, cor in cores.items():
            self.escolher(chave, cor)
        self.assertEqual(self.pagina.lbl_cookies.property('papel_tema'), 'dim')
        self.assertIn('QLabel[papel_tema="dim"] { color: #D3D8DE; }', self.app.styleSheet())
        self.assertEqual(cores_do_config(self.cfg), {k:'' for k in CHAVES_CORES})
        qss_previa = self.app.styleSheet()
        for valor in cores.values(): self.assertIn(valor, qss_previa)
        self.assertEqual(self.app.palette().color(QPalette.Button).name(), '#f5bd40')
        self.assertEqual(self.app.palette().color(QPalette.ButtonText).name(), '#000000')
        self.pagina.salvar()
        recarregado = Config(self.cfg.caminho)
        self.assertEqual(cores_do_config(recarregado), cores)
        self.assertEqual(recarregado.get('usar_cookies'), False)
        self.assertEqual(recarregado.get('pasta_saida'), str(self.base/'musicas'))
        aplicar_tema(self.app, recarregado.get('cor_destaque'), cores_do_config(recarregado))
        self.assertEqual(self.app.styleSheet(), qss_previa)
        self.assertEqual(self.app.palette().color(QPalette.Button).name(), '#f5bd40')

    def test_cancelar_paleta_nao_muda_cores_nem_disco(self):
        antes = self.app.styleSheet()
        with patch.object(QColorDialog, 'getColor', return_value=QColor()):
            self.pagina.botoes_cores['cor_fundo'].click()
        self.assertEqual(self.pagina.cores_em_edicao['cor_fundo'], '')
        self.assertEqual(self.app.styleSheet(), antes)
        self.assertFalse(self.cfg.caminho.exists())

    def test_restaurar_apenas_cores_precisa_salvar_e_preserva_demais_dados(self):
        self.escolher('cor_fundo', '#203040'); self.pagina.salvar()
        self.pagina.btn_cores_padrao.click()
        self.assertEqual(self.pagina.cores_em_edicao, {k:'' for k in CHAVES_CORES})
        self.assertEqual(Config(self.cfg.caminho).get('cor_fundo'), '#203040')
        self.pagina.salvar(); cfg = Config(self.cfg.caminho)
        self.assertEqual(cores_do_config(cfg), {k:'' for k in CHAVES_CORES})
        self.assertEqual(cfg.get('pasta_saida'), str(self.base/'musicas'))
        self.assertFalse(cfg.get('usar_cookies'))

    def test_corrompidas_ou_injecao_nao_entram_no_qss(self):
        for ruim in ('red', '#FFF', '#123456; color:red', '#aabbcc00', 123, None):
            self.assertEqual(validar_cor(ruim), '')
        self.cfg['cor_fundo'] = '#FF00AA; background:red'
        self.cfg['cor_botoes'] = {'invalido': True}
        self.assertEqual(cores_do_config(self.cfg)['cor_fundo'], '')
        self.assertEqual(paleta_personalizada(cores_do_config(self.cfg))['bg0'], PALETA['bg0'])
        self.assertNotIn('background:red', qss(cores=cores_do_config(self.cfg)))

    def test_preview_nao_remove_selecao_ou_altera_arquivo_de_musica(self):
        from app.models import TrackResult
        mp3 = self.base/'musica existente.mp3'; mp3.write_bytes(b'nao alterar')
        resultado = TrackResult('123', 'ytdlp', 'Canção', 'Artista')
        self.assertTrue(self.janela.pagina_downloads.adicionar_selecao({'resultado': resultado}))
        selecionada = self.janela.pagina_downloads.selecoes[0]
        self.escolher('cor_fundo', '#122233'); self.escolher('cor_botoes', '#FFAA00')
        self.assertIs(self.janela.pagina_downloads.selecoes[0], selecionada)
        self.assertTrue(selecionada.check.isChecked())
        self.assertEqual(mp3.read_bytes(), b'nao alterar')

    def test_cartoes_claros_ainda_tem_borda_visivel(self):
        p = paleta_personalizada({'cor_cartoes':'#FFFFFF', 'cor_texto':'#000000'})
        self.assertEqual(p['surface'], '#FFFFFF')
        self.assertNotEqual(p['border'], p['surface'])
        self.assertEqual(p['texto'], '#000000')

    def test_fundo_card_e_menu_cores_independentes(self):
        valores = {'cor_fundo':'#101020', 'cor_cartoes':'#202030', 'cor_lateral':'#FFFFFF',
                   'cor_botoes':'#FFCF30', 'cor_texto':'#FFFFFF'}
        css = qss(cores=valores)
        for cor in valores.values(): self.assertIn(cor, css)
        self.assertIn('QLabel#logo {\n    color: #000000;', css)
        self.assertIn('background: #202030;', css)
        self.assertIn('background: #FFCF30;', css)

if __name__ == '__main__': unittest.main()

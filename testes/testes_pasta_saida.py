"""Destino indisponível não impede abertura nem inicia downloads incorretos."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from app.config import Config
from app.models import AudioFormat, TrackResult
from app.pipeline import processar_resultado


class PastaSaida(unittest.TestCase):
    def test_ler_caminho_inacessivel_nao_tenta_criar_pasta(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = Config(Path(d) / 'config.json')
            cfg.dados['pasta_saida'] = r'D:\Musicas'
            with patch.object(Path, 'mkdir', side_effect=AssertionError('tentou criar')):
                self.assertEqual(str(cfg.pasta_saida), r'D:\Musicas')
            self.assertEqual(cfg.get('pasta_saida'), r'D:\Musicas')

    def test_unidade_desconectada_e_permissao_retornam_erro_sem_fallback(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = Config(Path(d) / 'config.json')
            cfg.dados['pasta_saida'] = r'D:\Musicas'
            with patch.object(Path, 'mkdir', side_effect=FileNotFoundError('unidade ausente')):
                with self.assertRaisesRegex(RuntimeError, 'Pasta de saída indisponível') as erro:
                    cfg.garantir_pasta_saida()
            self.assertIn(r'D:\Musicas', str(erro.exception))
            self.assertEqual(cfg.get('pasta_saida'), r'D:\Musicas')
            self.assertFalse(cfg.caminho.exists())
            cfg.dados['pasta_saida'] = d
            with patch('app.config.tempfile.TemporaryFile', side_effect=PermissionError('negado')):
                with self.assertRaisesRegex(RuntimeError, 'sem permissão'):
                    cfg.garantir_pasta_saida()
            self.assertEqual(cfg.get('pasta_saida'), d)

    def test_destino_valido_pode_ser_criado_e_nao_sobra_teste(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = Config(Path(d) / 'config.json')
            pasta = Path(d) / 'músicas com espaços' / 'novas'
            cfg.dados['pasta_saida'] = str(pasta)
            self.assertEqual(cfg.garantir_pasta_saida(), pasta)
            self.assertTrue(pasta.is_dir())
            self.assertEqual(list(pasta.iterdir()), [])

    def test_pipeline_interrompe_antes_de_baixar_em_pasta_invalida(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            arquivo = base / 'arquivo'; arquivo.write_text('não é pasta')
            cfg = Config(base / 'config.json')
            cfg.dados['pasta_saida'] = str(arquivo / 'músicas')
            fonte = Mock()
            r = TrackResult('id', 'ytdlp', 'Música')
            with patch('app.pipeline._pasta_temp', side_effect=AssertionError('criou pasta temporária')):
                resultado = processar_resultado(r, cfg, AudioFormat(codec='opus', format_id='251'), fonte=fonte)
            self.assertFalse(resultado['ok'])
            self.assertIn('Pasta de saída indisponível', resultado['erro'])
            fonte.baixar.assert_not_called()
            self.assertEqual(cfg.get('pasta_saida'), str(arquivo / 'músicas'))
            self.assertEqual(arquivo.read_text(), 'não é pasta')

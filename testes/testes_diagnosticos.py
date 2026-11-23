"""Erros tratados devem chegar ao console sem divulgar segredos comuns."""
import io
import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from app import logging_setup, pipeline
from app.config import Config
from app.downloader import GerenciadorFila
from app.models import AudioFormat, TrackResult


class Diagnosticos(unittest.TestCase):
    def test_filtro_console_e_arquivo_com_traceback(self):
        stream = io.StringIO()
        with tempfile.TemporaryDirectory() as d:
            logger = logging.getLogger('rifflab')
            antigos = list(logger.handlers)
            for h in antigos: logger.removeHandler(h)
            try:
                with patch.object(logging_setup, 'ARQ_LOG', Path(d) / 'log.txt'), \
                     patch.object(logging_setup.sys, 'stderr', stream):
                    logging_setup.configurar()
                    try:
                        raise ValueError('token=segredo123 https://exemplo.test/a?key=xyz')
                    except ValueError:
                        logger.exception('Erro no lote: Cookie: sessao=abc')
                    logging_setup.registrar_erro('gravação', 'falha longa ' + 'x' * 600 + '\nAuthorization: Bearer secreta')
                    for h in logger.handlers: h.flush()
                    arquivo = (Path(d) / 'log.txt').read_text(encoding='utf8')
                for texto in (stream.getvalue(), arquivo):
                    for segredo in ('segredo123', 'exemplo.test', 'sessao=abc', 'secreta'):
                        self.assertNotIn(segredo, texto)
                    self.assertIn('ValueError', texto)
                    self.assertIn('Traceback', texto)
                    self.assertIn('x' * 600, texto)
            finally:
                for h in list(logger.handlers):
                    logger.removeHandler(h); h.close()
                for h in antigos: logger.addHandler(h)

    def test_pasta_saida_informa_causa(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = Config(Path(d) / 'config.json')
            with patch.object(Path, 'mkdir', side_effect=PermissionError('dispositivo indisponível')):
                with self.assertRaisesRegex(RuntimeError, 'PermissionError: dispositivo indisponível'):
                    cfg.garantir_pasta_saida()

    def test_falha_pipeline_na_fila_e_registrada_com_etapa_sem_truncar(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = Config(Path(d) / 'config.json')
            banco = Mock()
            fila = GerenciadorFila(cfg, banco)
            job = {'id': 7, 'titulo': 'Exemplo'}
            erro = 'sem espaço ' + 'x' * 700
            with patch('app.downloader.registrar_erro') as registrar, patch.object(fila, '_liberar'):
                fila._concluir(job, {'ok': False, 'erro': erro, 'etapa': 'gravação na pasta de saída'})
            self.assertIn('gravação na pasta de saída', registrar.call_args.args[0])
            self.assertEqual(registrar.call_args.args[1], erro)
            self.assertEqual(job['erro'], erro)
            self.assertEqual(banco.atualizar_download.call_args.kwargs['erro'], erro)

    def test_pipeline_indica_etapa_do_download(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = Config(Path(d) / 'config.json')
            cfg.dados['pasta_saida'] = str(Path(d) / 'saida')
            fonte = Mock()
            fonte.baixar.side_effect = OSError('disco cheio')
            fmt = AudioFormat(codec='mp3')
            resultado = TrackResult('id', 'teste', 'Música', formatos=[fmt])
            with patch.object(pipeline, 'PASTA_TEMP', Path(d) / 'temp'):
                res = pipeline.processar_resultado(resultado, cfg, formato=fmt, fonte=fonte)
            self.assertFalse(res['ok'])
            self.assertEqual(res['etapa'], 'obtenção do áudio')
            self.assertIn('disco cheio', res['erro'])

if __name__ == '__main__':
    unittest.main()

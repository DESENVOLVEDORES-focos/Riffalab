"""Consulta sob demanda não modifica o resultado antes da conclusão."""
import unittest
from unittest.mock import patch
from app.models import AudioFormat, TrackResult
from app.ui.pages.downloads_page import consultar_formatos_download


class ConsultaSobDemanda(unittest.TestCase):
    def test_reconsulta_em_copia_e_preserva_originais(self):
        anterior = AudioFormat(codec='aac', format_id='140')
        resultado = TrackResult('a', 'ytdlp', 'Música', 'Artista', formatos=[anterior],
            extra={'metodos_consulta': [{'estado': 'ok'}], 'erro_detalhe': 'falha antiga'})
        class Fonte:
            def detalhar(self, copia):
                self.assert_copia(copia)
                copia.formatos = [AudioFormat(codec='opus', format_id='251')]
                return copia
            def assert_copia(self, copia):
                assert copia is not resultado
                assert not copia.formatos
                assert 'metodos_consulta' not in copia.extra
                assert 'erro_detalhe' not in copia.extra
        with patch('app.sources.por_id', return_value=Fonte()):
            novo = consultar_formatos_download(resultado, {})
        self.assertEqual(novo.formatos[0].format_id, '251')
        self.assertEqual(resultado.formatos[0].format_id, '140')
        self.assertIn('falha antiga', resultado.extra['erro_detalhe'])

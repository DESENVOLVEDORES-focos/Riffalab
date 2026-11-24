"""Casos reproduzíveis de busca de capas; não acessam ou modificam MP3s."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import pipeline
from app.config import Config
from app.metadata import coverartarchive, musicbrainz
from app.models import CoverResult, TrackMeta


class CorrecaoCapas(unittest.TestCase):
    def test_busca_legada_nao_consulta_api_de_capas(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = Config(Path(d) / 'config.json')
            meta = TrackMeta(titulo='Metallica - Nothing Else Matters', artista='MetallicaVEVO')
            with patch.object(pipeline.covers, 'encontrar_capa', side_effect=AssertionError('API de capa')):
                capa = pipeline.buscar_capa(meta, cfg)
            self.assertFalse(capa.ok)
            self.assertIn('manualmente', capa.observacao)

    def test_contracapa_na_edicao_nao_esconde_frontal_do_grupo(self):
        def resultado(release_id='', release_group=''):
            if release_id:
                return [{'url':'https://example.test/back', 'frontal':False, 'tipos':['Back']}]
            return [{'url':'https://example.test/front', 'frontal':True, 'tipos':['Front']}]
        with patch.object(musicbrainz, 'capas_release', side_effect=resultado) as chamadas:
            imagens = coverartarchive.imagens(release_id='single-edicao', release_group='single-grupo')
        self.assertEqual([i['url'] for i in imagens], ['https://example.test/front'])
        self.assertEqual(chamadas.call_count, 2)
        self.assertEqual(chamadas.call_args.kwargs['release_group'], 'single-grupo')

    def test_frontal_da_edicao_nao_busca_outro_grupo(self):
        with patch.object(musicbrainz, 'capas_release', return_value=[
                {'url':'https://example.test/front', 'frontal':True, 'tipos':['Front']}]) as chamadas:
            imagens = coverartarchive.imagens(release_id='single-edicao', release_group='single-grupo')
        self.assertEqual(len(imagens), 1)
        self.assertEqual(chamadas.call_count, 1)

    def test_fallback_nunca_aceita_contracapa(self):
        with patch.object(musicbrainz, 'capas_release', return_value=[
                {'url':'https://example.test/back', 'frontal':False, 'tipos':['Back']}]) as chamadas:
            self.assertEqual(coverartarchive.imagens(release_id='r', release_group='g'), [])
        self.assertEqual(chamadas.call_count, 2)

if __name__ == '__main__':
    unittest.main()

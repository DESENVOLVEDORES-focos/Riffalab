"""Pesquisa de vários termos: ordem, erros isolados e progresso."""
import threading
import time
import unittest
from unittest.mock import patch

from app import search_service


class PesquisasMultiplas(unittest.TestCase):
    def test_termos_em_paralelo_ordem_e_falha_isolada(self):
        inicio = threading.Barrier(3)
        chamadas = []
        progresso = []

        def pesquisar(termo, config, limite, fontes, **kwargs):
            chamadas.append((termo, limite, fontes, kwargs))
            inicio.wait(timeout=4)
            if termo == 'Pink Floyd':
                raise RuntimeError('fonte indisponível')
            if termo == 'Guns':
                time.sleep(0.05)
            return {'consulta': termo, 'resultados': [termo], 'filtrados': [],
                    'fontes': ['Fonte'], 'erros': {}, 'segundos': 1}

        with patch.object(search_service, 'pesquisar', side_effect=pesquisar):
            resultado = search_service.pesquisar_varias(['Guns', '', ' Pink Floyd ', 'Led Zeppelin'],
                object(), 7, ['fonte'], progresso=lambda n, m: progresso.append((n, m)),
                ordenar_por='qualidade')
        self.assertEqual([r['consulta'] for r in resultado], ['Guns', 'Pink Floyd', 'Led Zeppelin'])
        self.assertIn('fonte indisponível', resultado[1]['erros']['pesquisa'])
        self.assertEqual(resultado[2]['resultados'], ['Led Zeppelin'])
        self.assertEqual(progresso[-1][0], 100)
        self.assertTrue(all(c[1:3] == (7, ['fonte']) for c in chamadas))
        self.assertTrue(all(c[3]['ordenar_por'] == 'qualidade' for c in chamadas))
        self.assertTrue(all(c[3]['enriquecer_automatico'] is False for c in chamadas))

    def test_vazios_nao_geram_busca_e_repetidos_sao_mantidos(self):
        with patch.object(search_service, 'pesquisar', side_effect=lambda termo, *a, **k: {'consulta': termo}) as p:
            self.assertEqual(search_service.pesquisar_varias([' ', ''], object()), [])
            self.assertEqual(p.call_count, 0)
            r = search_service.pesquisar_varias(['X', 'X'], object())
            self.assertEqual([x['consulta'] for x in r], ['X', 'X'])
            self.assertEqual(p.call_count, 2)

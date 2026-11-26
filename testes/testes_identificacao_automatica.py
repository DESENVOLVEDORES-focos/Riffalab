"""Identificação em duas etapas antes da exibição, com rede simulada."""
import unittest
from unittest.mock import patch

from app.ia import identificador, revisao
from app.models import Identificacao, TrackResult
from app.preparacao import identificar_antes_de_download


class IdentificacaoAutomatica(unittest.TestCase):
    def setUp(self):
        self.r = TrackResult('video', 'ytdlp', 'Canção', 'Canal genérico',
                             extra={'titulo_original': 'Artista Exemplo - Canção (Official Video)'})
        self.cfg = {'ia_ativa': True, 'ia_min_confianca': .7}
        self.ident = Identificacao(ok=True, titulo='Canção', artista='Artista Exemplo', confianca=.95)
        self.catalogo = {'titulo': 'Canção', 'artista': 'Artista Exemplo', 'album': 'Disco',
                         'ano': 2001, 'faixa': 2, 'genero': 'Rock', 'fonte': 'musicbrainz',
                         'creditos_faixa': ['Pessoa — produção']}

    def test_duas_etapas_sequenciais_e_campos_aparecem(self):
        chamadas = []
        def primeira(r, cfg, **kw):
            chamadas.append(('primeira', kw))
            return self.ident
        def segunda(r, cfg, pedido):
            chamadas.append(('segunda', pedido['dados_atuais'].copy()))
            return {'ident': self.ident, 'catalogo': self.catalogo}
        with patch.object(identificador, 'identificar', side_effect=primeira), \
             patch.object(revisao, 'reavaliar', side_effect=segunda):
            dados = identificar_antes_de_download(self.r, self.cfg)
        self.assertEqual([x[0] for x in chamadas], ['primeira', 'segunda'])
        self.assertTrue(chamadas[0][1]['somente_identidade'])
        self.assertEqual(chamadas[1][1]['titulo'], 'Canção')
        self.assertEqual(chamadas[1][1]['artista'], 'Artista Exemplo')
        self.assertEqual((dados['meta'].album, dados['meta'].ano, dados['meta'].faixa), ('Disco', 2001, 2))
        self.assertIn('Pessoa', dados['creditos_catalogo'][0])
        self.assertTrue(dados['capa_pendente'])

    def test_prompt_utiliza_titulo_original_inclusive_na_revisao(self):
        self.assertIn('Artista Exemplo - Canção (Official Video)', identificador.montar_pedido(self.r))
        self.assertIn('Artista Exemplo - Canção (Official Video)', identificador.montar_pedido(self.r, {'dados_atuais': {}}))
        self.assertEqual(set(identificador.ESQUEMA_VIDEO['properties']),
                         {'identificado', 'confianca', 'titulo', 'artista', 'campos_incertos'})

    def test_ia_insegura_nao_inventa_identidade_de_canal(self):
        incerto = Identificacao(ok=True, titulo='Canção', artista='Artista Errado', confianca=.2)
        with patch.object(identificador, 'identificar', return_value=incerto), \
             patch.object(revisao, 'reavaliar') as segunda:
            dados = identificar_antes_de_download(self.r, self.cfg)
        segunda.assert_not_called()
        self.assertEqual(dados['meta'].artista, 'Canal genérico')
        self.assertFalse(dados['meta'].album)
        self.assertIn('não confirmou', dados['identificacao_aviso'])

    def test_ia_desligada_e_falha_mantem_dados_sem_inventar(self):
        for ativa, ident in [(False, None), (True, Identificacao(ok=False, erro='sem conexão'))]:
            with self.subTest(ativa=ativa), patch.object(identificador, 'identificar', return_value=ident) as primeira, \
                 patch.object(revisao, 'reavaliar') as segunda:
                dados = identificar_antes_de_download(self.r, {'ia_ativa': ativa})
                self.assertEqual(dados['meta'].titulo, 'Canção')
                self.assertFalse(dados['meta'].album)
                self.assertTrue(dados['identificacao_aviso'])
                segunda.assert_not_called()
                self.assertEqual(primeira.call_count, int(ativa))

    def test_edicoes_manuais_prevalecem_e_nao_misturam_album(self):
        edicao = {'titulo': 'Minha canção', 'artista': 'Outro artista', 'album': 'Meu álbum', 'ano': '2010'}
        with patch.object(identificador, 'identificar', return_value=self.ident), \
             patch.object(revisao, 'reavaliar', return_value={'ident': self.ident, 'catalogo': self.catalogo}) as segunda:
            dados = identificar_antes_de_download(self.r, self.cfg, edicao)
        self.assertEqual(segunda.call_args.args[2]['dados_atuais']['artista'], 'Outro artista')
        meta = dados['meta']
        self.assertEqual((meta.titulo, meta.artista, meta.album, meta.ano, meta.faixa),
                         ('Minha canção', 'Outro artista', 'Meu álbum', 2010, None))

    def test_versao_distinta_e_identidade_incertas_nao_sao_aceitas(self):
        for ident in (Identificacao(ok=True, titulo='Canção', artista='Artista Exemplo', confianca=.9, campos_incertos=['artista']),
                      Identificacao(ok=True, titulo='Canção Remix', artista='Artista Exemplo', confianca=.9)):
            with self.subTest(ident=ident), patch.object(identificador, 'identificar', return_value=ident), \
                 patch.object(revisao, 'reavaliar') as segunda:
                dados = identificar_antes_de_download(self.r, self.cfg)
                segunda.assert_not_called()
                self.assertIn('não confirmou', dados['identificacao_aviso'])

    def test_chamadas_reais_de_identificador_com_pedidos_distintos_e_catalogo(self):
        from app.ia import cliente_groq
        respostas = [
            ({'identificado': True, 'confianca': .95, 'titulo': 'Canção',
              'artista': 'Artista Exemplo', 'campos_incertos': []}, 'mock'),
            ({'identificado': True, 'confianca': .95, 'titulo': 'Canção',
              'artista': 'Artista Exemplo', 'album': 'Disco', 'genero': 'Rock',
              'ano': 2001, 'faixa': 2, 'artista_album': 'Artista Exemplo',
              'artistas_participantes': [], 'creditos_album': [], 'campos_incertos': []}, 'mock'),
        ]
        with patch.object(cliente_groq, 'disponivel', return_value=(True, '')), \
             patch.object(cliente_groq, 'completar_json', side_effect=respostas) as completar, \
             patch('app.metadata.album_original.encontrar', return_value=self.catalogo), \
             patch('app.metadata.itunes.melhor_faixa', return_value={}):
            resultado = identificar_antes_de_download(self.r, self.cfg)
        self.assertEqual(completar.call_count, 2)
        primeira, segunda = completar.call_args_list
        self.assertIs(primeira.args[3], identificador.ESQUEMA_VIDEO)
        self.assertIs(segunda.args[3], identificador.ESQUEMA_REVISAO)
        self.assertIn('Artista Exemplo - Canção (Official Video)', primeira.args[2])
        self.assertIn('Artista Exemplo', segunda.args[2])
        self.assertEqual(resultado['meta'].album, 'Disco')

"""Nomes de saída e capas somente de lançamentos sinalizados como single."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.config import Config
from app.models import TrackMeta
from app.organizer import aplicar_template
from app.metadata import busca_capas, covers, itunes, musicbrainz, provedores


class Organizacao(unittest.TestCase):
    def test_migracao_padrao_novo_sem_alterar_outros_campos_ou_modelo_customizado(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'config.json'
            p.write_text(json.dumps({'pasta_saida': 'D:/Musicas',
                'template_organizacao': '{artista}/{artista} - {titulo}.mp3',
                'fontes_capa': ['itunes']}))
            cfg = Config(p)
            self.assertEqual(cfg.get('template_organizacao'), '{artista}/{titulo}.mp3')
            self.assertEqual(cfg.get('pasta_saida'), 'D:/Musicas')
            self.assertEqual(cfg.get('fontes_capa'), ['itunes'])
            meta = TrackMeta(titulo='The Trooper', artista='Iron Maiden', album='Piece of Mind')
            self.assertEqual(aplicar_template(cfg.get('template_organizacao'), meta),
                             'Iron Maiden/The Trooper.mp3')
            self.assertEqual(meta.album, 'Piece of Mind')
            p.write_text(json.dumps({'template_organizacao': '{artista}/{album}/{titulo}.mp3'}))
            self.assertEqual(Config(p).get('template_organizacao'), '{artista}/{album}/{titulo}.mp3')

    def test_novo_padrao_e_nome_do_arquivo(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = Config(Path(d) / 'config.json')
            self.assertEqual(cfg.get('template_organizacao'), '{artista}/{titulo}.mp3')
            meta = TrackMeta(titulo='War Pigs', artista='Black Sabbath', album='Paranoid')
            self.assertEqual(aplicar_template(cfg.get('template_organizacao'), meta),
                             'Black Sabbath/War Pigs.mp3')


class CapasDeSingle(unittest.TestCase):
    def test_itunes_marca_somente_sufixo_explicito_de_single(self):
        def item(nome, faixa='Canção'):
            return {'trackName':faixa, 'artistName':'Pessoa', 'collectionName':nome,
                    'artworkUrl100':f'https://example.com/{nome}/100x100bb.jpg'}
        with patch.object(itunes, 'buscar', return_value=[item('Disco'), item('Canção - Single'),
                                                          item('Outra - Single','Outra')]):
            capas = provedores.apple_music('Canção', 'Pessoa')
        self.assertEqual(len(capas), 2)
        self.assertEqual(capas[0].extra['tipo_lancamento'], '')
        self.assertEqual(capas[1].extra['tipo_lancamento'], 'single')

    def test_itunes_busca_singles_apos_muitos_albuns_e_faz_fallback_brasil(self):
        def item(nome):
            return {'trackName': 'Paradise City', 'artistName': 'Guns N Roses',
                    'collectionName': nome,
                    'artworkUrl100': f'https://example.com/{nome}/100x100bb.jpg'}
        albuns = [item('Disco' + str(i)) for i in range(12)]
        def buscar(_consulta, limite=10, pais='US', entidade='song'):
            return albuns if pais == 'US' else [item('Paradise City - Single')]
        with patch.object(itunes, 'buscar', side_effect=buscar) as consulta:
            capas = provedores.apple_music('Paradise City', 'Guns N Roses')
        self.assertEqual([c.kwargs['pais'] for c in consulta.call_args_list], ['US', 'BR'])
        self.assertTrue(any(c.extra['tipo_lancamento'] == 'single' for c in capas))
        self.assertTrue(all(c.extra['tipo_lancamento'] != 'single' for c in capas[:12]))

    def test_itunes_busca_ambos_paises_mesmo_com_single_nos_eua(self):
        def buscar(_consulta, limite=10, pais='US', entidade='song'):
            return [{'trackName':'Canção', 'artistName':'Pessoa',
                     'collectionName':'Canção - Single',
                     'artworkUrl100':f'https://example.com/{pais}/100x100bb.jpg'}]
        with patch.object(itunes, 'buscar', side_effect=buscar) as consulta:
            capas = provedores.apple_music('Canção', 'Pessoa')
        self.assertEqual([c.kwargs['pais'] for c in consulta.call_args_list], ['US', 'BR'])
        self.assertEqual(len(capas), 2)
        self.assertTrue(all(c.extra['tipo_lancamento'] == 'single' for c in capas))

    def test_deezer_prioriza_detalhes_do_nome_da_musica_sem_inventar_tipo(self):
        def item(i, nome):
            return {'title':'Paradise City', 'artist':{'name':'Guns N Roses'},
                    'album':{'id':i,'title':nome, 'cover_xl':f'https://example.com/{i}'}}
        data = {'data':[item(i, 'Álbum '+str(i)) for i in range(1, 6)] + [item(6, 'Paradise City')]}
        def get(url, *args, **kwargs):
            if '/search?' in url: return data
            return {'record_type': 'single' if url.endswith('/6') else 'album'}
        with patch.object(provedores, '_get_json', side_effect=get) as chamadas:
            capas = provedores.deezer('Paradise City', 'Guns N Roses')
        detalhes = [c.args[0] for c in chamadas.call_args_list if '/album/' in c.args[0]]
        self.assertTrue(detalhes[0].endswith('/6'))
        self.assertEqual(capas[0].extra['tipo_lancamento'], 'single')
        self.assertLessEqual(len(detalhes), 4)

    def test_deezer_tipo_confirmado_e_ausente_sem_inventar(self):
        data = {'data':[{'title':'Canção', 'artist':{'name':'Pessoa'},
                'album':{'id':1,'title':'Disco','cover_xl':'https://example.com/a'}},
                {'title':'Canção', 'artist':{'name':'Pessoa'},
                 'album':{'id':2,'title':'Single','cover_xl':'https://example.com/b'}},
                {'title':'Canção', 'artist':{'name':'Pessoa'},
                 'album':{'id':3,'title':'Incerto','cover_xl':'https://example.com/c'}}]}
        def get(url, *args, **kwargs):
            if '/search?' in url: return data
            if url.endswith('/1'): return {'record_type':'album'}
            if url.endswith('/2'): return {'record_type':'single'}
            return None
        with patch.object(provedores, '_get_json', side_effect=get):
            capas = provedores.deezer('Canção', 'Pessoa')
        self.assertEqual([x.extra['tipo_lancamento'] for x in capas], ['album', 'single', ''])

    def test_musicbrainz_escolhe_single_e_ignora_album(self):
        dados = {'recordings':[{'title':'Canção', 'score':100,
            'artist-credit':[{'name':'Pessoa'}],
            'releases':[{'id':'album-id','title':'Disco','release-group':{'primary-type':'Album'}},
                        {'id':'single-id','title':'Canção','release-group':{'primary-type':'Single'}}]}]}
        with patch.object(musicbrainz, '_get', return_value=dados):
            singles = musicbrainz.buscar_gravacao('Canção','Pessoa', somente_single=True)
        self.assertEqual([x['release_id'] for x in singles], ['single-id'])
        self.assertEqual(singles[0]['tipo_lancamento'], 'Single')
        with patch.object(musicbrainz, 'buscar_gravacao', return_value=singles) as busca, \
             patch.object(musicbrainz, 'capas_release', return_value=[{'url':'https://example.com', 'frontal':True}]):
            capa = musicbrainz.melhor_capa('Canção', 'Pessoa', somente_single=True)
        self.assertEqual(capa['tipo_lancamento'], 'Single')
        self.assertTrue(busca.call_args.kwargs['somente_single'])

    def test_caa_traz_edicoes_singles_e_varias_frontais_sem_albuns(self):
        def rel(ident, tipo):
            return {'id': ident, 'title': 'Canção',
                    'release-group': {'id': 'g-' + ident, 'primary-type': tipo}}
        dados = {'recordings': [{'title': 'Canção', 'score': 100,
                 'artist-credit': [{'name': 'Pessoa'}],
                 'releases': [rel('album', 'Album'), rel('single1', 'Single'),
                              rel('single2', 'Single'), rel('incerto', '')]}]}
        def imagens(release_id='', release_group=''):
            if release_id == 'single1':
                return [{'url':'https://example.com/front1', 'frontal':True, 'tipos':['Front']},
                        {'url':'https://example.com/back', 'frontal':False, 'tipos':['Back']},
                        {'url':'https://example.com/front2', 'frontal':True, 'tipos':['Front']}]
            return [{'url':'https://example.com/front3', 'frontal':True, 'tipos':['Front']}]
        with patch.object(musicbrainz, '_get', return_value=dados), \
             patch.object(musicbrainz, 'capas_release', side_effect=imagens) as chamadas:
            capas = provedores.caa_busca('Canção', 'Pessoa')
        self.assertEqual({c.url for c in capas}, {'https://example.com/front1',
                         'https://example.com/front2', 'https://example.com/front3'})
        self.assertEqual({c.extra['tipo_lancamento'] for c in capas}, {'single'})
        self.assertEqual({c.kwargs['release_id'] for c in chamadas.call_args_list}, {'single1', 'single2'})

    def test_caa_respeita_limite_e_descarta_tipo_e_confianca_incorretos(self):
        registros = [dict(release_id=str(i), titulo='Canção', artista='Pessoa',
                          tipo_lancamento='Single', confianca=1) for i in range(9)]
        registros[0]['tipo_lancamento'] = 'Album'
        registros[1]['confianca'] = .2
        with patch.object(musicbrainz, 'buscar_gravacao', return_value=registros), \
             patch.object(provedores.coverartarchive, 'imagens', return_value=[]) as imagens:
            self.assertEqual(provedores.caa_busca('Canção','Pessoa'), [])
        self.assertEqual(imagens.call_count, 4)

    def test_sem_single_nao_faz_fallback_para_album_nem_thumb(self):
        album = provedores.Capa(url='https://example.com/album', titulo='Canção', artista='Pessoa',
                                album='Disco', extra={'tipo_lancamento':'album'})
        desconhecido = provedores.Capa(url='https://example.com/incerto', titulo='Canção', artista='Pessoa')
        with patch.object(provedores, 'apple_music', return_value=[album, desconhecido]), \
             patch.object(provedores, 'miniatura') as thumb, \
             patch.object(busca_capas, '_obter_imagem') as baixar:
            capa = covers.encontrar_capa('Canção', 'Pessoa', 'Disco', fontes=['itunes'],
                                         thumb_extra='https://example.com/thumbnail', usar_miniatura=True)
        self.assertFalse(capa.ok)
        self.assertIn('Nenhuma capa de single', capa.observacao)
        thumb.assert_not_called()
        baixar.assert_not_called()

    def test_single_diferente_da_faixa_nao_e_aprovado(self):
        class Valida:
            ok=True; largura=500; altura=500; hash='h'; motivo=''
        c = provedores.Capa(url='https://example.com/a', titulo='Outra', artista='Pessoa',
                            album='Outra - Single', extra={'tipo_lancamento':'single'})
        with patch.object(provedores, 'apple_music', return_value=[c]), \
             patch.object(busca_capas, '_obter_imagem', return_value=('capa.jpg', b'fake')), \
             patch.object(busca_capas.capa_validacao, 'validar', return_value=Valida()):
            aprovadas, reprovadas = busca_capas.coletar('Canção','Pessoa','Disco',fontes=['itunes'])
        self.assertEqual(aprovadas, [])
        self.assertEqual(len(reprovadas), 1)

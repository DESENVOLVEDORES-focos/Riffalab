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

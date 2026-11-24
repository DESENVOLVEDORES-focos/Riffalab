"""Álbuns e singles para revisão, com comparação conservadora de identidade."""
import unittest
from unittest.mock import patch
from app.metadata import busca_capas, covers, itunes, provedores, musicbrainz
from app.models import CoverResult


class CapasAlbumSingle(unittest.TestCase):
    @staticmethod
    def item(album, titulo='Bohemian Rhapsody', artista='Queen', url='https://example.test/100x100bb.jpg'):
        return {'trackName': titulo, 'artistName': artista, 'collectionName': album,
                'collectionType': 'Album', 'artworkUrl100': url}

    def coletar_itunes(self, itens, album='A Night at the Opera', modo=True):
        class Valida:
            ok=True; largura=500; altura=500; hash='mesma-imagem'; motivo=''
        with patch.object(itunes, 'buscar', return_value=itens), \
             patch.object(busca_capas, '_obter_imagem', return_value=('capa.jpg', b'imagem')), \
             patch.object(busca_capas.capa_validacao, 'validar', return_value=Valida()):
            return covers.encontrar_capa('Bohemian Rhapsody', 'Queen', album,
                    fontes=['itunes'], incluir_albuns_para_revisao=modo)

    def test_album_e_single_mesma_imagem_permanecem_opcoes_diferentes(self):
        dados = [self.item('A Night at the Opera'), self.item('Bohemian Rhapsody - Single')]
        capa = self.coletar_itunes(dados)
        opcoes = [capa] + capa.alternativas
        self.assertEqual({x.tipo_lancamento for x in opcoes}, {'colecao','single'})
        self.assertEqual({x.album for x in opcoes}, {'A Night at the Opera','Bohemian Rhapsody - Single'})

    def test_artista_semelhante_e_reprovado_mesmo_se_nome_da_musica_bate(self):
        dados = [self.item('A Night at the Opera', artista='Queensrÿche')]
        capa = self.coletar_itunes(dados)
        self.assertFalse(capa.ok)
        self.assertIn('correspondência', capa.observacao)

    def test_titulo_parcial_nao_e_a_mesma_faixa(self):
        album = provedores.Capa(url='x', titulo='One More Time', artista='Queen', album='Disco',
                                extra={'tipo_lancamento':'album'})
        self.assertFalse(busca_capas._identidade_estrita('One', 'Queen', album))
        self.assertFalse(busca_capas._identidade_estrita('Canção', 'Queen',
            provedores.Capa(titulo='Canção', artista='Queen of Muppets')))
        self.assertTrue(busca_capas._identidade_estrita('Bohemian Rhapsody', 'Queen',
            provedores.Capa(titulo='Bohemian Rhapsody - 2011 Remaster', artista='Queen')))

    def test_album_diferente_do_informado_aparece_com_aviso_e_single_tambem(self):
        dados = [self.item('Uma Coletânea'), self.item('Bohemian Rhapsody - Single')]
        capa = self.coletar_itunes(dados)
        self.assertTrue(capa.ok)
        opcoes = [capa] + capa.alternativas
        self.assertEqual({x.tipo_lancamento for x in opcoes}, {'colecao', 'single'})
        self.assertTrue(any('Álbum diferente' in x.observacao for x in opcoes))
        self.assertTrue(busca_capas._album_compativel('A Night at the Opera', 'A Night at the Opera (Deluxe Edition)'))
        self.assertFalse(busca_capas._album_compativel('A Night at the Opera','News of the World'))

    def test_modo_sem_revisao_nao_escolhe_album_automaticamente(self):
        capa = self.coletar_itunes([self.item('A Night at the Opera')], modo=False)
        self.assertFalse(capa.ok)
        self.assertIn('single', capa.observacao)

    def test_caa_album_exige_tipo_album_e_mantem_creditos_da_faixa(self):
        entrada = {'titulo':'Bohemian Rhapsody', 'artista':'Queen', 'confianca':.95,
                   'album':'A Night at the Opera', 'tipo_lancamento':'Album',
                   'release_id':'r', 'release_group':'g', 'ano':1975}
        with patch.object(musicbrainz, 'buscar_gravacao', return_value=[entrada]), \
             patch.object(provedores.coverartarchive, 'imagens', return_value=[{'url':'https://example.test/front'}]):
            capas = provedores.caa_albuns('Bohemian Rhapsody','Queen','A Night at the Opera')
        self.assertEqual(len(capas),1)
        self.assertEqual(capas[0].extra['tipo_lancamento'],'album')
        self.assertEqual((capas[0].titulo,capas[0].artista), ('Bohemian Rhapsody','Queen'))

    def test_musicbrainz_lista_todos_os_albuns_da_gravacao(self):
        def release(ident, nome, tipo):
            return {'id':ident, 'title':nome, 'release-group':{'id':ident+'g', 'primary-type':tipo}}
        dados = {'recordings':[{'title':'Bohemian Rhapsody', 'score':100,
                   'artist-credit':[{'name':'Queen'}], 'releases':[
                       release('s','Single','Single'), release('a','Álbum A','Album'),
                       release('b','Álbum B','Album')]}]}
        with patch.object(musicbrainz, '_get', return_value=dados):
            achados = musicbrainz.buscar_gravacao('Bohemian Rhapsody','Queen', todos_albuns=True)
        self.assertEqual({a['release_id'] for a in achados}, {'a','b'})

    def test_itunes_collection_type_sozinho_nao_confirma_album(self):
        capa = self.coletar_itunes([self.item('Nome sem Single')], album='')
        self.assertEqual(capa.tipo_lancamento, 'colecao')

    def test_um_provedor_falhar_nao_apaga_resultado_de_outro(self):
        item = self.item('Bohemian Rhapsody - Single')
        class Valida:
            ok=True; largura=500; altura=500; hash='imagem'; motivo=''
        with patch.object(itunes, 'buscar', return_value=[item]), \
             patch.object(provedores, 'caa_busca', side_effect=RuntimeError('503')), \
             patch.object(busca_capas, '_obter_imagem', return_value=('capa.jpg',b'dados')), \
             patch.object(busca_capas.capa_validacao, 'validar', return_value=Valida()):
            capa = covers.encontrar_capa('Bohemian Rhapsody','Queen', fontes=['itunes','coverartarchive'],
                                        incluir_albuns_para_revisao=True)
        self.assertTrue(capa.ok)
        self.assertEqual(capa.tipo_lancamento, 'single')

if __name__ == '__main__': unittest.main()

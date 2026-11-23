"""A URL igual para álbum e single não pode ocultar a evidência do single."""
import unittest
from unittest.mock import patch
from app.metadata import busca_capas, covers, itunes, provedores


class SingleDuplicado(unittest.TestCase):
    @staticmethod
    def item(album, titulo='Canção', artista='Pessoa', url='https://example.test/100x100bb.jpg'):
        return {'trackName': titulo, 'artistName': artista, 'collectionName': album,
                'artworkUrl100': url}

    def test_album_primeiro_nao_descarta_single_com_igual_imagem(self):
        album, single = self.item('Disco'), self.item('Canção - Single')
        with patch.object(itunes, 'buscar', return_value=[album, single]):
            capas = provedores.apple_music('Canção', 'Pessoa')
        self.assertEqual(len(capas), 1)
        self.assertEqual(capas[0].album, 'Canção - Single')
        self.assertEqual(capas[0].extra['tipo_lancamento'], 'single')

    def test_single_primeiro_nao_e_substituido_por_album(self):
        with patch.object(itunes, 'buscar', return_value=[self.item('Canção - Single'), self.item('Disco')]):
            capas = provedores.apple_music('Canção', 'Pessoa')
        self.assertEqual(len(capas), 1)
        self.assertEqual(capas[0].extra['tipo_lancamento'], 'single')

    def test_single_errado_nao_substitui_album_correto(self):
        with patch.object(itunes, 'buscar', return_value=[self.item('Disco'), self.item('Outra - Single', titulo='Outra')]):
            capas = provedores.apple_music('Canção', 'Pessoa')
        self.assertEqual(len(capas), 1)
        self.assertEqual(capas[0].extra['tipo_lancamento'], '')

    def test_single_real_chega_a_etapa_de_escolha_sem_liberar_album(self):
        class Valida:
            ok=True; largura=500; altura=500; hash='mesma-imagem'; motivo=''
        album, single = self.item('Disco'), self.item('Canção - Single')
        with patch.object(itunes, 'buscar', return_value=[album, single]), \
             patch.object(busca_capas, '_obter_imagem', return_value=('capa.jpg', b'dados')), \
             patch.object(busca_capas.capa_validacao, 'validar', return_value=Valida()):
            capa = covers.encontrar_capa('Canção', 'Pessoa', fontes=['itunes'])
        self.assertTrue(capa.ok)
        self.assertEqual(capa.album, 'Canção - Single')
        with patch.object(itunes, 'buscar', return_value=[album]), \
             patch.object(busca_capas, '_obter_imagem') as obter:
            capa = covers.encontrar_capa('Canção', 'Pessoa', fontes=['itunes'])
        self.assertFalse(capa.ok); obter.assert_not_called()
        self.assertIn('1 sem confirmação de single', capa.observacao)

if __name__ == '__main__': unittest.main()

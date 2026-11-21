"""Leitura de MP3s sem modificar músicas nem utilizar imagens externas."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mutagen.id3 import APIC, ID3, TALB, TIT2, TPE1

from app import tagging, visualizador_mp3 as v


def mp3_com_tags(caminho, com_capa=True):
    caminho.write_bytes(b'')
    tags = ID3()
    tags.add(TIT2(encoding=3, text='Paradise City'))
    tags.add(TPE1(encoding=3, text='Guns N Roses'))
    tags.add(TALB(encoding=3, text='Disco'))
    if com_capa:
        tags.add(APIC(encoding=3, mime='image/jpeg', type=4, desc='verso', data=b'verso'))
        tags.add(APIC(encoding=3, mime='image/png', type=3, desc='frente', data=b'frente'))
    tags.save(str(caminho), v2_version=3)


class VisualizadorMP3(unittest.TestCase):
    def test_leitura_capa_frontal_multiplas_tags_sem_alterar_arquivo(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'musica.mp3'
            mp3_com_tags(p)
            antes = hashlib.sha256(p.read_bytes()).hexdigest()
            item = v.ler_mp3(p, incluir_imagens=True)
            self.assertEqual((item['titulo'], item['artista'], item['album']), ('Paradise City', 'Guns N Roses', 'Disco'))
            self.assertEqual(item['quantidade'], 2)
            self.assertEqual([a['dados'] for a in item['imagens']], [b'frente', b'verso'])
            self.assertEqual(antes, hashlib.sha256(p.read_bytes()).hexdigest())

    def test_pasta_subpastas_sem_capa_sem_tags_erro_e_indisponivel(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d); (p / 'artista').mkdir()
            mp3_com_tags(p / 'artista' / 'com.MP3')
            mp3_com_tags(p / 'sem.mp3', False)
            (p / 'sem_tags.mp3').write_bytes(b'arquivo sem ID3')
            (p / 'ignorar.wav').write_bytes(b'')
            itens = v.listar_mp3(p)['itens']
            self.assertEqual(len(itens), 3)
            por_nome = {Path(x['caminho']).name: x for x in itens}
            self.assertEqual(por_nome['com.MP3']['quantidade'], 2)
            self.assertEqual(por_nome['sem.mp3']['estado'], 'Sem imagem ID3')
            self.assertEqual(por_nome['sem_tags.mp3']['estado'], 'Sem tags ID3')
            self.assertEqual(v.ler_mp3(p / 'nao_existe.mp3')['estado'], 'Erro de leitura')
            with self.assertRaises(ValueError): v.listar_mp3(p / 'inexistente')

    def test_nao_oculta_erro_ao_remover_capa_e_verifica_apic(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'musica.mp3'; mp3_com_tags(p)
            with self.assertRaises(RuntimeError): tagging.garantir_sem_capa(p)
            with patch('mutagen.id3.ID3.save', side_effect=PermissionError('sem permissão')):
                with self.assertRaises(PermissionError): tagging.remover_capa(p)
            self.assertEqual(v.ler_mp3(p)['quantidade'], 2)
            tagging.remover_capa(p)
            tagging.garantir_sem_capa(p)
            self.assertEqual(v.ler_mp3(p)['quantidade'], 0)
            self.assertEqual(str(ID3(str(p))['TIT2']), 'Paradise City')

    def test_imagem_grande_ou_imagem_invalidada_e_identificada_sem_silencio(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'musica.mp3'; mp3_com_tags(p)
            with patch.object(v, 'MAX_IMAGEM', 4):
                item = v.ler_mp3(p, incluir_imagens=True)
            self.assertEqual(item['quantidade'], 2)
            self.assertEqual(item['imagens'][0]['dados'], b'')
            self.assertEqual(item['imagens'][0]['tamanho'], 6)


if __name__ == '__main__':
    unittest.main()

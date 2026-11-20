"""Regressões da marca ID3 e conferência de arquivos locais."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mutagen.id3 import COMM, ID3, TALB, TIT2, TPE1
from app import arquivos_baixados
from app.models import TrackResult


def criar_mp3(path, titulo='Canção', artista='Artista', comentario=None):
    # Um arquivo de tags basta para testar ID3; o pipeline é testado à parte com áudio real.
    path.parent.mkdir(parents=True, exist_ok=True)
    tags = ID3()
    tags.add(TIT2(encoding=3, text=titulo))
    tags.add(TPE1(encoding=3, text=artista))
    tags.add(TALB(encoding=3, text='Disco'))
    if comentario:
        tags.add(COMM(encoding=3, lang='eng', desc='', text=comentario))
    tags.save(str(path), v2_version=3)


class ArquivosBaixados(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.resultado = TrackResult('ytdlpid:123', 'ytdlp', 'Canção', 'Artista')

    def test_marca_mp3_preserva_outras_tags_e_substitui_id_antigo(self):
        p = self.base / 'um.mp3'
        criar_mp3(p, comentario='Comentário pessoal')
        arquivos_baixados.marcar(p, self.resultado)
        tags = ID3(p)
        self.assertEqual(str(tags['TIT2']), 'Canção')
        self.assertEqual(str(tags['TALB']), 'Disco')
        self.assertEqual(str(tags['COMM::eng']), 'Comentário pessoal')
        self.assertEqual(str(tags['COMM:RiffLab:eng']), 'RiffLab')
        self.assertEqual(str(tags['TXXX:RiffLab:id']), 'ytdlpid:123')
        arquivos_baixados.marcar(p, TrackResult('', 'ytdlp', 'Outra', 'Outro'))
        self.assertNotIn('TXXX:RiffLab:id', ID3(p))
        self.assertEqual(str(ID3(p)['COMM::eng']), 'Comentário pessoal')

    def test_recursivo_movido_diferenciar_id_e_possivel(self):
        p = self.base / 'biblioteca' / 'artista' / 'disco' / 'outro nome.MP3'
        criar_mp3(p)
        arquivos_baixados.marcar(p, self.resultado)
        self.assertEqual(str(ID3(p)['COMM::eng']), 'RiffLab')
        antes = p.read_bytes()
        outros = [self.resultado, TrackResult('diferente', 'outra', 'Canção', 'Artista'),
                  TrackResult('nada', 'outra', 'Canção', 'Outros'),
                  TrackResult('nada', 'outra', 'Outra', 'Artista')]
        ret = arquivos_baixados.conferir(outros, [str(self.base)])
        self.assertEqual(ret['correspondencias'][0], {'tipo': 'id', 'caminho': str(p)})
        self.assertEqual(ret['correspondencias'][1], {'tipo': 'possivel', 'caminho': str(p)})
        self.assertEqual(ret['correspondencias'][2:], [None, None])
        self.assertEqual(antes, p.read_bytes())
        novo = self.base / 'movidos' / 'novo nome.mp3'
        novo.parent.mkdir(); p.rename(novo)
        ret = arquivos_baixados.conferir([self.resultado], [str(self.base)])
        self.assertEqual(ret['correspondencias'][0]['caminho'], str(novo))

    def test_apenas_marcados_e_outra_pasta(self):
        normal = self.base / 'saida' / 'normal.mp3'
        criar_mp3(normal, comentario='não é RiffLab')
        manual = self.base / 'extra' / 'sub' / 'manual.mp3'
        criar_mp3(manual, comentario='RiffLab')
        self.assertIsNone(arquivos_baixados.conferir([self.resultado], [str(normal.parent)])['correspondencias'][0])
        achado = arquivos_baixados.conferir([self.resultado], [str(normal.parent), str(self.base / 'extra')])
        self.assertEqual(achado['correspondencias'][0]['tipo'], 'possivel')
        self.assertEqual(achado['correspondencias'][0]['caminho'], str(manual))

    def test_raiz_inexistente_indica_verificacao_incompleta(self):
        ret = arquivos_baixados.conferir([self.resultado], [str(self.base / 'nao existe')])
        self.assertTrue(ret['erros'])
        self.assertEqual(ret['correspondencias'], [None])

    def test_sem_identidade_nao_gera_correspondencia_falsa(self):
        p = self.base / 'a.mp3'
        criar_mp3(p, titulo='Outra', artista='Outro')
        arquivos_baixados.marcar(p, TrackResult('ytdlpid:None', 'ytdlp', 'Outra', 'Outro'))
        r = TrackResult('ytdlpid:None', 'ytdlp', 'X', 'Y')
        self.assertIsNone(arquivos_baixados.conferir([r], [str(self.base)])['correspondencias'][0])

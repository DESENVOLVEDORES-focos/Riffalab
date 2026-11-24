"""Regressões do fluxo de seleção, preparação e lote sequencial."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from app import pipeline, preparacao
from app.config import Config
from app.downloader import GerenciadorFila
from app.models import AudioFormat, CoverResult, TrackMeta, TrackResult
from app.sources.local_library import FonteBibliotecaLocal
from app.sources.ytdlp import FonteYtDlp


class FluxoLote(unittest.TestCase):
    def test_preparar_nao_baixa_audio_nem_busca_api_de_capas(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = Config(Path(d) / 'config.json')
            r = TrackResult('1', 'ytdlp', 'Música', 'Artista')
            meta = TrackMeta(titulo='Música', artista='Artista')
            capa = CoverResult(caminho='capa.jpg', alternativas=[CoverResult(caminho='outra.jpg')])
            with patch.object(pipeline, 'montar_metadados', return_value=meta), \
                 patch.object(pipeline, 'buscar_capa', side_effect=AssertionError('buscou capa')), \
                 patch.object(pipeline, 'processar_resultado', side_effect=AssertionError('baixou áudio')):
                dados = preparacao.preparar_musica(r, cfg)
            self.assertIs(dados['meta'], meta)
            self.assertFalse(dados['capa'].ok)

    def test_fila_e_sequencial_mesmo_com_config_antiga(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = Config(Path(d) / 'config.json')
            cfg.dados['downloads_simultaneos'] = 4
            banco = Mock()
            banco.criar_download.side_effect = [1, 2, 3]
            fila = GerenciadorFila(cfg, banco)
            iniciados = []
            with patch.object(fila, '_iniciar', side_effect=lambda item: iniciados.append(item)):
                for i in range(3):
                    fila.adicionar(TrackResult(str(i), 'ytdlp', f'Música {i}'),
                                   preparacao={'capa': CoverResult()})
                self.assertEqual([x['resultado'].uid for x in iniciados], ['0'])
                fila._liberar()
                self.assertEqual([x['resultado'].uid for x in iniciados], ['0', '1'])
                fila._liberar()
                self.assertEqual([x['resultado'].uid for x in iniciados], ['0', '1', '2'])
                self.assertEqual(iniciados[1]['preparacao']['capa'].ok, False)

    def test_topic_preservado_para_priorizacao(self):
        import json
        with tempfile.TemporaryDirectory() as d:
            fonte = FonteYtDlp(Config(Path(d) / 'config.json'))
            payload = json.dumps({'entries': [{'id': 'abc', 'title': 'Artista - Música',
                                               'channel': 'Artista - Topic'}]})
            with patch.object(fonte, 'disponivel', return_value=(True, '')), \
                 patch.object(fonte, '_args_base', return_value=[]), \
                 patch.object(fonte, '_rodar', return_value=(0, payload, '')):
                r = fonte.buscar('Artista Música')[0]
            self.assertEqual(r.canal, 'Artista - Topic')
            self.assertEqual(r.artista, 'Artista')

    @unittest.skipUnless(shutil.which('ffmpeg'), 'ffmpeg não disponível')
    def test_pipeline_grava_escolha_e_nao_pesquisa_novamente(self):
        from mutagen.id3 import ID3
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            wav = base / 'som.wav'
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
                            'sine=frequency=440:duration=1', str(wav)], check=True)
            imagem = base / 'escolhida.png'
            imagem.write_bytes((Path(__file__).resolve().parents[1] / 'docs' / 'tela-pesquisa.png').read_bytes())
            cfg = Config(base / 'config.json')
            cfg.dados.update(pasta_saida=str(base / 'saida'), gravar_tags=False,
                             incorporar_capa=False, ia_ativa=False)
            fmt = AudioFormat(codec='wav', url=str(wav), lossless=True)
            fonte = FonteBibliotecaLocal(cfg)
            for titulo, capa in [('Com capa', CoverResult(caminho=str(imagem), fonte='teste')),
                                  ('Sem capa', CoverResult(observacao='sem capa'))]:
                r = TrackResult(titulo, 'biblioteca_local', titulo, 'Artista', formatos=[fmt])
                meta = TrackMeta(titulo=titulo, artista='Artista', album='Álbum de teste', capa='anterior.jpg')
                with patch.object(pipeline, 'PASTA_TEMP', base / 'temp'), \
                     patch.object(pipeline, 'buscar_capa', side_effect=AssertionError('busca repetida')), \
                     patch.object(pipeline, 'montar_metadados', side_effect=AssertionError('metadados repetidos')):
                    res = pipeline.processar_resultado(r, cfg, fonte=fonte,
                            preparacao={'meta': meta, 'capa': capa, 'ident': None})
                self.assertTrue(res['ok'], res)
                tags = ID3(res['caminho'])
                self.assertEqual(str(tags['TIT2']), titulo)
                self.assertEqual(str(tags['TALB']), 'Álbum de teste')
                self.assertEqual(Path(res['caminho']).relative_to(base / 'saida'), Path('Artista') / (titulo + '.mp3'))
                self.assertEqual(str(tags['COMM:RiffLab:eng']), 'RiffLab')
                self.assertEqual(str(tags['TXXX:RiffLab:id']), titulo)
                from app.arquivos_baixados import conferir
                achado = conferir([r], [str(base / 'saida')])['correspondencias'][0]
                self.assertEqual(achado['tipo'], 'id')
                self.assertEqual(achado['caminho'], res['caminho'])
                self.assertEqual(bool(tags.getall('APIC')), capa.ok)
                if capa.ok:
                    mp3_com_capa = res['caminho']
            # Uma origem MP3 copiada também precisa perder a capa anterior ao
            # escolher explicitamente "sem capa".
            fmt_mp3 = AudioFormat(codec='mp3', url=mp3_com_capa)
            r = TrackResult('sem-capa-mp3', 'biblioteca_local', 'Sem capa MP3',
                            'Artista', formatos=[fmt_mp3])
            with patch.object(pipeline, 'PASTA_TEMP', base / 'temp'):
                res = pipeline.processar_resultado(r, cfg, fonte=fonte,
                    preparacao={'meta': TrackMeta(titulo='Sem capa MP3', artista='Artista'),
                                'capa': CoverResult(), 'ident': None})
            self.assertTrue(res['ok'], res)
            self.assertFalse(ID3(res['caminho']).getall('APIC'))

    @unittest.skipUnless(shutil.which('ffmpeg'), 'ffmpeg não disponível')
    def test_sem_capa_nao_conclui_se_remocao_falha_ou_apic_continua(self):
        from mutagen.id3 import ID3, APIC
        with tempfile.TemporaryDirectory() as d:
            base = Path(d); origem = base / 'origem.mp3'
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
                            'sine=frequency=440:duration=0.5', str(origem)], check=True)
            try: tags = ID3(str(origem))
            except Exception: tags = ID3()
            tags.add(APIC(encoding=3, mime='image/jpeg', type=3, desc='frente', data=b'foto preexistente'))
            tags.save(str(origem), v2_version=3)
            original = origem.read_bytes()
            cfg = Config(base / 'config.json'); cfg.dados['pasta_saida'] = str(base / 'saida')
            fonte = FonteBibliotecaLocal(cfg)
            fmt = AudioFormat(codec='mp3', url=str(origem))
            r = TrackResult('id', 'biblioteca_local', 'Música', 'Artista', formatos=[fmt])
            def copiar_sem_remover(origem_, destino, **kwargs):
                shutil.copyfile(origem_, destino)
                return {'acao':'copiar', 'motivo':'teste'}
            for remocao in (PermissionError('sem permissão'), None):
                prep = {'meta':TrackMeta(titulo='Música', artista='Artista'),
                        'capa':CoverResult(observacao='sem capa'), 'ident':None}
                with patch.object(pipeline, 'PASTA_TEMP', base / 'temp'), \
                     patch.object(pipeline.convert, 'converter_para_mp3', side_effect=copiar_sem_remover), \
                     patch.object(pipeline.tagging, 'remover_capa', side_effect=remocao):
                    res = pipeline.processar_resultado(r, cfg, fonte=fonte, preparacao=prep)
                self.assertFalse(res['ok'], res)
                self.assertFalse((base / 'saida' / 'Artista' / 'Música.mp3').exists())
                self.assertEqual(origem.read_bytes(), original)
                self.assertTrue(ID3(str(origem)).getall('APIC'))

if __name__ == '__main__':
    unittest.main()

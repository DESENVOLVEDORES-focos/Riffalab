"""Persistência, listas, edição e repetição de downloads."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from app import estado_musicas, preparacao
from app.config import Config
from app.db import Banco
from app.downloader import GerenciadorFila
from app.models import AudioFormat, CoverResult, TrackMeta, TrackResult


class NovosFluxos(unittest.TestCase):
    def test_serializacao_reabre_formato_e_nao_guarda_url_de_stream_ytdlp(self):
        fmt = AudioFormat(codec='opus', format_id='251', url='https://stream.invalid/?token=segredo')
        r = TrackResult('id', 'ytdlp', 'Canção', 'Artista', pagina_url='https://youtube.com/watch?v=id',
                        formatos=[fmt], extra={'id': 'id', 'cookie': 'segredo'})
        salvo = estado_musicas.serializar_pedido({'resultado': r, 'formato': fmt})
        self.assertNotIn('segredo', str(salvo))
        restaurado = estado_musicas.desserializar_pedido(salvo)
        self.assertEqual(restaurado['resultado'].pagina_url, r.pagina_url)
        self.assertEqual(restaurado['formato'].format_id, '251')
        self.assertEqual(restaurado['formato'].url, '')
        self.assertEqual(restaurado['resultado'].formatos[0].format_id, '251')

    def test_listas_e_estado_sobrevivem_reabertura_sem_apagar_tabelas_antigas(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'banco.db'
            banco = Banco(path)
            banco.registrar_historico('pesquisa', 'Anterior')
            banco.salvar_estado('marcacoes', [{'a': 1}])
            banco.salvar_lista('Rock para o carro', [{'a': 2}])
            banco.fechar()
            banco = Banco(path)
            self.assertEqual(banco.ler_estado('marcacoes'), [{'a': 1}])
            self.assertEqual(banco.ler_lista('rock para o carro'), [{'a': 2}])
            self.assertEqual(banco.listar_historico()[0]['consulta'], 'Anterior')
            banco.apagar_lista('Rock para o carro')
            self.assertFalse(banco.nomes_listas())
            self.assertEqual(banco.ler_estado('marcacoes'), [{'a': 1}])
            banco.fechar()

    def test_preparacao_usa_identidade_editada_e_pula_busca_de_capa(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = Config(Path(d) / 'config.json')
            r = TrackResult('id', 'ytdlp', 'Título antigo', 'Artista antigo', album='Antigo')
            meta = TrackMeta(titulo='retorno', artista='retorno', album='retorno')
            with patch.object(preparacao.pipeline, 'montar_metadados', return_value=meta) as montar, \
                 patch.object(preparacao.pipeline, 'buscar_capa') as buscar:
                dados = preparacao.preparar_musica(r, cfg, edicao={'titulo': 'Novo', 'artista': 'Outro', 'album': ''},
                                                   sem_capa=True)
            self.assertEqual(montar.call_args.args[0].titulo, 'Novo')
            self.assertEqual(montar.call_args.args[0].artista, 'Outro')
            self.assertEqual(r.titulo, 'Título antigo')
            self.assertEqual((dados['meta'].titulo, dados['meta'].artista, dados['meta'].album), ('Novo', 'Outro', ''))
            self.assertFalse(dados['capa'].ok)
            buscar.assert_not_called()

    @unittest.skipUnless(shutil.which('ffmpeg'), 'ffmpeg não disponível')
    def test_dados_editados_chegam_ao_arquivo_e_tags_sem_capa(self):
        from app import pipeline
        from app.sources.local_library import FonteBibliotecaLocal
        from mutagen.id3 import ID3
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            origem = base / 'som.wav'
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
                            'sine=frequency=440:duration=0.5', str(origem)], check=True)
            cfg = Config(base / 'config.json')
            cfg.dados.update(pasta_saida=str(base / 'saida'), ia_ativa=False)
            fmt = AudioFormat(codec='wav', container='wav', url=str(origem), lossless=True)
            r = TrackResult('local-id', 'biblioteca_local', 'Original', 'Antigo', formatos=[fmt])
            edit = {'titulo': 'Título certo', 'artista': 'Artista certo', 'album': 'Álbum certo'}
            with patch.object(pipeline.covers, 'metadados_completos', return_value={}), \
                 patch.object(pipeline, 'PASTA_TEMP', base / 'temp'):
                prep = preparacao.preparar_musica(r, cfg, edicao=edit, sem_capa=True)
                resultado = pipeline.processar_resultado(r, cfg, fmt, fonte=FonteBibliotecaLocal(cfg),
                                                         preparacao=prep)
            self.assertTrue(resultado['ok'], resultado)
            self.assertEqual(Path(resultado['caminho']).relative_to(base / 'saida'),
                             Path('Artista certo') / 'Título certo.mp3')
            tags = ID3(resultado['caminho'])
            self.assertEqual((str(tags['TIT2']), str(tags['TPE1']), str(tags['TALB'])),
                             ('Título certo', 'Artista certo', 'Álbum certo'))
            self.assertFalse(tags.getall('APIC'))

    @unittest.skipUnless(shutil.which('ffmpeg'), 'ffmpeg não disponível')
    def test_album_vazio_apaga_tag_antiga_ao_processar_e_apos_reabrir(self):
        from dataclasses import asdict
        from app import pipeline
        from app.sources.local_library import FonteBibliotecaLocal
        from mutagen.id3 import ID3, TALB
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            origem = base / 'original.mp3'
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
                            'sine=frequency=440:duration=0.5', str(origem)], check=True)
            tags = ID3(str(origem))
            tags.add(TALB(encoding=3, text='Álbum antigo'))
            tags.save(str(origem), v2_version=3)
            cfg = Config(base / 'config.json')
            cfg.dados.update(pasta_saida=str(base / 'saida'), ia_ativa=False)
            fmt = AudioFormat(codec='mp3', container='mp3', url=str(origem))
            r = TrackResult('local-id', 'biblioteca_local', 'Música', 'Artista', formatos=[fmt])
            edit = {'titulo': 'Música', 'artista': 'Artista', 'album': ''}
            with patch.object(pipeline.covers, 'metadados_completos', return_value={}), \
                 patch.object(pipeline, 'PASTA_TEMP', base / 'temp'):
                prep = preparacao.preparar_musica(r, cfg, edicao=edit, sem_capa=True)
                # Representa os dados salvos pela versão anterior, sem apagar_tags.
                salvo = {'pedido': estado_musicas.serializar_pedido({'resultado':r, 'formato':fmt, 'edicao':edit}),
                         'marcada': True, 'preparacao': {'meta':asdict(prep['meta']),
                         'capa':asdict(prep['capa']), 'ident':None}}
                pedido, _, restaurada = estado_musicas.desserializar_selecao(salvo)
                self.assertEqual(restaurada['apagar_tags'], ['album'])
                resultado = pipeline.processar_resultado(pedido['resultado'], cfg, pedido['formato'],
                           fonte=FonteBibliotecaLocal(cfg), preparacao=restaurada)
            self.assertTrue(resultado['ok'], resultado)
            self.assertNotIn('TALB', ID3(resultado['caminho']))
            self.assertEqual(str(ID3(str(origem))['TALB']), 'Álbum antigo')

    @unittest.skipUnless(shutil.which('ffmpeg'), 'ffmpeg não disponível')
    def test_album_desconhecido_sem_edicao_nao_apaga_tag_original(self):
        from app import tagging
        from mutagen.id3 import ID3, TALB
        with tempfile.TemporaryDirectory() as d:
            origem = Path(d) / 'original.mp3'
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
                            'sine=frequency=440:duration=0.5', str(origem)], check=True)
            tags = ID3(str(origem))
            tags.add(TALB(encoding=3, text='Álbum conhecido'))
            tags.save(str(origem), v2_version=3)
            tagging.gravar(origem, TrackMeta(titulo='Música', artista='Artista', album=''))
            self.assertEqual(str(ID3(str(origem))['TALB']), 'Álbum conhecido')

    def test_repeticao_cria_novo_job_conservando_formato_e_preparacao(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = Config(Path(d) / 'config.json')
            cfg.dados['pasta_saida'] = str(Path(d) / 'saida')
            banco = Banco(Path(d) / 'banco.db')
            fila = GerenciadorFila(cfg, banco)
            r = TrackResult('id', 'ytdlp', 'Canção', 'Artista')
            fmt = AudioFormat(codec='opus', format_id='251')
            prep = {'meta': TrackMeta(titulo='Corrigido', artista='Artista'), 'capa': CoverResult(), 'ident': None}
            chamadas = []
            with patch.object(fila, '_iniciar', side_effect=lambda item: chamadas.append(item)):
                primeiro = fila.adicionar(r, fmt, preparacao=prep)
                fila._concluir(fila.jobs[primeiro], {'ok': False, 'erro': 'sem rede'})
                self.assertEqual(len(chamadas), 1)
                novo = fila.tentar_novamente(primeiro)
                self.assertNotEqual(primeiro, novo)
                self.assertIs(chamadas[1]['formato'], fmt)
                self.assertIs(chamadas[1]['preparacao'], prep)
                self.assertTrue(fila.jobs[primeiro]['nova_tentativa'])
                with self.assertRaises(ValueError):
                    fila.tentar_novamente(primeiro)
            banco.fechar()

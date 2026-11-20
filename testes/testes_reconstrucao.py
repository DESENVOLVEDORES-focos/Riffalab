"""Testes de regressão do fluxo principal, sem consultas à internet.

Execute: python -m unittest discover -s testes -p 'testes_reconstrucao.py'
O teste de conversão real requer ffmpeg no PATH e o pacote mutagen.
"""
from __future__ import annotations

import concurrent.futures
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import convert, cookies, pipeline, search_service, tools
from app.config import Config
from app.models import ArquivoInfo, AudioFormat, TrackResult
from app.sources.local_library import FonteBibliotecaLocal


class FluxoTestes(unittest.TestCase):
    def test_pastas_temporarias_sao_unicas(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(pipeline, 'PASTA_TEMP', Path(temp)):
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
                pastas = list(pool.map(pipeline._pasta_temp, ['mesmo-video'] * 20))
            self.assertEqual(len(set(pastas)), 20)
            self.assertTrue(all(p.is_dir() for p in pastas))

    def test_mp3_sem_bitrate_e_copiado(self):
        info = ArquivoInfo(caminho='origem.mp3', codec='mp3', bitrate_kbps=None)
        self.assertEqual(convert.planejar(info)['acao'], 'copiar')

    def test_cookies_httponly_sao_reconhecidos(self):
        with tempfile.TemporaryDirectory() as temp:
            caminho = Path(temp) / 'cookies.txt'
            caminho.write_text('# Netscape HTTP Cookie File\n#HttpOnly_.example.invalid\tTRUE\t/\tTRUE\t0\tnome\tvalor\n')
            status = cookies.verificar(caminho)
            self.assertTrue(status.utilizavel)
            self.assertEqual(status.cookies_validos, 1)

    def test_versao_ytdlp_usa_opcao_correta(self):
        resposta = subprocess.CompletedProcess([], 0, stdout='2026.11.19\n', stderr='')
        with patch.object(tools.subprocess, 'run', return_value=resposta) as executar:
            versao, erro = tools._versao('yt-dlp.exe')
        self.assertEqual(versao, '2026.11.19')
        self.assertEqual(erro, '')
        self.assertEqual(executar.call_args.args[0], ['yt-dlp.exe', '--version'])

    def test_pesquisa_preserva_videos_distintos(self):
        class FonteFalsa:
            nome = 'yt-dlp'
            def disponivel(self):
                return True, ''
            def buscar(self, consulta, limite):
                return [TrackResult(uid=uid, fonte='ytdlp', titulo='Mesma música',
                                    artista='Artista', duracao_s=210)
                        for uid in ('video1', 'video2', 'video1')]
            def enriquecer(self, *args, **kwargs):
                raise AssertionError('A verificação automática foi desativada')

        with tempfile.TemporaryDirectory() as temp:
            config = Config(Path(temp) / 'config.json')
            config.dados['verificar_automatico'] = 0
            config.dados['evitar_ao_vivo'] = False
            with patch.object(search_service, 'todas_as_fontes', return_value={'ytdlp': FonteFalsa()}):
                retorno = search_service.pesquisar('Mesma música', config)
            self.assertEqual({r.uid for r in retorno['resultados']}, {'video1', 'video2'})
            self.assertEqual(len(retorno['resultados']), 2)

    @unittest.skipUnless(shutil.which('ffmpeg'), 'ffmpeg não disponível no PATH')
    def test_conversao_local_completa(self):
        try:
            from mutagen.id3 import ID3
        except ImportError:
            self.skipTest('mutagen não instalado')
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            origem = base / 'origem.wav'
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
                            'sine=frequency=440:duration=1', str(origem)], check=True)
            config = Config(base / 'config.json')
            config.dados.update(pasta_saida=str(base / 'saida'), baixar_capa=False,
                                gravar_tags=True, ia_ativa=False)
            formato = AudioFormat(codec='wav', container='wav', url=str(origem), lossless=True)
            resultado = TrackResult(uid='local:1', fonte='biblioteca_local',
                                    titulo='Teste', artista='Artista', formatos=[formato])
            with patch.object(pipeline, 'PASTA_TEMP', base / 'temporarios'), \
                 patch.object(pipeline.covers, 'metadados_completos', return_value={}):
                resposta = pipeline.processar_resultado(resultado, config,
                                                        fonte=FonteBibliotecaLocal(config))
            self.assertTrue(resposta['ok'], resposta)
            mp3 = Path(resposta['caminho'])
            self.assertTrue(mp3.is_file())
            self.assertEqual(str(ID3(str(mp3))['TIT2']), 'Teste')
            self.assertEqual(str(ID3(str(mp3))['TPE1']), 'Artista')
            self.assertEqual(list((base / 'temporarios').iterdir()), [])

    def test_erro_limpa_arquivos_parciais(self):
        class FonteComFalha:
            nome = 'teste'
            def baixar(self, resultado, formato, destino, progresso):
                (destino.parent / 'parcial.part').write_text('parcial')
                raise RuntimeError('falha simulada')
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            config = Config(base / 'config.json')
            resultado = TrackResult(uid='falha', fonte='teste', titulo='Teste',
                                    formatos=[AudioFormat(codec='mp3')])
            with patch.object(pipeline, 'PASTA_TEMP', base / 'temporarios'):
                resposta = pipeline.processar_resultado(resultado, config, fonte=FonteComFalha())
            self.assertFalse(resposta['ok'])
            self.assertEqual(list((base / 'temporarios').iterdir()), [])


if __name__ == '__main__':
    unittest.main()

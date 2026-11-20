"""Comparação de formatos sem presumir dados técnicos ausentes."""
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
import unittest

from app.formatos_detalhes import campos
from app.metadata.consulta_formatos import consultar
from app.models import AudioFormat, TrackResult
from app.quality import pontuar
from app.sources.ytdlp import FonteYtDlp, _aviso_extracao


class DetalhesAudio(unittest.TestCase):
    def test_campos_conhecidos_sem_confundir_total_com_bitrate_de_audio(self):
        fmt = AudioFormat(codec='aac', format_id='301', container='m4a',
                          extra={'metodos':['JSON -j'], 'detalhes_audio':{
                              'acodec':'mp4a.40.2', 'vcodec':'avc1.640',
                              'tbr': 1234.56, 'asr': 48000, 'audio_channels':2,
                              'filesize_approx': 1048576, 'language':'pt-BR',
                              'protocol':'https', 'has_drm':False}})
        d = campos(fmt)
        self.assertEqual(d['Bitrate áudio'], 'não informado')
        self.assertEqual(d['Bitrate total'], '1234.56 kbps')
        self.assertEqual(d['Codec'], 'AAC (mp4a.40.2)')
        self.assertEqual(d['Amostragem'], '48000 Hz')
        self.assertEqual(d['Canais'], '2 (estéreo)')
        self.assertEqual(d['Tipo'], 'Áudio + vídeo')
        self.assertIn('aproximado', d['Tamanho'])
        self.assertEqual(d['Proteção DRM'], 'não')
        self.assertEqual(d['Métodos'], 'JSON -j')
        self.assertEqual(d['Bits por amostra'], 'não informado')
        self.assertLess(pontuar(fmt), pontuar(AudioFormat(codec='opus', bitrate_kbps=156)))

    def test_taxa_exata_e_arredondada_preservam_a_informada(self):
        fonte = FonteYtDlp()
        r = TrackResult('1', 'ytdlp', 'musica', pagina_url='https://example.com/v')
        fonte._aplicar_json(r, {'formats':[{'format_id':'251', 'acodec':'opus', 'vcodec':'none',
                              'ext':'webm', 'abr':155.789, 'asr':48000,
                              'filesize':1048576, 'audio_channels':2,
                              '_metodos':['JSON -j']}]})
        d = campos(r.formatos[0])
        self.assertEqual(d['Bitrate áudio'], '155.789 kbps')
        self.assertEqual(r.formatos[0].bitrate_kbps, 156)
        self.assertEqual(d['Tipo'], 'Somente áudio')
        self.assertEqual(d['Tamanho'], '1.0 MB')
        self.assertEqual(d['Métodos'], 'JSON -j')

    def test_divergencias_e_ausencias_sao_visiveis(self):
        url = 'https://example.com/video'
        def rodar(args, timeout):
            if '-F' in args and '--print-json' not in args:
                return 0, 'ID EXT RESOLUTION\n301 m4a audio only aac\n', ''
            formatos = [{'format_id':'301', 'acodec':'none', 'vcodec':'h264', 'ext':'mp4'},
                        {'format_id':'251', 'acodec':'opus', 'vcodec':'none', 'ext':'webm', 'abr':156}]
            return 0, json.dumps({'formats':formatos}), ''
        dados = consultar(url, ['yt-dlp'], rodar, _aviso_extracao)
        r = TrackResult('id', 'ytdlp', 'x', pagina_url=url)
        FonteYtDlp()._aplicar_json(r, dados)
        f = next(f for f in r.formatos if f.format_id == '301')
        detalhes = campos(f)
        self.assertIn('áudio não confirmado', detalhes['Tipo'])
        self.assertIn('codec de áudio', detalhes['Divergências entre métodos'])
        self.assertIn('Lista -F', detalhes['Divergências entre métodos'])
        self.assertIn('JSON -j', detalhes['Divergências entre métodos'])
        self.assertEqual(detalhes['Bitrate áudio'], 'não informado')

    @unittest.skipUnless(shutil.which('yt-dlp'), 'yt-dlp necessário')
    def test_tabela_real_preserva_abr_sem_confundir_asr(self):
        from app.metadata.consulta_formatos import _lista_texto
        info = {'id':'t','title':'Teste','extractor':'youtube','extractor_key':'Youtube',
                'formats':[{'format_id':'251','url':'https://example.com/a', 'ext':'webm',
                            'acodec':'opus','vcodec':'none','abr':155.758,'asr':48000},
                           {'format_id':'140','url':'https://example.com/b','ext':'m4a',
                            'acodec':'mp4a.40.2','vcodec':'none','asr':44100}]}
        with tempfile.TemporaryDirectory() as d:
            caminho = Path(d) / 'info.json'; caminho.write_text(json.dumps(info))
            saida = subprocess.run([shutil.which('yt-dlp'), '--ignore-config',
                                    '--load-info-json', str(caminho), '-F'],
                                   text=True, capture_output=True, check=True).stdout
        formatos = {f['format_id']:f for f in _lista_texto(saida)}
        self.assertNotIn('abr', formatos['140'])
        self.assertEqual(formatos['140']['_asr_tabela'], '44k')
        self.assertEqual(formatos['251']['abr'], 156.0)
        self.assertTrue(formatos['251']['_abr_da_tabela'])
        r = TrackResult('id', 'ytdlp', 'x', pagina_url='https://example.com')
        FonteYtDlp()._aplicar_json(r, {'formats':list(formatos.values())})
        d140 = campos(next(f for f in r.formatos if f.format_id=='140'))
        d251 = campos(next(f for f in r.formatos if f.format_id=='251'))
        self.assertEqual(d140['Bitrate áudio'], 'não informado')
        self.assertEqual(d140['Amostragem'], '44k Hz (tabela, arredondado)')
        self.assertIn('156 kbps (arredondado da tabela)', d251['Bitrate áudio'])

    def test_json_tem_precedencia_sobre_bitrate_arredondado_da_tabela(self):
        tabela = ('ID  EXT RESOLUTION | VCODEC     ACODEC ABR ASR\n'
                  '251 webm audio only | audio only opus  156k 48k\n')
        # Tabela real em outro teste; aqui simular a saída do parser para
        # verificar a precedência dos formatos da fonte estruturada.
        dados = {'format_id':'251', 'acodec':'opus', 'vcodec':'none', 'abr':156.0}
        def rodar(args, timeout):
            if '-F' in args and '--print-json' not in args: return 0, tabela, ''
            return 0, json.dumps({'formats':[dados]}), ''
        from unittest.mock import patch
        with patch('app.metadata.consulta_formatos._lista_texto',
                   return_value=[dict(dados, _abr_da_tabela=True)]):
            resposta = consultar('https://example.com', ['yt-dlp'], rodar, _aviso_extracao)
        self.assertNotIn('_abr_da_tabela', resposta['formats'][0])

    def test_abr_arredondado_na_tabela_nao_gira_divergencia_falsa(self):
        from unittest.mock import patch
        tabela = {'format_id':'251','acodec':'opus','vcodec':'none','abr':156.0,
                  '_abr_da_tabela':True}
        json_fmt = {'format_id':'251','acodec':'opus','vcodec':'none','abr':155.758}
        def rodar(args, timeout):
            if '-F' in args and '--print-json' not in args: return 0, 'tabela', ''
            return 0, json.dumps({'formats':[json_fmt]}), ''
        with patch('app.metadata.consulta_formatos._lista_texto', return_value=[tabela]):
            dados = consultar('https://example.com', ['yt-dlp'], rodar, _aviso_extracao)
        self.assertNotIn('abr', dados['formats'][0].get('_divergencias', {}))
        self.assertEqual(dados['formats'][0]['abr'], 155.758)

    def test_nao_exibe_url_da_nota_e_nao_cria_informacoes(self):
        fmt = AudioFormat(codec='unknown', format_id='x', extra={'nota':'info https://example.com/token'})
        d = campos(fmt)
        self.assertNotIn('https://', d['Nota da fonte'])
        self.assertEqual(d['Amostragem'], 'não informado')
        self.assertEqual(d['Canais'], 'não informado')
        self.assertEqual(d['Tamanho'], 'não informado')
        self.assertEqual(d['Tipo'], 'Não informado')

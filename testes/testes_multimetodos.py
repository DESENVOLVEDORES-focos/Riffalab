"""Quatro métodos, cruzamento, falhas independentes e proteção dos cookies."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.metadata import consulta_formatos as c
from app.models import TrackResult
from app.sources.ytdlp import FonteYtDlp, _aviso_extracao


def formato(ident, codec='opus', abr=128, vcodec='none'):
    return {'format_id': ident, 'acodec': codec, 'vcodec': vcodec,
            'ext': 'webm', 'abr': abr, 'asr': 48000}


def obj(formatos):
    return json.dumps({'formats': formatos, '_versao_biblioteca': '2026.10.26'})


class Multimetodos(unittest.TestCase):
    def test_formatos_sao_publicados_antes_dos_metodos_lentos_terminarem(self):
        import threading
        liberar = threading.Event()
        recebeu = threading.Event()
        parciais = []
        finais = []
        def rodar(args, timeout):
            if '-j' in args:
                return 0, obj([formato('251'), formato('140', 'aac', 130)]), ''
            self.assertTrue(liberar.wait(5))
            return 1, '', 'ERROR: HTTP Error 403'
        def parcial(dados):
            parciais.append(dados)
            recebeu.set()
        def executar():
            finais.append(c.consultar('https://example.com/video', ['yt-dlp'], rodar,
                                      _aviso_extracao, ao_parcial=parcial))
        worker = threading.Thread(target=executar)
        worker.start()
        try:
            self.assertTrue(recebeu.wait(3), 'nenhum formato parcial foi publicado')
            self.assertTrue(worker.is_alive(), 'métodos lentos não deveriam ter terminado')
            primeiro = parciais[0]
            self.assertEqual({f['format_id'] for f in primeiro['formats']}, {'251', '140'})
            self.assertEqual(sum(m['estado'] == 'consultando' for m in primeiro['metodos']), 3)
        finally:
            liberar.set()
            worker.join(10)
        self.assertFalse(worker.is_alive())
        self.assertEqual({f['format_id'] for f in finais[0]['formats']}, {'251', '140'})
        self.assertEqual([m['estado'] for m in finais[0]['metodos']],
                         ['falhou', 'ok', 'falhou', 'falhou'])

    def test_cruza_todos_mesmo_link_preserva_ids_e_nao_baixa(self):
        url = 'https://www.youtube.com/watch?v=abcdef'
        chamadas = []
        tabela = ('ID  EXT   RESOLUTION | PROTO | VCODEC ACODEC ABR ASR\n'
                  '251 webm  audio only | https | audio only opus 128k 48k\n'
                  '140 m4a   audio only | https | audio only mp4a.40.2 129k 44k\n'
                  'sb3 mhtml 48x27 | https | images\n')
        def rodar(args, timeout):
            chamadas.append(args)
            if 'consulta_biblioteca_ytdlp.py' in ' '.join(args):
                return 0, obj([formato('251'), formato('252'), formato('99', vcodec='h264')]), ''
            if '--print-json' in args:
                return 0, tabela + obj([formato('251'), formato('140', 'mp4a.40.2', 129)]), ''
            if '-j' in args:
                return 0, obj([formato('251'), formato('252')]), ''
            return 0, tabela, ''
        dados = c.consultar(url, ['yt-dlp', '--ignore-config'], rodar, _aviso_extracao)
        self.assertEqual(len(chamadas), 4)
        self.assertTrue(all(url in a for a in chamadas))
        self.assertTrue(all('-x' not in a and '-o' not in a for a in chamadas))
        self.assertEqual([x['estado'] for x in dados['metodos']], ['ok'] * 4)
        formatos = {f['format_id']: f for f in dados['formats']}
        self.assertEqual(set(formatos), {'251', '140', '252', '99'})
        self.assertEqual(set(formatos['251']['_metodos']), set(c.NOMES))
        self.assertEqual(set(formatos['252']['_metodos']), {'JSON -j', 'Biblioteca Python'})
        self.assertEqual(set(formatos['140']['_metodos']), {'Lista -F', 'Lista + JSON'})
        self.assertEqual(formatos['251']['abr'], 128)
        self.assertNotIn('sb3', formatos)
        self.assertEqual(dados['metodos'][3]['versao'], '2026.10.26')
        r = TrackResult('id', 'ytdlp', 'Música', pagina_url=url)
        FonteYtDlp()._aplicar_json(r, dados)
        self.assertEqual({f.format_id for f in r.formatos}, {'251', '140', '252', '99'})
        # Dois IDs com mesmo codec e bitrate não são eliminados.
        self.assertEqual(len([f for f in r.formatos if f.bitrate_kbps == 128]), 3)

    def test_falhas_isoladas_sem_fabricar_qualidade(self):
        def rodar(args, timeout):
            if 'consulta_biblioteca_ytdlp.py' in ' '.join(args):
                return 3, '', 'Biblioteca yt-dlp não instalada'
            if '--print-json' in args:
                return 0, obj([{'format_id':'sb','acodec':'none','vcodec':'none'}]), 'WARNING: Only images are available'
            if '-j' in args:
                return 1, '', 'ERROR: HTTP Error 403: forbidden'
            return 0, 'ID EXT RESOLUTION\n251 webm audio only opus\n', ''
        dados = c.consultar('https://example.com/video', ['yt-dlp'], rodar, _aviso_extracao)
        self.assertEqual([x['estado'] for x in dados['metodos']], ['ok', 'falhou', 'sem áudio', 'indisponível'])
        self.assertIn('403', dados['metodos'][1]['motivo'])
        self.assertEqual(len(dados['formats']), 1)
        self.assertNotIn('abr', dados['formats'][0])
        self.assertEqual(dados['formats'][0]['_metodos'], ['Lista -F'])

    def test_tabela_nao_confunde_taxa_de_amostragem_com_bitrate(self):
        linha = ('ID  EXT RESOLUTION | VCODEC ACODEC  ABR ASR\n'
                 '251 webm audio only | audio only opus       48k\n')
        encontrados = c._lista_texto(linha)
        self.assertEqual(len(encontrados), 1)
        self.assertNotIn('abr', encontrados[0])

    def test_saida_combinada_usa_tabela_e_json(self):
        def rodar(args, timeout):
            if '--print-json' in args:
                return 0, 'ID EXT RESOLUTION\n140 m4a audio only aac\n' + obj([formato('251')]), ''
            return 0, obj([]), ''
        dados = c.consultar('https://example.com/v', ['yt-dlp'], rodar, _aviso_extracao)
        formatos = {f['format_id']: f for f in dados['formats']}
        self.assertEqual(set(formatos), {'140', '251'})
        self.assertEqual(formatos['140']['_metodos'], ['Lista + JSON'])

    def test_json_invalido_e_falha_nao_resultado_sem_audio(self):
        dados = c.consultar('https://example.com/v', ['yt-dlp'],
                            lambda args, timeout: (0, 'resposta invalida', ''), _aviso_extracao)
        self.assertEqual(dados['metodos'][1]['estado'], 'falhou')
        self.assertEqual(dados['metodos'][2]['estado'], 'falhou')
        self.assertEqual(dados['metodos'][3]['estado'], 'falhou')

    def test_metadados_do_json_sao_preservados(self):
        resposta = json.dumps({'formats':[formato('251')], 'channel':'Canal',
                               'live_status':'was_live', 'view_count':123})
        dados = c.consultar('https://example.com/v', ['yt-dlp'],
                            lambda args, timeout: (0, resposta, ''), _aviso_extracao)
        r = TrackResult('id', 'ytdlp', 'Música', pagina_url='https://example.com/v')
        FonteYtDlp()._aplicar_json(r, dados)
        self.assertEqual(r.canal, 'Canal')
        self.assertEqual(r.extra['live_status'], 'was_live')
        self.assertEqual(r.visualizacoes, 123)

    def test_cookies_de_cada_consulta_sao_copias_temporarias_independentes(self):
        with tempfile.TemporaryDirectory() as d:
            cookie = Path(d) / 'cookie original.txt'; cookie.write_text('PRIVATE COOKIE TEST')
            copias = []
            def rodar(args, timeout):
                caminho = Path(args[3] if 'consulta_biblioteca_ytdlp.py' in ' '.join(args)
                               else args[args.index('--cookies') + 1])
                self.assertNotEqual(caminho, cookie)
                self.assertEqual(caminho.read_text(), 'PRIVATE COOKIE TEST')
                copias.append(caminho)
                caminho.write_text('alterado pelo processo')
                return (0, obj([formato('251')]), '')
            dados = c.consultar('https://example.com/v', ['yt-dlp', '--cookies', str(cookie)], rodar, _aviso_extracao)
            self.assertEqual(len(copias), 4)
            self.assertEqual(len(set(copias)), 4)
            self.assertTrue(all(not p.exists() for p in copias))
            self.assertEqual(cookie.read_text(), 'PRIVATE COOKIE TEST')
            self.assertNotIn('PRIVATE COOKIE TEST', repr(dados))

    def test_video_preservado_sem_contar_como_audio(self):
        video = {'format_id':'137','vcodec':'avc1.4d','acodec':'none','height':1080,'ext':'mp4'}
        def rodar(args, timeout): return (0, obj([video]), '')
        dados = c.consultar('https://example.com/v', ['yt-dlp'], rodar, _aviso_extracao)
        self.assertTrue(all(x['estado'] == 'sem áudio' for x in dados['metodos']))
        r = TrackResult('id', 'ytdlp', 'Música', pagina_url='https://example.com/v')
        FonteYtDlp()._aplicar_json(r, dados)
        self.assertFalse(r.formatos)
        self.assertEqual(r.video.get('altura'), 1080)

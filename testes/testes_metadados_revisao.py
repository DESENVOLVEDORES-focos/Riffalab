"""Identificação, revisão, tags e organização dos novos arquivos (sem rede real)."""
import hashlib
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import pipeline, preparacao, estado_musicas, tagging
from app.config import Config
from app.ia import identificador
from app.metadata import covers, itunes, musicbrainz
from app.models import AudioFormat, CoverResult, Identificacao, TrackMeta, TrackResult
from app.texto import limpar_titulo


class Metadados(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.cfg = Config(self.base / 'config.json')
        self.r = TrackResult('id', 'ytdlp', 'Canção', 'Pessoa', duracao_s=99,
                             pagina_url='https://example.com/video')

    def test_titulo_preserva_participacao_e_versao(self):
        self.assertEqual(limpar_titulo('Canção (feat. Outra) [Official Video]'), 'Canção (feat. Outra)')
        self.assertEqual(limpar_titulo('Canção (Live) (Remastered 2011)'), 'Canção (Live) (Remastered 2011)')
        self.assertEqual(limpar_titulo('Canção - Official Audio'), 'Canção')

    def test_nao_usa_resposta_de_outra_musica_nem_campos_incertos(self):
        dados = {'titulo':'Canção', 'artista':'Pessoa', 'album':'Disco', 'faixa':3,
                 'total_faixas':12, 'ano':2000, 'genero':'Rock', 'artista_album':'Pessoa'}
        outra = Identificacao(ok=True, confianca=.99, titulo='Música completamente diferente',
                              artista='Outro Artista', album='Errado', faixa=9)
        with patch.object(pipeline.covers, 'metadados_completos', return_value=dados):
            meta = pipeline.montar_metadados(self.r, self.cfg, ident=outra)
        self.assertEqual((meta.titulo, meta.artista, meta.album, meta.faixa), ('Canção','Pessoa','Disco',3))
        ident = Identificacao(ok=True, confianca=.99, titulo='Canção', artista='Pessoa',
                              album='Outro álbum', faixa=9, genero='Jazz',
                              artistas_participantes=['Alguém'], campos_incertos=['album','faixa','genero'])
        with patch.object(pipeline.covers, 'metadados_completos', return_value=dados):
            meta = pipeline.montar_metadados(self.r, self.cfg, ident=ident)
        self.assertEqual((meta.album, meta.faixa, meta.genero), ('Disco',3,'Rock'))
        self.assertEqual(meta.artistas_participantes, ['Alguém'])

    def test_ia_nao_troca_versao_ao_vivo_por_estudio(self):
        r = TrackResult('id','ytdlp','Canção (Live)','Pessoa')
        ident = Identificacao(ok=True,confianca=.99,titulo='Canção',artista='Pessoa',album='Estúdio')
        with patch.object(pipeline.covers, 'metadados_completos', return_value={}):
            meta = pipeline.montar_metadados(r,self.cfg,ident=ident)
        self.assertEqual(meta.titulo, 'Canção (Live)')
        self.assertNotEqual(meta.album, 'Estúdio')

    def test_confianca_invalida_nao_causa_erro_nem_autorizacao(self):
        self.assertEqual(identificador._confianca('invalida'), 0)
        self.assertEqual(identificador._confianca(float('nan')), 0)
        self.assertEqual(identificador._confianca(float('inf')), 0)
        self.assertEqual(identificador._confianca(.9), .9)

    def test_album_novo_nao_herda_numero_total_de_outro_album(self):
        ident = Identificacao(ok=True, confianca=.95, titulo='Canção', artista='Pessoa',
                              album='Outro disco', faixa=2, artista_album='Pessoa e Convidados')
        with patch.object(pipeline.covers, 'metadados_completos', return_value={
                'album':'Disco anterior', 'faixa':9, 'total_faixas':18, 'disco':2, 'ano':2001,
                'artista_album':'Pessoa'}):
            meta = pipeline.montar_metadados(self.r, self.cfg, ident=ident)
        self.assertEqual((meta.album, meta.faixa, meta.total_faixas, meta.disco), ('Outro disco',2,None,None))
        self.assertEqual(meta.artista_album, 'Pessoa e Convidados')
        self.assertIsNone(meta.ano)

    def test_busca_catalogo_com_album_ia_e_prefere_faixa_do_catalogo(self):
        ident = Identificacao(ok=True, confianca=.95, titulo='Canção', artista='Pessoa',
                              album='Disco', ano=2002, faixa=9, genero='Pop', artista_album='Errado')
        with patch.object(pipeline.covers, 'metadados_completos', return_value={
                'album':'Disco','faixa':3,'ano':2001,'genero':'Rock','artista_album':'Pessoa'}) as buscar:
            meta = pipeline.montar_metadados(self.r,self.cfg,ident=ident)
        self.assertEqual(buscar.call_args.args, ('Canção','Pessoa','Disco',2002))
        self.assertEqual((meta.album,meta.faixa,meta.ano,meta.genero), ('Disco',3,2001,'Rock'))
        self.assertEqual(meta.artista_album, 'Pessoa')

    def test_falhas_de_catalogo_e_ia_nao_inventam_campos(self):
        self.cfg.dados['ia_ativa'] = True
        with patch.object(identificador, 'identificar', return_value=Identificacao(ok=False,erro='sem rede')), \
             patch.object(pipeline.covers, 'metadados_completos', side_effect=OSError('sem rede')):
            prep = preparacao.preparar_musica(self.r, self.cfg, sem_capa=True)
        meta = prep['meta']
        self.assertEqual((meta.titulo, meta.artista), ('Canção','Pessoa'))
        self.assertEqual((meta.album,meta.genero,meta.ano,meta.faixa), ('','',None,None))
        self.assertEqual(meta.artistas_participantes, [])
        self.assertEqual(meta.artista_album, 'Pessoa')  # alternativa informada no guia

    def test_faixa_musicbrainz_nao_confunde_versao(self):
        dados = {'title':'Disco', 'media':[{'position':1, 'track-count':2, 'tracks':[
            {'title':'Canção (Live)', 'number':'1'}, {'title':'Canção', 'number':'2'}]}]}
        with patch.object(musicbrainz, '_get', return_value=dados):
            det = musicbrainz.detalhes_release('id', 'Canção')
        self.assertEqual(det['faixa'], 2)

    def test_musicbrainz_nao_confirma_album_de_artista_diferente(self):
        ident = Identificacao(ok=True, titulo='Canção', artista='Pessoa', album='Disco')
        with patch.object(musicbrainz, 'buscar_release_group', return_value=[
                {'album':'Disco', 'artista':'Alguém completamente diferente', 'mbid':'abc'}]):
            identificador._conferir_musicbrainz(ident)
        self.assertFalse(ident.verificado_musicbrainz)
        self.assertIn('album', ident.campos_incertos)

    def test_catalogo_corrige_grafia_e_busca_artista_album_sem_trocar_versao(self):
        item = {'titulo':'Canção', 'artista':'Pessoa', 'album':'Disco',
                'faixa':4, 'ano':2004, 'genero':'Rock', 'artista_album':'Pessoa e Banda'}
        with patch.object(itunes, 'melhor_faixa', return_value=item), \
             patch.object(musicbrainz, 'buscar_gravacao', return_value=[]):
            dados = covers.metadados_completos('cancao', 'pessoa')
        self.assertEqual((dados['titulo'],dados['artista'],dados['artista_album']), ('Canção','Pessoa','Pessoa e Banda'))
        with patch.object(itunes, 'melhor_faixa', return_value={**item, 'titulo':'Canção (Live)'}), \
             patch.object(musicbrainz, 'buscar_gravacao', return_value=[]):
            dados = covers.metadados_completos('Canção', 'Pessoa')
        self.assertEqual(dados['titulo'], 'Canção')

    def test_itunes_rejeita_outra_versao_e_respeita_artista_album_do_catalogo(self):
        comum = {'trackName':'Canção', 'artistName':'Pessoa', 'collectionName':'Disco',
                  'collectionArtistName':'Pessoa e Banda', 'releaseDate':'2004-02-01',
                  'trackNumber':4, 'trackCount':11, 'primaryGenreName':'Rock'}
        with patch.object(itunes, 'buscar', return_value=[{**comum, 'trackName':'Canção (Live)'}, comum]):
            melhor = itunes.melhor_faixa('Canção','Pessoa','Disco')
        self.assertEqual(melhor['titulo'], 'Canção')
        self.assertEqual(melhor['artista_album'], 'Pessoa e Banda')
        with patch.object(itunes, 'buscar', return_value=[{**comum,'trackName':'Canção (Live)'}]):
            self.assertIsNone(itunes.melhor_faixa('Canção','Pessoa','Disco'))

    def test_artista_album_pedido_a_ia_e_canal_real_no_pedido(self):
        self.assertIn('artista_album', identificador.ESQUEMA['required'])
        self.r.canal = 'Canal Original'
        pedido = identificador.montar_pedido(self.r)
        self.assertIn('Canal Original', pedido)
        self.assertNotIn('cookie', pedido.lower())

    def test_ano_e_faixa_inalterados_preservam_data_e_total(self):
        meta = TrackMeta(ano=2000, data_lancamento='2000-03-01', faixa=3, total_faixas=12)
        preparacao.aplicar_edicao(meta, {'ano':'2000', 'faixa':'3'})
        self.assertEqual(meta.data_lancamento,'2000-03-01')
        self.assertEqual(meta.total_faixas,12)
        preparacao.aplicar_edicao(meta, {'ano':'2001', 'faixa':'4'})
        self.assertEqual(meta.data_lancamento,'')
        self.assertIsNone(meta.total_faixas)

    def test_edicoes_tem_precedencia_e_nao_afetam_o_resultado_original(self):
        dados = {'titulo':'Canção', 'artista':'Pessoa', 'album':'Disco', 'ano':2000,
                 'faixa':4, 'genero':'Rock'}
        edit = {'titulo':'Título corrigido', 'artista':'Banda', 'album':'Novo',
                'ano':'2003', 'faixa':'7', 'genero':'Pop', 'artista_album':'Banda',
                'artistas_participantes':'Pessoa A, Pessoa B'}
        with patch.object(pipeline.covers, 'metadados_completos', return_value=dados):
            prep = preparacao.preparar_musica(self.r, self.cfg, edicao=edit, sem_capa=True)
        meta = prep['meta']
        self.assertEqual((meta.titulo,meta.artista,meta.album,meta.ano,meta.faixa,meta.genero),
                         ('Título corrigido','Banda','Novo',2003,7,'Pop'))
        self.assertEqual(meta.artistas_participantes, ['Pessoa A','Pessoa B'])
        self.assertEqual((self.r.titulo,self.r.artista), ('Canção','Pessoa'))
        self.assertEqual(prep['apagar_tags'], [])

    def test_edicao_vazia_e_persistencia_de_campos_removidos(self):
        meta = TrackMeta(titulo='Canção', artista='Pessoa', album='Disco', ano=2000,
                         faixa=3, genero='Rock', artista_album='Pessoa', data_lancamento='2000-01-01')
        edicao = {'album':'', 'ano':'', 'faixa':'', 'genero':'', 'artista_album':'', 'artistas_participantes':''}
        apagar = preparacao.aplicar_edicao(meta, edicao)
        self.assertEqual(set(apagar), {'album','ano','faixa','genero','artista_album'})
        self.assertEqual(meta.data_lancamento, '')
        class Check:
            def isChecked(self): return True
        class Linha:
            pedido = {'resultado':self.r, 'edicao':edicao}
            check = Check()
            preparacao = {'meta':meta, 'capa':CoverResult(), 'ident':None, 'apagar_tags':apagar}
        _, _, restaurada = estado_musicas.desserializar_selecao(estado_musicas.serializar_selecao(Linha()))
        self.assertEqual(set(restaurada['apagar_tags']), set(apagar))

    @unittest.skipUnless(shutil.which('ffmpeg'), 'ffmpeg não disponível')
    def test_pipeline_real_grava_todos_campos_duracao_e_nome_sem_tocar_antigos(self):
        from mutagen.id3 import ID3
        from app.sources.local_library import FonteBibliotecaLocal
        origem = self.base / 'som.wav'
        subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i',
                        'sine=frequency=440:duration=1.2',str(origem)], check=True)
        self.cfg.dados.update(pasta_saida=str(self.base/'saida'), ia_ativa=False)
        destino = self.base/'saida'/'Banda Certa'/'Título Correto.mp3'
        destino.parent.mkdir(parents=True)
        destino.write_bytes(b'arquivo antigo do usuario')
        antes = hashlib.sha256(destino.read_bytes()).hexdigest()
        fmt = AudioFormat(codec='wav', container='wav', url=str(origem), lossless=True)
        resultado = TrackResult('local','biblioteca_local','Título antigo','Banda antiga',
                                duracao_s=99, formatos=[fmt])
        edicao = {'titulo':'Título Correto','artista':'Banda Certa','album':'Álbum Certo',
                  'artistas_participantes':'Convidada, Outro', 'artista_album':'Banda do Álbum',
                  'genero':'Rock','ano':'2003','faixa':'7'}
        with patch.object(pipeline.covers, 'metadados_completos', return_value={}), \
             patch.object(pipeline, 'PASTA_TEMP', self.base/'temp'):
            prep = preparacao.preparar_musica(resultado, self.cfg, edicao=edicao, sem_capa=True)
            res = pipeline.processar_resultado(resultado, self.cfg, fmt,
                                               fonte=FonteBibliotecaLocal(self.cfg), preparacao=prep)
        self.assertTrue(res['ok'], res)
        self.assertEqual(Path(res['caminho']).relative_to(self.base/'saida'),
                         Path('Banda Certa')/'Título Correto (2).mp3')
        self.assertEqual(hashlib.sha256(destino.read_bytes()).hexdigest(), antes)
        tags = ID3(res['caminho'])
        self.assertEqual(str(tags['TIT2']), 'Título Correto')
        self.assertEqual(str(tags['TPE1']), 'Banda Certa feat. Convidada, Outro')
        self.assertEqual(str(tags['TPE2']), 'Banda do Álbum')
        self.assertEqual(str(tags['TALB']), 'Álbum Certo')
        self.assertEqual(str(tags['TCON']), 'Rock')
        self.assertEqual(str(tags['TDRC']), '2003')
        self.assertEqual(str(tags['TRCK']), '7')
        self.assertTrue(1000 <= int(str(tags['TLEN'])) <= 1600, str(tags['TLEN']))
        self.assertNotEqual(int(str(tags['TLEN'])), 99000)
        self.assertFalse(tags.getall('APIC'))
        from app.visualizador_mp3 import ler_mp3
        conteudo = Path(res['caminho']).read_bytes()
        visao = ler_mp3(res['caminho'], incluir_imagens=True)
        self.assertEqual((visao['titulo'], visao['artista_album'], visao['faixa'], visao['genero']),
                         ('Título Correto', 'Banda do Álbum', '7', 'Rock'))
        self.assertTrue(1 <= visao['duracao_s'] <= 1.6)
        self.assertEqual(Path(res['caminho']).read_bytes(), conteudo)

    @unittest.skipUnless(shutil.which('ffmpeg'), 'ffmpeg não disponível')
    def test_copia_mp3_remove_tags_nao_identificadas_sem_mexer_no_original(self):
        from mutagen.id3 import ID3, TALB, TCON, TRCK, TDRC, TPE2, TLEN
        from app.sources.local_library import FonteBibliotecaLocal
        origem = self.base / 'origem.mp3'
        subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i',
                        'sine=frequency=440:duration=0.5',str(origem)], check=True)
        tags = ID3(str(origem))
        for frame in (TALB(encoding=3,text='Errado'), TCON(encoding=3,text='Errado'),
                      TRCK(encoding=3,text='99'), TDRC(encoding=3,text='1999'),
                      TPE2(encoding=3,text='Outro'), TLEN(encoding=3,text='99999')):
            tags.add(frame)
        tags.save(str(origem),v2_version=3)
        antes = origem.read_bytes()
        self.cfg.dados.update(pasta_saida=str(self.base/'saida'), ia_ativa=False)
        fmt = AudioFormat(codec='mp3',container='mp3',url=str(origem))
        r = TrackResult('origem','biblioteca_local','Canção','Pessoa',formatos=[fmt])
        prep = {'meta':TrackMeta(titulo='Canção',artista='Pessoa'), 'capa':CoverResult(), 'ident':None}
        with patch.object(pipeline, 'PASTA_TEMP', self.base/'temp'):
            res = pipeline.processar_resultado(r,self.cfg,fmt,fonte=FonteBibliotecaLocal(self.cfg),preparacao=prep)
        self.assertTrue(res['ok'],res)
        novo = ID3(res['caminho'])
        for frame in ('TALB','TCON','TRCK','TDRC','TPE2'):
            self.assertNotIn(frame,novo)
        self.assertLess(int(str(novo['TLEN'])), 2000)
        self.assertEqual(origem.read_bytes(),antes)

"""Identidade, álbum original e grafia consistente sem acesso externo."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from app import pipeline, preparacao
from app.config import Config
from app.ia import identificador
from app.metadata import album_original, covers, musicbrainz
from app.models import Identificacao, TrackResult
from app.texto import limpar_titulo_tags


class AlbumETitulo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.cfg = Config(Path(self.tmp.name)/'config.json')
        self.cfg.dados['ia_ativa'] = True

    def test_remove_ruidos_tecnicos_e_preserva_edicao_musical(self):
        entradas = {
            'Billie Jean (4K Remastered)': 'Billie Jean',
            'Billie Jean - 2011 Remaster': 'Billie Jean',
            'Billie Jean 4K Remasterizado': 'Billie Jean',
            'Billie Jean (Versão de 2022)': 'Billie Jean',
            'Billie Jean - 2022 Remastered Official Video': 'Billie Jean',
            'Billie Jean (Live) (Remastered 2011)': 'Billie Jean (Live)',
            'Billie Jean (Remix) [4K Remastered]': 'Billie Jean (Remix)',
            'Song (feat. A) [Remastered]': 'Song (feat. A)',
            'Remastered': 'Remastered',
            'One - Live': 'One - Live',
            'Version of Events': 'Version of Events',
        }
        for bruto, esperado in entradas.items():
            with self.subTest(bruto=bruto): self.assertEqual(limpar_titulo_tags(bruto), esperado)

    @staticmethod
    def release(ident, titulo, album, grupo, ano, secundarias=(), status='Official', artista='Michael Jackson'):
        return {'titulo':titulo, 'artista':artista, 'album':album, 'album_grupo':grupo,
                'tipo_lancamento':'Album', 'tipos_secundarios':list(secundarias),
                'status':status, 'data_grupo':str(ano)+'-01-01', 'data_release':str(ano)+'-01-01',
                'release_id':ident, 'release_group':ident+'-grupo'}

    def test_album_mais_antigo_ligado_a_faixa_sem_coletanea_ou_artista_errado(self):
        releases = [self.release('fake','Billie Jean','Fake','Fake',1970,artista='Outro'),
                    self.release('hits','Billie Jean','Greatest Hits','Greatest Hits',1975,['Compilation']),
                    self.release('live','Billie Jean','Live','Live',1979,['Live']),
                    self.release('a','Billie Jean','Thriller (Remastered)','Thriller',1982),
                    self.release('a2','Billie Jean','Thriller','Thriller',1982),
                    self.release('deluxe','Billie Jean','Thriller 25','Thriller 25',2008)]
        detalhes = {'album':'Thriller','ano':1982,'faixa':6,'total_faixas':9,'disco':1}
        with patch.object(musicbrainz,'buscar_gravacao',return_value=releases) as buscar, \
             patch.object(musicbrainz,'detalhes_release',return_value=detalhes):
            achado = album_original.encontrar('Billie Jean','Michael Jackson')
        self.assertEqual(achado['album'], 'Thriller')
        self.assertEqual((achado['ano'],achado['faixa']),(1982,6))
        self.assertTrue(buscar.call_args.kwargs['todos_lancamentos'])
        self.assertEqual(buscar.call_args.args[2], '')

    def test_single_associado_quando_nao_ha_album_regular(self):
        single=self.release('s','Canção','Canção','Canção',2021,artista='Pessoa')
        single['tipo_lancamento'] = 'Single'
        with patch.object(musicbrainz,'buscar_gravacao',return_value=[single]), \
             patch.object(musicbrainz,'detalhes_release',return_value={}):
            resultado=album_original.encontrar('Canção','Pessoa')
        self.assertEqual((resultado['album'],resultado['ano']),('Canção',2021))

    def test_nome_oficial_do_grupo_nao_e_mutilado(self):
        album=self.release('r','Canção','Deluxe (Deluxe)','Deluxe (Deluxe)',2001,artista='Pessoa')
        with patch.object(musicbrainz,'buscar_gravacao',return_value=[album]), \
             patch.object(musicbrainz,'detalhes_release',return_value={}):
            self.assertEqual(album_original.encontrar('Canção','Pessoa')['album'], 'Deluxe (Deluxe)')

    def test_retorno_realista_musicbrainz_consulta_grupo_para_grafia(self):
        # A pesquisa de gravação real omite título e data do release-group.
        rel = {'id':'release-a', 'title':'Thriller (Remastered)', 'date':'1982-11-30', 'status':'Official',
               'release-group':{'id':'grupo-a','primary-type':'Album'}}
        resultado = {'recordings':[{'title':'Billie Jean', 'score':100,
                      'artist-credit':[{'name':'Michael Jackson'}], 'releases':[rel]}]}
        grupo = {'id':'grupo-a','title':'Thriller','primary-type':'Album',
                 'secondary-types':[], 'first-release-date':'1982-11-30'}
        detalhe = {'title':'Thriller', 'date':'1982-11-30',
                   'artist-credit':[{'name':'Michael Jackson'}],
                   'media':[{'position':1,'track-count':9,'tracks':[{'title':'Billie Jean', 'number':'6'}]}]}
        def get(url):
            if '/recording/' in url: return resultado
            if '/release-group/' in url: return grupo
            return detalhe
        musicbrainz.detalhes_grupo.cache_clear()
        with patch.object(musicbrainz,'_get',side_effect=get) as chamadas:
            achado=album_original.encontrar('Billie Jean','Michael Jackson')
            outro=album_original.encontrar('Billie Jean','Michael Jackson')
        self.assertEqual((achado['album'],achado['ano'],achado['faixa']), ('Thriller',1982,6))
        self.assertEqual(achado['release_group'],'grupo-a')
        self.assertEqual(outro['album'],'Thriller')
        self.assertEqual(sum('/release-group/' in c.args[0] for c in chamadas.call_args_list),1)
        musicbrainz.detalhes_grupo.cache_clear()

    def test_nome_oficial_do_grupo_mantem_capitalizacao_entre_faixas(self):
        resultados = []
        for titulo, grafia_ia in [("Welcome to the Jungle",'Appetite For Destruction'),
                                  ("Sweet Child O' Mine",'appetite for destruction')]:
            registro = self.release('r',titulo,'Appetite for Destruction (Remastered)',
                                    'Appetite for Destruction',1987,artista="Guns N' Roses")
            ident = Identificacao(ok=True,confianca=.99,titulo=titulo+' (2018 Remaster)',
                                  artista="Guns N' Roses",album=grafia_ia,genero='Errado')
            r = TrackResult(titulo,'ytdlp',"Guns N' Roses - "+titulo+' (4K Remastered)',"Guns N' Roses")
            item = {'titulo':titulo+' - 2018 Remaster','artista':"Guns N' Roses",
                    'album':'Appetite for Destruction','ano':1987,'genero':'rock'}
            with patch.object(musicbrainz,'buscar_gravacao',return_value=[registro]), \
                 patch.object(musicbrainz,'detalhes_release',return_value={}), \
                 patch.object(covers.itunes,'melhor_faixa',return_value=item):
                meta=pipeline.montar_metadados(r,self.cfg,ident=ident)
            resultados.append(meta)
        self.assertEqual([m.album for m in resultados],['Appetite for Destruction']*2)
        self.assertEqual([m.genero for m in resultados],['Rock','Rock'])
        self.assertEqual([m.titulo for m in resultados],["Welcome to the Jungle", "Sweet Child O' Mine"])

    def test_ia_inventa_album_sem_catalogo_nao_vira_tag(self):
        r=TrackResult('id','ytdlp','Billie Jean 4K Remasterizado','Michael Jackson',album='Compilação errada')
        ident=Identificacao(ok=True,confianca=.99,titulo='Billie Jean (2022 Remaster)',
                            artista='Michael Jackson',album='Álbum inventado',ano=2022,faixa=99,genero='Errado')
        with patch.object(musicbrainz,'buscar_gravacao',return_value=[]), \
             patch.object(covers.itunes,'melhor_faixa',return_value=None):
            meta=pipeline.montar_metadados(r,self.cfg,ident=ident)
        self.assertEqual(meta.titulo,'Billie Jean')
        self.assertEqual((meta.album,meta.ano,meta.faixa,meta.genero),('',None,None,''))

    def test_usuario_pode_editar_nome_album_e_genero_e_nunca_reescreve_origem(self):
        r=TrackResult('id','ytdlp','Billie Jean 4K','Michael Jackson')
        edit={'titulo':'Meu título (Remaster)', 'artista':'Michael Jackson',
              'album':'Minha Grafia', 'genero':'Meu Gênero', 'faixa':'3', 'ano':'1982'}
        with patch.object(identificador,'identificar',return_value=Identificacao(ok=False)), \
             patch.object(covers,'metadados_completos',return_value={}):
            dados=preparacao.preparar_musica(r,self.cfg,edicao=edit,sem_capa=True)
        self.assertEqual((dados['meta'].titulo,dados['meta'].album,dados['meta'].genero),
                         ('Meu título (Remaster)','Minha Grafia','Meu Gênero'))
        self.assertEqual((dados['meta'].faixa,dados['meta'].ano),(3,1982))
        self.assertEqual(r.titulo,'Billie Jean 4K')

    def test_nao_fabrica_grafia_quando_falta_titulo_do_grupo(self):
        registro=self.release('a','Canção','Álbum remaster','',2000,artista='Pessoa')
        with patch.object(musicbrainz,'buscar_gravacao',return_value=[registro]), \
             patch.object(musicbrainz,'detalhes_grupo',return_value={}):
            self.assertEqual(album_original.encontrar('Canção','Pessoa'),{})

    def test_faixa_da_reedicao_nao_e_atribuida_ao_ano_original(self):
        registro=self.release('r','Canção','Disco (Remastered)','Disco',1990,artista='Pessoa')
        detalhe={'album':'Disco (Remastered)','ano':2011,'faixa':4,'disco':2,'total_faixas':12}
        with patch.object(musicbrainz,'buscar_gravacao',return_value=[registro]), \
             patch.object(musicbrainz,'detalhes_release',return_value=detalhe):
            resultado=album_original.encontrar('Canção','Pessoa')
        self.assertEqual(resultado['album'],'Disco'); self.assertEqual(resultado['ano'],1990)
        self.assertNotIn('faixa',resultado); self.assertNotIn('disco',resultado)

    def test_edicao_extra_de_album_nao_herda_dados_do_disco_anterior(self):
        r=TrackResult('id','ytdlp','Canção','Pessoa')
        catalogo={'titulo':'Canção','artista':'Pessoa','album':'Antigo','ano':2001,
                  'faixa':7,'total_faixas':12,'disco':1,'genero':'Rock',
                  'artista_album':'Banda','fontes':['musicbrainz']}
        with patch.object(covers,'metadados_completos',return_value=catalogo):
            meta=pipeline.montar_metadados(r,self.cfg,extra={'album':'Outro','faixa':2})
        self.assertEqual((meta.album,meta.faixa),('Outro',2))
        self.assertEqual((meta.ano,meta.total_faixas,meta.disco,meta.genero,meta.artista_album),
                         (None,None,None,'',''))

    def test_mesmo_ano_mas_edicao_diferente_nao_herda_faixa(self):
        registro=self.release('r','Canção','Disco (Deluxe)','Disco',1990,artista='Pessoa')
        detalhe={'album':'Disco (Deluxe)','ano':1990,'faixa':10,'disco':2,'total_faixas':20}
        with patch.object(musicbrainz,'buscar_gravacao',return_value=[registro]), \
             patch.object(musicbrainz,'detalhes_release',return_value=detalhe):
            resultado=album_original.encontrar('Canção','Pessoa')
        self.assertNotIn('faixa',resultado)
        self.assertNotIn('total_faixas',resultado)

    def test_prompt_pede_campos_e_preserva_grafia_oficial(self):
        self.assertIn('4K', identificador.SISTEMA)
        self.assertIn('capitalização oficiais', identificador.SISTEMA)
        self.assertIn('gênero', identificador.SISTEMA)
        self.assertIn('null', identificador.SISTEMA)

if __name__ == '__main__': unittest.main()

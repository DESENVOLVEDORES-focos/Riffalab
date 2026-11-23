"""Busca de capa usa a identificação da própria música, sem tocar MP3s."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app import estado_musicas, pipeline, preparacao
from app.config import Config
from app.models import CoverResult, Identificacao, TrackMeta, TrackResult


class IdentidadeCapaLote(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.config = Config(Path(self.temp.name) / 'config.json')
        self.config.dados['ia_ativa'] = True

    def test_lote_consulta_cada_faixa_pela_identidade_propria_da_ia(self):
        musicas = [TrackResult('1', 'ytdlp', 'Nome do vídeo 1', 'Canal 1'),
                   TrackResult('2', 'ytdlp', 'Nome do vídeo 2', 'Canal 2'),
                   TrackResult('3', 'ytdlp', 'Nome do vídeo 3', 'Canal 3')]
        identidades = {r.uid: Identificacao(ok=True, confianca=.95,
                            titulo=f'Título IA {r.uid}', artista=f'Artista IA {r.uid}') for r in musicas}
        consultas = []
        def capa(titulo, artista, album, ano, **kwargs):
            consultas.append((titulo, artista, album, ano, kwargs.get('identificacao')))
            return CoverResult(observacao='nenhuma encontrada no teste')
        with patch.object(preparacao.identificador, 'identificar', side_effect=lambda r,c,p: identidades[r.uid]), \
             patch.object(pipeline.covers, 'metadados_completos', return_value={}), \
             patch.object(pipeline.covers, 'encontrar_capa', side_effect=capa):
            preps = [preparacao.preparar_musica(r, self.config) for r in musicas]
        self.assertEqual([(c[0], c[1]) for c in consultas],
                         [(f'Título IA {i}', f'Artista IA {i}') for i in (1,2,3)])
        for i, prep in enumerate(preps, 1):
            self.assertEqual(prep['consulta_capa']['origem'], 'IA')
            self.assertEqual(prep['consulta_capa']['titulo'], f'Título IA {i}')
            self.assertIs(consultas[i-1][4], identidades[str(i)])
            self.assertEqual(prep['meta'].titulo, f'Nome do vídeo {i}')  # nome do arquivo não é alterado
            self.assertIn('difere dos metadados', prep['consulta_capa']['aviso'])

    def test_edicao_usuario_tem_prioridade_e_isrc_incompativel_nao_passado(self):
        r = TrackResult('1', 'ytdlp', 'Música', 'Pessoa')
        ident = Identificacao(ok=True, confianca=.95, titulo='Música da IA', artista='Artista da IA', isrc='ID')
        with patch.object(preparacao.identificador, 'identificar', return_value=ident), \
             patch.object(pipeline.covers, 'metadados_completos', return_value={}), \
             patch.object(pipeline.covers, 'encontrar_capa', return_value=CoverResult()) as buscar:
            prep = preparacao.preparar_musica(r, self.config, edicao={'titulo':'Correção', 'artista':'Meu Artista'})
        self.assertEqual(buscar.call_args.args[:2], ('Correção', 'Meu Artista'))
        self.assertIsNone(buscar.call_args.kwargs['identificacao'])
        self.assertEqual(prep['consulta_capa']['origem'], 'dados revisados')

    def test_ia_incerta_invalida_e_desativada_nao_e_usada_sem_aviso(self):
        meta = TrackMeta(titulo='Título', artista='Artista')
        for ident in (Identificacao(ok=False, titulo='Outro', artista='Outro', confianca=1),
                      Identificacao(ok=True, titulo='Outro', artista='Outro', confianca=.2),
                      Identificacao(ok=True, titulo='Outro', artista='Outro', confianca=.9, campos_incertos=['artista'])):
            consulta, passada = preparacao.identidade_para_capa(meta, ident, self.config)
            self.assertEqual((consulta['titulo'],consulta['artista']), ('Título','Artista'))
            self.assertIn('IA sem', consulta['aviso']); self.assertIsNone(passada)
        self.config.dados['ia_ativa'] = False
        consulta, _ = preparacao.identidade_para_capa(meta, None, self.config)
        self.assertIn('IA desativada', consulta['aviso'])

    def test_nao_troca_versao_ao_vivo_por_estudio(self):
        meta = TrackMeta(titulo='Música (Live)', artista='Pessoa')
        ident = Identificacao(ok=True, titulo='Música', artista='Pessoa', confianca=.95)
        consulta, passada = preparacao.identidade_para_capa(meta, ident, self.config)
        self.assertEqual(consulta['titulo'], 'Música (Live)')
        self.assertIn('versão', consulta['aviso']); self.assertIsNone(passada)

    def test_nome_de_canal_e_termo_mostrado_igual_ao_que_e_buscado(self):
        r = TrackResult('1', 'ytdlp', 'Metallica - Nothing Else Matters', 'MetallicaVEVO')
        self.config.dados['ia_ativa'] = False
        with patch.object(pipeline.covers, 'metadados_completos', return_value={}), \
             patch.object(pipeline.covers, 'encontrar_capa', return_value=CoverResult()) as buscar:
            prep = preparacao.preparar_musica(r, self.config)
        self.assertEqual(buscar.call_args.args[:2], (prep['consulta_capa']['titulo'], prep['consulta_capa']['artista']))

    def test_persistencia_da_consulta_e_compatibilidade_antiga(self):
        r = TrackResult('1','ytdlp','A','B')
        consulta = {'titulo':'A da IA','artista':'B da IA','origem':'IA','aviso':'confira'}
        prep = {'meta':TrackMeta(titulo='A',artista='B'), 'ident':None,
                'capa':CoverResult(), 'consulta_capa':consulta}
        linha = SimpleNamespace(pedido={'resultado':r}, preparacao=prep, check=SimpleNamespace(isChecked=lambda:True))
        gravado = estado_musicas.serializar_selecao(linha)
        _, _, recuperado = estado_musicas.desserializar_selecao(gravado)
        self.assertEqual(recuperado['consulta_capa'], consulta)
        del gravado['preparacao']['consulta_capa']
        _, _, antigo = estado_musicas.desserializar_selecao(gravado)
        self.assertEqual(antigo['consulta_capa'], {})

if __name__ == '__main__': unittest.main()

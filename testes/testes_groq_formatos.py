"""Resposta realista de HTTP 400 e alternativas seguras, sem rede nem chave real."""
import io
import json
import unittest
import urllib.error
from unittest.mock import patch
from app.ia import cliente_groq as groq, identificador


class Resposta:
    def __init__(self, dados): self.dados = dados
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def read(self): return json.dumps(self.dados).encode()


def erro400(codigo='json_validate_failed', texto="Failed to generate JSON. See 'failed_generation' for more details."):
    body = {'error':{'message':texto, 'code':codigo, 'failed_generation':'DADOS PARCIAIS PRIVADOS'}}
    return urllib.error.HTTPError('https://api.groq.com/openai/v1/chat/completions',400,'erro',{},io.BytesIO(json.dumps(body).encode()))


def resposta(conteudo, finish='stop'):
    return {'model':'modelo-atual', 'choices':[{'finish_reason':finish,'message':{'content':conteudo}}]}


class FormatosGroq(unittest.TestCase):
    def setUp(self):
        self.cfg={'ia_modelo':'modelo-atual','ia_timeout':5}
        self.resultado={'identificado':True,'confianca':.95,'titulo':'Nature','artista':'Pessoa',
                        'album':'Disco','genero':'Rock','ano':2001,'faixa':2,
                        'artista_album':'Pessoa','artistas_participantes':[],'campos_incertos':[]}
        self.urlpatch=patch.object(groq.seguranca,'ler',return_value='chave-ficticia')
        self.urlpatch.start();self.addCleanup(self.urlpatch.stop)

    def completar(self):
        return groq.completar_json(self.cfg, identificador.SISTEMA_REVISAO,
                                   'Nature — Pessoa — Disco', identificador.ESQUEMA_REVISAO)

    def test_erro_400_dos_dois_formatos_e_recuperado_em_texto(self):
        pedidos=[]
        def urlopen(req, timeout):
            body=json.loads(req.data);pedidos.append(body)
            if len(pedidos) <= 2: raise erro400()
            return Resposta(resposta('```json\n'+json.dumps(self.resultado)+'\n```'))
        with patch('urllib.request.urlopen',side_effect=urlopen):
            dados, modelo=self.completar()
        self.assertEqual(dados,self.resultado);self.assertEqual(modelo,'modelo-atual')
        self.assertEqual([p.get('response_format',{}).get('type') for p in pedidos],['json_schema','json_object',None])
        self.assertTrue(all(p['model']=='modelo-atual' for p in pedidos))
        self.assertEqual(pedidos[0]['max_completion_tokens'],2048)
        self.assertIn('campos_incertos',pedidos[2]['messages'][1]['content'])
        self.assertNotIn('DADOS PARCIAIS',json.dumps(pedidos))

    def test_erro_de_json_se_resolve_no_formato_intermediario(self):
        with patch('urllib.request.urlopen',side_effect=[erro400(),Resposta(resposta(json.dumps(self.resultado)))]) as url:
            dados,_=self.completar()
        self.assertEqual(dados['titulo'],'Nature'); self.assertEqual(url.call_count,2)

    def test_rejeicao_do_schema_cai_no_formato_simples(self):
        err=erro400('invalid_request_error',"The response_format json_schema is not supported by this model")
        with patch('urllib.request.urlopen',side_effect=[err,Resposta(resposta(json.dumps(self.resultado)))]) as url:
            self.completar()
        self.assertEqual(url.call_count,2)

    def test_schema_invalido_aceita_alternativa_sem_mascarar_outros_400(self):
        err=erro400('invalid_request_error',"Invalid schema for response_format: unsupported keyword")
        with patch('urllib.request.urlopen',side_effect=[err,Resposta(resposta(json.dumps(self.resultado)))]) as url:
            self.completar()
        self.assertEqual(url.call_count,2)

    def test_erro_de_modelo_nao_tenta_mais_vezes_ou_troca_modelo(self):
        err=erro400('invalid_request_error','The model does not exist or is unavailable')
        with patch('urllib.request.urlopen',side_effect=err) as url:
            with self.assertRaises(groq.ErroGroq) as exc: self.completar()
        self.assertEqual(url.call_count,1);self.assertEqual(exc.exception.status,400)
        self.assertIn('model does not exist',str(exc.exception))

    def test_nao_repete_credencial_invalida(self):
        err=urllib.error.HTTPError('https://api.groq.com',401,'erro',{},io.BytesIO(b'{}'))
        with patch('urllib.request.urlopen',side_effect=err) as url:
            with self.assertRaises(groq.ErroGroq) as exc: self.completar()
        self.assertEqual(url.call_count,1); self.assertEqual(exc.exception.status,401)

    def test_limite_ou_indisponibilidade_nao_mudam_formato_nem_modelo(self):
        for status in (429, 503):
            erro=groq.ErroGroq('serviço indisponível', status)
            with self.subTest(status=status), patch.object(groq,'_pedido',side_effect=erro) as pedido:
                with self.assertRaises(groq.ErroGroq) as exc: self.completar()
                self.assertEqual(exc.exception.status,status)
                self.assertEqual(pedido.call_count,1)
                self.assertEqual(pedido.call_args.args[3]['model'],'modelo-atual')

    def test_resposta_invalida_tenta_outro_formato_sem_aproveitar_dados_parciais(self):
        respostas=[Resposta(resposta('texto inválido')),Resposta(resposta('[1,2,3]')),
                   Resposta(resposta(json.dumps(self.resultado)))]
        with patch('urllib.request.urlopen',side_effect=respostas) as url:
            dados,_=self.completar()
        self.assertEqual(url.call_count,3);self.assertEqual(dados['titulo'],'Nature')

    def test_resposta_truncada_e_invalida_nao_preenchem_campos(self):
        with patch('urllib.request.urlopen',side_effect=[Resposta(resposta(json.dumps(self.resultado),'length')),
                Resposta(resposta('{"titulo":"parcial"')),
                Resposta(resposta('{"identificado":"false","confianca":0.9}'))]):
            with self.assertRaises(groq.ErroGroq) as exc: self.completar()
        self.assertIn('inválidos',str(exc.exception))

    def test_erro_final_de_formatacao_e_claro_sem_vazar_geracao_parcial(self):
        with patch('urllib.request.urlopen',side_effect=[erro400(),erro400(),erro400()]):
            with self.assertRaises(groq.ErroGroq) as exc: self.completar()
        self.assertIn('organizar a resposta',str(exc.exception))
        self.assertNotIn('DADOS PARCIAIS',str(exc.exception))
        self.assertNotIn('failed_generation',str(exc.exception))

    def test_revisao_envia_apenas_identidade_e_observacao_e_pede_os_oito_campos(self):
        from app.models import TrackResult
        r=TrackResult('id','ytdlp','Nature 4K','Pessoa',pagina_url='https://example.com/video')
        revisao={'dados_atuais':{'titulo':'Nature','artista':'Pessoa','album':'Disco',
                                 'genero':'não enviar','faixa':'4'},'observacao':'faixa errada'}
        pedido=identificador.montar_pedido(r,revisao)
        self.assertIn('Nature',pedido);self.assertIn('Pessoa',pedido);self.assertIn('Disco',pedido)
        self.assertIn('faixa errada',pedido); self.assertNotIn('não enviar',pedido)
        self.assertNotIn('https://example.com',pedido)
        for chave in ('titulo','artista','album','genero','ano','faixa','artista_album','artistas_participantes'):
            self.assertIn(chave,identificador.ESQUEMA_REVISAO['properties'])

if __name__ == '__main__': unittest.main()

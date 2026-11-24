"""Cliente mínimo da API da Groq (GroqCloud).

Por que HTTP "na mão" (urllib) e não o SDK oficial: o RiffLab não tem nenhuma
dependência além de PySide6 e mutagen, e a API da Groq é compatível com o
formato OpenAI. Assim continua instalável em qualquer Windows sem
`pip install groq` nem `pip install openai`.

Endpoints usados (atenção ao caminho: a Groq usa `/openai/v1`, não `/v1`):
    POST https://api.groq.com/openai/v1/chat/completions  → identificação
    GET  https://api.groq.com/openai/v1/models           → teste de conexão

Autenticação: `Authorization: Bearer gsk_…` (chave criada em console.groq.com).
Quando o formato estruturado falha, tentamos formatos alternativos no mesmo
modelo e validamos a resposta antes de devolver os dados.

O cliente NÃO conhece regra de negócio: recebe sistema+usuário+schema e devolve
um dict já validado como JSON. Quem interpreta é `app/ia/identificador.py`.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from .. import seguranca
from ..config import Config

BASE_PADRAO = "https://api.groq.com/openai/v1"
MODELO_PADRAO = "openai/gpt-oss-120b"
UA = "RiffLab/0.4 (uso local)"


class ErroGroq(RuntimeError):
    """Falha na chamada à API, já traduzida para o usuário."""

    def __init__(self, mensagem: str, status: int = 0, codigo: str = "") -> None:
        super().__init__(mensagem)
        self.status = status
        self.codigo = codigo


def _base(config: Optional[Config]) -> str:
    if config is not None:
        return str(config.get("ia_url_base") or BASE_PADRAO).rstrip("/")
    return BASE_PADRAO


def _chave(config: Optional[Config] = None) -> str:
    return seguranca.ler()


def _cabecalhos(chave: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {chave}", "Content-Type": "application/json",
            "Accept": "application/json", "User-Agent": UA}


def _traduzir_erro(status: int, corpo: str) -> ErroGroq:
    texto = (corpo or "").strip()
    codigo = ""
    try:
        dados = json.loads(texto)
        erro = dados.get("error") or {}
        if isinstance(erro, dict):
            codigo = str(erro.get("code") or "")
            texto = erro.get("message") or dados.get("message") or ""
        else:
            texto = str(erro)
    except Exception:                                             # noqa: BLE001
        pass
    texto = str(texto)[:300]
    if status == 400:
        erro = ErroGroq(f"a Groq recusou o pedido (HTTP 400): {texto}", status, codigo)
        if _erro_de_formato(erro):
            return ErroGroq("a IA não conseguiu organizar a resposta. Tente novamente.", status, 'formato')
        return erro
    if status == 401:
        return ErroGroq("chave da API inválida ou revogada (HTTP 401) — confira a "
                        "chave gsk_… em console.groq.com", status, codigo)
    if status == 403:
        return ErroGroq("a conta não tem acesso a esse modelo (HTTP 403)", status, codigo)
    if status == 404:
        return ErroGroq(f"modelo/rota não encontrado (HTTP 404): {texto}", status, codigo)
    if status == 429:
        return ErroGroq("limite de uso da Groq atingido (HTTP 429: requisições ou "
                        "tokens por minuto) — aguarde um pouco e tente de novo", status, codigo)
    if status in (413, 503):
        return ErroGroq(f"a Groq recusou por tamanho/disponibilidade (HTTP {status})", status, codigo)
    if status >= 500:
        return ErroGroq(f"serviço da Groq indisponível (HTTP {status})", status, codigo)
    return ErroGroq(f"HTTP {status}: {texto}", status, codigo)


def _erro_de_formato(erro: ErroGroq) -> bool:
    """Somente rejeições de formato; um 400 de modelo ou parâmetros não é retry."""
    if erro.status != 400:
        return False
    codigo = str(erro.codigo or '').lower()
    if codigo in ('json_validate_failed', 'formato'):
        return True
    texto = str(erro).lower()
    if any(termo in texto for termo in (
        'failed to generate json', 'failed to validate json',
        'json validation failed', 'json_validate_failed')):
        return True
    return (any(termo in texto for termo in ('response_format', 'json_schema', 'json schema'))
            and any(termo in texto for termo in ('not supported', 'unsupported', 'does not support', 'invalid schema')))


def _espera_do_429(exc: urllib.error.HTTPError, teto: float = 8.0) -> float:
    """A Groq manda `retry-after` (ou `x-ratelimit-reset-requests`); respeita."""
    for nome in ("retry-after", "x-ratelimit-reset-requests"):
        valor = (exc.headers or {}).get(nome) if exc.headers else None
        if not valor:
            continue
        texto = str(valor).strip().lower()
        try:
            if texto.endswith("ms"):
                return min(teto, float(texto[:-2]) / 1000.0)
            if texto.endswith("s"):
                return min(teto, float(texto[:-1]))
            return min(teto, float(texto))
        except ValueError:
            continue
    return 2.0


def _pedido(metodo: str, url: str, chave: str, corpo: Optional[dict],
            timeout: int, tentativas: int = 2) -> Dict[str, Any]:
    dados = json.dumps(corpo).encode("utf-8") if corpo is not None else None
    req = urllib.request.Request(url, data=dados, method=metodo,
                                 headers=_cabecalhos(chave))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            bruto = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        detalhe = exc.read().decode("utf-8", "replace")
        if exc.code == 429 and tentativas > 1:
            time.sleep(_espera_do_429(exc))       # 1 nova tentativa, sem travar a UI
            return _pedido(metodo, url, chave, corpo, timeout, tentativas - 1)
        raise _traduzir_erro(exc.code, detalhe) from None
    except urllib.error.URLError as exc:
        raise ErroGroq(f"não foi possível falar com a Groq: {exc.reason}") from None
    except TimeoutError:
        raise ErroGroq("a Groq não respondeu a tempo") from None
    try:
        return json.loads(bruto)
    except json.JSONDecodeError:
        raise ErroGroq("a Groq devolveu uma resposta ilegível") from None


# ------------------------------------------------------------------ API pública
def disponivel(config: Optional[Config] = None) -> tuple[bool, str]:
    """A IA só roda se estiver ligada E houver chave."""
    ligada = bool(config.get("ia_ativa")) if config is not None else False
    if not ligada:
        return False, "identificação por IA desligada nas Configurações"
    if not seguranca.existe():
        return False, "nenhuma chave da API da Groq configurada"
    return True, ""


def listar_modelos(config: Optional[Config] = None, timeout: int = 20) -> List[str]:
    chave = _chave(config)
    if not chave:
        raise ErroGroq("nenhuma chave da API configurada")
    dados = _pedido("GET", f"{_base(config)}/models", chave, None, timeout)
    modelos = [m.get("id") for m in dados.get("data") or [] if m.get("id")]
    return sorted(modelos)


def testar(config: Optional[Config] = None) -> Dict[str, Any]:
    """Teste de conexão usado pelo botão das Configurações."""
    inicio = time.time()
    chave = _chave(config)
    if not chave:
        return {"ok": False, "mensagem": "Nenhuma chave configurada.", "modelos": []}
    try:
        modelos = listar_modelos(config)
    except ErroGroq as exc:
        return {"ok": False, "mensagem": str(exc), "modelos": [], "status": exc.status}
    modelo = str((config.get("ia_modelo") if config else "") or MODELO_PADRAO)
    aviso = ""
    if modelos and modelo not in modelos:
        parecidos = [m for m in modelos if m.startswith("groq")]
        if parecidos:
            aviso = (f"O modelo '{modelo}' não aparece na lista da sua conta. "
                     f"Use um destes: {', '.join(parecidos[:4])}.")
    segundos = round(time.time() - inicio, 2)
    return {"ok": True, "modelos": modelos, "modelo": modelo, "aviso": aviso,
            "mensagem": (f"Conexão OK ({segundos}s, {len(modelos)} modelo(s) disponível(is)). "
                         + aviso).strip(),
            "segundos": segundos}


def _interpretar_resposta(resposta: Dict[str, Any], schema: Optional[dict]) -> tuple[dict, str]:
    """Decodifica a resposta inteira e rejeita objetos incompletos/inválidos."""
    try:
        escolha = resposta["choices"][0]
        mensagem = escolha["message"]
        conteudo = mensagem["content"]
    except (KeyError, IndexError, TypeError):
        raise ErroGroq("a IA respondeu sem dados. Tente novamente.", codigo='resposta_invalida') from None
    if escolha.get('finish_reason') == 'length':
        raise ErroGroq("a resposta da IA ficou incompleta. Tente novamente.", codigo='resposta_invalida')
    if isinstance(conteudo, list):
        conteudo = "".join(p.get("text", "") for p in conteudo if isinstance(p, dict))
    texto = str(conteudo or "").strip()
    if texto.startswith('```'):
        linhas = texto.splitlines()
        if len(linhas) >= 3 and linhas[-1].strip() == '```':
            texto = '\n'.join(linhas[1:-1]).strip()
    try:
        dados = json.loads(texto)
    except (json.JSONDecodeError, TypeError):
        # Alguns modelos incluem explicação antes/depois do objeto completo.
        inicio, fim = texto.find('{'), texto.rfind('}')
        try:
            dados = json.loads(texto[inicio:fim + 1]) if inicio >= 0 and fim > inicio else None
        except json.JSONDecodeError:
            dados = None
    if not isinstance(dados, dict):
        raise ErroGroq("a IA não conseguiu organizar a resposta. Tente novamente.", codigo='resposta_invalida')
    if schema:
        propriedades = schema.get('properties') or {}
        for chave, valor in dados.items():
            spec = propriedades.get(chave)
            if not isinstance(spec, dict):
                continue
            tipos = spec.get('type') or []
            tipos = [tipos] if isinstance(tipos, str) else tipos
            valido = (('null' in tipos and valor is None) or
                      ('string' in tipos and isinstance(valor, str)) or
                      ('boolean' in tipos and isinstance(valor, bool)) or
                      ('integer' in tipos and isinstance(valor, int) and not isinstance(valor, bool)) or
                      ('number' in tipos and isinstance(valor, (int, float)) and not isinstance(valor, bool)) or
                      ('array' in tipos and isinstance(valor, list) and all(isinstance(x, str) for x in valor)))
            if tipos and not valido:
                raise ErroGroq("a IA devolveu dados incompletos ou inválidos. Tente novamente.", codigo='resposta_invalida')
        if 'identificado' in propriedades:
            import math
            confianca = dados.get('confianca')
            if (not isinstance(dados.get('identificado'), bool)
                    or isinstance(confianca, bool) or not isinstance(confianca, (int, float))
                    or not math.isfinite(confianca) or not 0 <= confianca <= 1
                    or (dados['identificado'] and (not isinstance(dados.get('titulo'), str)
                        or not dados['titulo'].strip() or not isinstance(dados.get('artista'), str)
                        or not dados['artista'].strip()))):
                raise ErroGroq("a IA devolveu dados incompletos ou inválidos. Tente novamente.", codigo='resposta_invalida')
    return dados, str(resposta.get('model') or '')


def completar_json(config: Config, sistema: str, usuario: str,
                   schema: Optional[dict] = None, timeout: Optional[int] = None,
                   max_tokens: int = 2048) -> tuple[dict, str]:
    """Consulta o mesmo modelo e tenta formatos alternativos apenas se necessário."""
    chave = _chave(config)
    if not chave:
        raise ErroGroq("nenhuma chave da API configurada")
    modelo = str(config.get("ia_modelo") or MODELO_PADRAO)
    espera = int(timeout or config.get("ia_timeout") or 60)
    base = _base(config)
    corpo: Dict[str, Any] = {
        "model": modelo,
        "temperature": float(config.get("ia_temperatura") or 0),
        "max_completion_tokens": max_tokens,
        "messages": [{"role": "system", "content": sistema},
                     {"role": "user", "content": usuario}],
        "stream": False,
    }
    formatos = ([{"type": "json_schema", "json_schema": {
                     "name": "identificacao_musical", "schema": schema, "strict": True}},
                 {"type": "json_object"}, None] if schema else [None])
    ultimo = None
    for indice, formato in enumerate(formatos):
        tentativa = dict(corpo)
        if formato:
            tentativa['response_format'] = formato
        if indice and schema:
            # Os formatos menos estritos não recebem o schema da API; informar
            # as chaves ao modelo evita uma resposta válida porém inutilizável.
            campos = {k: v.get('type') for k, v in (schema.get('properties') or {}).items()}
            tentativa['messages'] = [dict(msg) for msg in corpo['messages']]
            tentativa['messages'][1]['content'] += (
                "\nResponda somente com um objeto JSON. Chaves e tipos: "
                + json.dumps(campos, ensure_ascii=False) +
                ". Use null ou [] quando não souber; identificado é booleano e confianca é número entre 0 e 1.")
        try:
            resposta = _pedido("POST", f"{base}/chat/completions", chave, tentativa, espera)
            dados, modelo_usado = _interpretar_resposta(resposta, schema)
            return dados, modelo_usado or modelo
        except ErroGroq as exc:
            ultimo = exc
            if indice == len(formatos) - 1 or not (_erro_de_formato(exc) or exc.codigo == 'resposta_invalida'):
                raise
    raise ultimo or ErroGroq("a IA não conseguiu organizar a resposta. Tente novamente.")

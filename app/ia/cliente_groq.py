"""Cliente mínimo da API da Groq (GroqCloud).

Por que HTTP "na mão" (urllib) e não o SDK oficial: o RiffLab não tem nenhuma
dependência além de PySide6 e mutagen, e a API da Groq é compatível com o
formato OpenAI. Assim continua instalável em qualquer Windows sem
`pip install groq` nem `pip install openai`.

Endpoints usados (atenção ao caminho: a Groq usa `/openai/v1`, não `/v1`):
    POST https://api.groq.com/openai/v1/chat/completions  → identificação
    GET  https://api.groq.com/openai/v1/models           → teste de conexão

Autenticação: `Authorization: Bearer gsk_…` (chave criada em console.groq.com).
Modelo padrão: `openai/gpt-oss-120b`, que aceita Structured Outputs com
`strict: true`; nos modelos que não aceitam, o cliente repete com
`{"type": "json_object"}`.

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

    def __init__(self, mensagem: str, status: int = 0) -> None:
        super().__init__(mensagem)
        self.status = status


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
    try:
        dados = json.loads(texto)
        texto = (dados.get("error") or {}).get("message") or dados.get("message") or texto
    except Exception:                                             # noqa: BLE001
        pass
    texto = str(texto)[:300]
    if status == 400:
        return ErroGroq(f"a Groq recusou o pedido (HTTP 400): {texto}", status)
    if status == 401:
        return ErroGroq("chave da API inválida ou revogada (HTTP 401) — confira a "
                        "chave gsk_… em console.groq.com", status)
    if status == 403:
        return ErroGroq("a conta não tem acesso a esse modelo (HTTP 403)", status)
    if status == 404:
        return ErroGroq(f"modelo/rota não encontrado (HTTP 404): {texto}", status)
    if status == 429:
        return ErroGroq("limite de uso da Groq atingido (HTTP 429: requisições ou "
                        "tokens por minuto) — aguarde um pouco e tente de novo", status)
    if status in (413, 503):
        return ErroGroq(f"a Groq recusou por tamanho/disponibilidade (HTTP {status})", status)
    if status >= 500:
        return ErroGroq(f"serviço da Groq indisponível (HTTP {status})", status)
    return ErroGroq(f"HTTP {status}: {texto}", status)


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


def completar_json(config: Config, sistema: str, usuario: str,
                   schema: Optional[dict] = None, timeout: Optional[int] = None,
                   max_tokens: int = 900) -> tuple[dict, str]:
    """Chama o modelo e devolve (dict, modelo_usado).

    Usa `response_format: json_schema` (strict) quando há schema. Se o modelo
    recusar o formato (HTTP 400), repete com `json_object` — assim funciona
    tanto nos modelos mais novos quanto nos antigos.
    """
    chave = _chave(config)
    if not chave:
        raise ErroGroq("nenhuma chave da API configurada")
    modelo = str(config.get("ia_modelo") or MODELO_PADRAO)
    espera = int(timeout or config.get("ia_timeout") or 60)
    base = _base(config)

    corpo: Dict[str, Any] = {
        "model": modelo,
        "temperature": float(config.get("ia_temperatura") or 0),
        "max_tokens": max_tokens,
        "messages": [{"role": "system", "content": sistema},
                     {"role": "user", "content": usuario}],
        "stream": False,
    }
    if schema:
        corpo["response_format"] = {"type": "json_schema",
                                    "json_schema": {"name": "identificacao_musical",
                                                    "schema": schema, "strict": True}}
    try:
        resposta = _pedido("POST", f"{base}/chat/completions", chave, corpo, espera)
    except ErroGroq as exc:
        if exc.status != 400 or not schema:
            raise
        corpo["response_format"] = {"type": "json_object"}
        resposta = _pedido("POST", f"{base}/chat/completions", chave, corpo, espera)

    try:
        conteudo = resposta["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise ErroGroq("a Groq respondeu sem conteúdo") from None
    if isinstance(conteudo, list):                 # alguns modelos devolvem blocos
        conteudo = "".join(p.get("text", "") for p in conteudo if isinstance(p, dict))
    modelo_usado = str(resposta.get("model") or modelo)

    texto = str(conteudo or "").strip()
    if texto.startswith("```"):
        texto = texto.split("```")[1] if "```" in texto[3:] else texto[3:]
        texto = texto.lstrip("json").strip()
    try:
        return json.loads(texto), modelo_usado
    except json.JSONDecodeError:
        inicio = texto.find("{")
        fim = texto.rfind("}")
        if inicio >= 0 and fim > inicio:
            try:
                return json.loads(texto[inicio:fim + 1]), modelo_usado
            except json.JSONDecodeError:
                pass
    raise ErroGroq("a resposta da IA não é um JSON válido")

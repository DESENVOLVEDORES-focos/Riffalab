"""Guarda da chave da API da Groq fora do `config.json`.

Por que um módulo só para isso: a proposta (§9) exige que a chave **nunca** fique
no código-fonte nem em texto puro no arquivo de preferências.

Ordem de prioridade na leitura:

1. variável de ambiente `GROQ_API_KEY` (nada é gravado em disco);
2. **`api.txt` na raiz do projeto** (o jeito mais simples: um arquivo de texto
   com a chave, criado à mão pelo usuário) — também aceita `api_key.txt` e
   `apikey.txt`. Aceita a chave pura, `GROQ_API_KEY=...`, `Bearer ...`, com
   aspas, BOM do Windows e linhas de comentário (`#`);
3. arquivo local `credenciais/groq.dat`:
     * **Windows**: cifrado com DPAPI (`CryptProtectData`), vinculado ao usuário
       do Windows — outro usuário/máquina não decifra;
     * **Linux/macOS**: arquivo com permissão 0600 (só o dono lê). Não é
       criptografia: é isolamento por permissão, e o LEIA-ME diz isso.

O valor nunca é escrito no log nem exibido: a interface mostra apenas a máscara
(`gsk_…AbCd`) e a origem.
"""
from __future__ import annotations

import base64
import os
import sys
from pathlib import Path
from typing import Optional, Tuple

from .config import RAIZ

PASTA = RAIZ / "credenciais"
ARQ = PASTA / "groq.dat"
VARIAVEL_AMBIENTE = "GROQ_API_KEY"

# Arquivo de texto na raiz: o caminho mais simples para o usuário. O nome tem
# que estar no .gitignore e nunca deve ser enviado a ninguém.
NOMES_API = ("api.txt", "api_key.txt", "apikey.txt")
ARQ_API = RAIZ / NOMES_API[0]

CABECALHO_API = ("# RiffLab - chave da API da Groq (Groq)\n"
                 "# Este arquivo e lido automaticamente. Nao compartilhe.\n")

_CRYPTPROTECT_UI_FORBIDDEN = 0x1


# --------------------------------------------------------------------- DPAPI
def _dpapi(dados: bytes, proteger: bool) -> bytes:
    """Cifra/decifra com DPAPI do Windows (sem dependência externa)."""
    import ctypes
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    # Manter o buffer vivo até o retorno e declarar ponteiros explicitamente:
    # ctypes assume int por padrão, o que trunca ponteiros em Windows 64 bits.
    buffer_entrada = ctypes.create_string_buffer(dados, len(dados))
    entrada = DATA_BLOB(len(dados), ctypes.cast(buffer_entrada, ctypes.POINTER(ctypes.c_char)))
    saida = DATA_BLOB()
    crypt32 = ctypes.windll.crypt32                     # type: ignore[attr-defined]
    kernel32 = ctypes.windll.kernel32                   # type: ignore[attr-defined]
    funcao = crypt32.CryptProtectData if proteger else crypt32.CryptUnprotectData
    funcao.argtypes = [ctypes.POINTER(DATA_BLOB), ctypes.c_void_p, ctypes.c_void_p,
                       ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD,
                       ctypes.POINTER(DATA_BLOB)]
    funcao.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    ok = funcao(ctypes.byref(entrada), None, None, None, None,
                _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(saida))
    if not ok:
        raise OSError("DPAPI recusou a operação")
    try:
        return ctypes.string_at(saida.pbData, saida.cbData)
    finally:
        kernel32.LocalFree(ctypes.cast(saida.pbData, ctypes.c_void_p))



def limpar_texto(conteudo: str) -> str:
    """Extrai a chave de um texto escrito à mão.

    Aceita: chave pura, `GROQ_API_KEY=chave`, `"chave"`, `Bearer chave`,
    BOM do Bloco de Notas, comentários com `#`/`//` e linhas em branco.
    """
    texto = (conteudo or "").replace("\ufeff", "").replace("\x00", "")
    for linha in texto.splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or linha.startswith("//"):
            continue
        if "=" in linha:                     # GROQ_API_KEY=gsk_...
            linha = linha.split("=", 1)[1].strip()
        linha = linha.strip().strip("\"'").strip()
        if linha.lower().startswith("bearer "):
            linha = linha[7:].strip()
        if linha:
            return linha
    return ""


def arquivo_api() -> Optional[Path]:
    """`api.txt` (ou variação) na raiz do projeto, se existir."""
    for nome in NOMES_API:
        caminho = RAIZ / nome
        if caminho.is_file():
            return caminho
    return None


def _windows() -> bool:
    return os.name == "nt"


# ------------------------------------------------------------------ API pública
def guardar(chave: str, texto_puro: Optional[bool] = None) -> Tuple[bool, str]:
    """Grava a chave. Devolve (ok, mensagem para a interface).

    Se já existe um `api.txt` na raiz, ele é **atualizado** (senão o arquivo
    antigo continuaria tendo prioridade e a chave salva não valeria nada).
    `texto_puro=True` força gravar em `api.txt`; `False` força o cofre.
    """
    chave = limpar_texto(chave)
    if not chave:
        return False, "chave vazia"

    api = arquivo_api()
    usar_txt = (api is not None) if texto_puro is None else bool(texto_puro)
    if usar_txt:
        destino = api or ARQ_API
        try:
            destino.write_text(CABECALHO_API + chave + "\n", encoding="utf-8", newline="\n")
            return True, (f"chave gravada em {destino.name} (texto puro — não compartilhe "
                          f"esse arquivo; ele é lido automaticamente)")
        except OSError as exc:
            return False, f"não foi possível escrever {destino.name}: {exc}"

    try:
        PASTA.mkdir(parents=True, exist_ok=True)
        bruto = chave.encode("utf-8")
        if _windows():
            conteudo = b"DPAPI1" + _dpapi(bruto, proteger=True)
        else:
            conteudo = b"LOCAL1" + bruto
        tmp = ARQ.with_suffix(".tmp")
        tmp.write_bytes(conteudo)
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        tmp.replace(ARQ)
        return True, ("chave guardada com DPAPI (só este usuário do Windows lê)"
                      if _windows() else "chave guardada em credenciais/ (permissão 0600)")
    except Exception as exc:                                      # noqa: BLE001
        return False, f"não foi possível guardar a chave: {exc}"


def ler() -> str:
    """Chave em uso (ambiente > api.txt > cofre). Vazio se não houver."""
    do_ambiente = (os.environ.get(VARIAVEL_AMBIENTE) or "").strip()
    if do_ambiente:
        return do_ambiente
    api = arquivo_api()
    if api is not None:
        try:
            valor = limpar_texto(api.read_text("utf-8", errors="replace"))
            if valor:
                return valor
        except OSError:
            pass
    try:
        if not ARQ.is_file():
            return ""
        conteudo = ARQ.read_bytes()
        if conteudo.startswith(b"DPAPI1"):
            if not _windows():
                return ""                       # arquivo de Windows em outra máquina
            return _dpapi(conteudo[6:], proteger=False).decode("utf-8", "replace").strip()
        if conteudo.startswith(b"LOCAL1"):
            return conteudo[6:].decode("utf-8", "replace").strip()
        # formato antigo/desconhecido: tenta texto puro
        return conteudo.decode("utf-8", "replace").strip()
    except Exception:                                             # noqa: BLE001
        return ""


def existe() -> bool:
    return bool(ler())


def origem() -> str:
    if (os.environ.get(VARIAVEL_AMBIENTE) or "").strip():
        return f"variável de ambiente {VARIAVEL_AMBIENTE}"
    api = arquivo_api()
    if api is not None:
        try:
            if limpar_texto(api.read_text("utf-8", errors="replace")):
                return f"{api.name} na raiz do projeto (texto puro)"
        except OSError:
            pass
    if ARQ.is_file():
        return f"arquivo local ({'DPAPI' if _windows() else 'permissão 0600'})"
    return ""


def caminho_legivel() -> str:
    """Texto curto dizendo de onde a chave vem (para a interface)."""
    if (os.environ.get(VARIAVEL_AMBIENTE) or "").strip():
        return f"variável de ambiente {VARIAVEL_AMBIENTE}"
    api = arquivo_api()
    if api is not None:
        return str(api)
    if ARQ.is_file():
        return str(ARQ)
    return str(ARQ_API) + "  (ainda não existe)"


def mascarar(chave: Optional[str] = None) -> str:
    """Forma segura de mostrar que existe uma chave: `gsk_…7f2c`."""
    valor = (chave if chave is not None else ler()) or ""
    if not valor:
        return ""
    if len(valor) <= 8:
        return "…"
    return f"{valor[:4]}…{valor[-4:]}"


def apagar() -> None:
    """Remove a chave do disco: o cofre e o(s) arquivo(s) `api*.txt` da raiz."""
    for caminho in [ARQ, *(RAIZ / nome for nome in NOMES_API)]:
        try:
            caminho.unlink(missing_ok=True)
        except OSError:
            pass

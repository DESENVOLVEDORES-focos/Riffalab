"""Verificação do cookies.txt — tratado como informação SENSÍVEL.

Regras de segurança adotadas aqui:
  * nenhum conteúdo (nome/valor de cookie) é lido para fora deste módulo;
  * nada é escrito em log: só caminho, tamanho, contagem de linhas e datas;
  * a validação é estrutural (formato Netscape), sem imprimir valores;
  * consultas podem usar cópias temporárias que são removidas ao fim; o
    conteúdo não é anexado aos resultados nem enviado ao RiffLab.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from .config import ARQ_COOKIES, RAIZ


@dataclass
class StatusCookies:
    caminho: str = ""
    existe: bool = False
    legivel: bool = False
    vazio: bool = False
    tamanho: int = 0
    linhas_totais: int = 0
    cookies_validos: int = 0
    dominios: int = 0
    modificado_em: float = 0.0
    expira_em: float = 0.0
    formato_netscape: bool = False
    mensagem: str = ""
    detalhes: List[str] = field(default_factory=list)

    @property
    def utilizavel(self) -> bool:
        return self.existe and self.legivel and not self.vazio and self.cookies_validos > 0

    @property
    def estado(self) -> str:
        if not self.existe:
            return "ausente"
        if not self.legivel:
            return "sem permissão de leitura"
        if self.vazio:
            return "vazio"
        if self.cookies_validos == 0:
            return "formato inválido"
        return "pronto"

    def modificado_texto(self) -> str:
        if not self.modificado_em:
            return "-"
        return time.strftime("%d/%m/%Y %H:%M", time.localtime(self.modificado_em))

    def para_exibicao(self) -> dict:
        """Somente dados não sensíveis (usado pela tela de Configurações)."""
        return {
            "caminho": self.caminho,
            "estado": self.estado,
            "tamanho": self.tamanho,
            "cookies": self.cookies_validos,
            "dominios": self.dominios,
            "linhas": self.linhas_totais,
            "modificado": self.modificado_texto(),
            "utilizavel": self.utilizavel,
            "mensagem": self.mensagem,
            "formato_netscape": self.formato_netscape,
        }


def verificar(caminho: str | Path | None = None) -> StatusCookies:
    """Verifica existência, acesso e conteúdo mínimo do cookies.txt."""
    alvo = Path(caminho) if caminho else ARQ_COOKIES
    st = StatusCookies(caminho=str(alvo))

    if not alvo.exists():
        st.mensagem = ("Nenhuma configuração de autenticação local encontrada. "
                       "O app continua funcionando normalmente; alguns vídeos podem "
                       "exigir cookies (idade, região, conteúdo privado).")
        return st

    st.existe = True
    try:
        st.tamanho = alvo.stat().st_size
        st.modificado_em = alvo.stat().st_mtime
        with open(alvo, "rb") as fh:
            fh.read(1)                       # teste real de leitura
        st.legivel = True
    except PermissionError:
        st.mensagem = "Arquivo existe, mas o Windows negou a leitura (permissões)."
        return st
    except OSError:
        st.mensagem = "Arquivo existe, mas não pôde ser aberto."
        return st

    if st.tamanho == 0:
        st.vazio = True
        st.mensagem = "cookies.txt está vazio (0 bytes)."
        return st

    # Leitura estrutural: conta campos, SEM guardar valores
    dominios = set()
    expiracoes = []
    try:
        with open(alvo, "r", encoding="utf-8", errors="replace") as fh:
            for linha in fh:
                st.linhas_totais += 1
                linha_limpa = linha.strip()
                if not linha_limpa:
                    continue
                # Netscape usa #HttpOnly_ como prefixo de domínio; essas linhas
                # são cookies válidos, não comentários.
                if linha_limpa.startswith("#HttpOnly_"):
                    linha_limpa = linha_limpa[len("#HttpOnly_"):]
                elif linha_limpa.startswith("#"):
                    continue
                campos = linha_limpa.split("\t")
                if len(campos) >= 7 and campos[0]:
                    st.cookies_validos += 1
                    dominios.add(campos[0])
                    try:
                        exp = int(campos[4])
                        if exp > 0:
                            expiracoes.append(exp)
                    except (ValueError, IndexError):
                        pass
    except OSError:
        st.mensagem = "Falha ao ler o conteúdo do arquivo."
        return st

    st.dominios = len(dominios)
    st.formato_netscape = st.cookies_validos > 0
    st.expira_em = min(expiracoes) if expiracoes else 0.0

    if st.cookies_validos == 0:
        st.mensagem = ("Arquivo existe, mas nenhuma linha no formato Netscape "
                       "(dominio<TAB>flag<TAB>caminho<TAB>seguro<TAB>expira<TAB>nome<TAB>valor).")
    else:
        st.mensagem = (f"{st.cookies_validos} cookie(s) de {st.dominios} domínio(s). "
                       "Conteúdo não é exibido nem registrado em log.")
        if st.expira_em and st.expira_em < time.time():
            st.detalhes.append("Atenção: pelo menos um cookie pode estar expirado.")
    return st


def existe() -> bool:
    return ARQ_COOKIES.exists() or verificar().utilizavel


def caminho_padrao() -> Path:
    return ARQ_COOKIES


def exemplo_conteudo() -> str:
    """Modelo didático (valores FICTÍCIOS) para o arquivo de exemplo."""
    return (
        "# Netscape HTTP Cookie File\n"
        "# Arquivo de exemplo — NÃO use estes valores.\n"
        "# dominio\tflag\tcaminho\tseguro\texpira\tnome\tvalor\n"
        "exemplo.invalid\tTRUE\t/\tTRUE\t1700000000\tnome_do_cookie\tvalor_do_cookie\n"
    )


def nunca_logar() -> str:
    return ("Conteúdo de cookies.txt é sensível: não é exibido na interface, "
            "nem gravado em logs, nem enviado a terceiros.")

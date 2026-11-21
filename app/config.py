"""Configuração central: caminhos, constantes e preferências persistentes.

Todos os caminhos são relativos à raiz do aplicativo (a pasta que contém
o main.py), exatamente como no layout pedido:

    RiffLab/
        main.py
        cookies.txt
        downloads/
        capas/
        temp/
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict

APP_NOME = "RiffLab"
APP_SUB = "pesquisa · qualidade · metadados"
APP_VERSAO = "0.6.1"

# ------------------------------------------------------------------ caminhos
def _raiz() -> Path:
    """Raiz do app: pasta do main.py (ou a do executável, se congelado)."""
    if getattr(sys, "frozen", False):                      # PyInstaller
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


RAIZ = _raiz()
PASTA_DOWNLOADS = RAIZ / "downloads"
PASTA_CAPAS = RAIZ / "capas"
PASTA_TEMP = RAIZ / "temp"
PASTA_FERRAMENTAS = RAIZ / "ferramentas"
PASTA_CACHE_CAPAS = PASTA_CAPAS / "cache"

ARQ_CONFIG = RAIZ / "config.json"
ARQ_BANCO = RAIZ / "rifflab.db"
ARQ_LOG = RAIZ / "rifflab.log"
ARQ_COOKIES = RAIZ / "cookies.txt"

EXTENSOES_AUDIO = (".mp3", ".flac", ".m4a", ".aac", ".opus", ".ogg", ".wav", ".wma", ".aiff", ".alac")

# ------------------------------------------------------------------ padrões
PADROES: Dict[str, Any] = {
    # saída
    "pasta_saida": str(PASTA_DOWNLOADS),
    "pasta_verificar_baixados": "",     # opcional, além da pasta de saída
    "template_organizacao": "{artista}/{titulo}.mp3",   # ou {artista}/{album}/{faixa} {titulo}.mp3
    "sobrescrever": False,
    # conversão — controles simples (§5 e §12 da proposta)
    "qualidade_mp3": "automatica",     # automatica | alta | personalizada
    "mp3_bitrate": 256,                # 128..320, usado em "personalizada"
    "modo_mp3": "preservar",           # legado (migrado para qualidade_mp3)
    "preferir_lossless": True,
    "manter_original_nao_mp3": False,
    # download / lote
    "downloads_simultaneos": 2,        # 1..4
    "manter_temporarios": False,       # debug: não apaga temp/<uid>/
    "quantidade_padrao": 5,            # campo "Quantidade" da pesquisa
    # fontes de pesquisa — yt-dlp é a principal; o Archive fica disponível
    # nas Configurações, mas desligado (basta marcar para usar)
    "fontes_ativas": ["ytdlp"],
    "ytdlp_consentido": False,
    "biblioteca_local": "",
    "limite_resultados": 20,
    # pesquisa visual (v0.5.0)
    "evitar_ao_vivo": True,            # filtro de shows/ao vivo ativado por padrão
    "verificar_automatico": 10,        # quantos vídeos enriquecer/verificar na busca
    "mostrar_filtrados": False,        # o botão "Mostrar resultados filtrados"
    "confirmar_antes_processar": True, # etapa 5 do fluxo: confirmação
    "confirmar_capa": True,            # etapa 9: o usuário aprova a capa
    "tamanho_minimo_capa": 300,
    # identificação musical por IA (Groq) — proposta de atualização
    "ia_ativa": False,                 # liga/desliga a identificação com IA
    "ia_modelo": "openai/gpt-oss-120b",           # ajustável nas Configurações
    "ia_url_base": "https://api.groq.com/openai/v1",
    "ia_timeout": 60,
    "ia_temperatura": 0.0,
    "ia_min_confianca": 0.35,          # abaixo disso a identificação é descartada
    # metadados / capas
    "fontes_capa": ["coverartarchive", "itunes", "deezer"],
    "usar_thumb_como_capa": False,     # thumbnail do vídeo NÃO é capa oficial
    "tamanho_minimo_capa": 300,
    "preferir_capa_quadrada": True,
    "gravar_tags": True,
    "gravar_id3v1": True,
    "baixar_capa": True,               # procurar capa automaticamente
    "incorporar_capa": True,           # gravar a capa dentro do MP3 (APIC)
    # cookies
    "usar_cookies": True,
    "caminho_cookies": "",             # vazio = ./cookies.txt
    # aparência
    "tema": "neon-graffiti",
    "cor_destaque": "violeta",
}

def garantir_pastas() -> None:
    for p in (PASTA_DOWNLOADS, PASTA_CAPAS, PASTA_TEMP, PASTA_CACHE_CAPAS, PASTA_FERRAMENTAS):
        p.mkdir(parents=True, exist_ok=True)


class Config:
    """Preferências em JSON, com valores padrão e gravação atômica."""

    def __init__(self, caminho: Path | None = None) -> None:
        self.caminho = Path(caminho or ARQ_CONFIG)
        self.dados: Dict[str, Any] = dict(PADROES)
        self.carregar()

    # -- persistência -------------------------------------------------
    def carregar(self) -> None:
        try:
            if self.caminho.exists():
                bruto = json.loads(self.caminho.read_text(encoding="utf-8"))
                if isinstance(bruto, dict):
                    for k, v in bruto.items():
                        if k in PADROES or k.startswith("_"):
                            self.dados[k] = v
                    self._migrar(bruto)
        except Exception:
            pass  # config corrompida: segue com os padrões

    def _migrar(self, bruto: Dict[str, Any]) -> None:
        """Converte chaves antigas para as novas, sem perder a escolha do usuário."""
        # 0.3.x apontava para a xAI; a integração agora é com a Groq.
        url = str(self.dados.get("ia_url_base") or "")
        if "api.x.ai" in url:
            self.dados["ia_url_base"] = "https://api.groq.com/openai/v1"
        modelo = str(self.dados.get("ia_modelo") or "")
        if not modelo or modelo.startswith("grok") or modelo.startswith("gpt-4"):
            self.dados["ia_modelo"] = "openai/gpt-oss-120b"
        if "qualidade_mp3" not in bruto:
            antigo = str(bruto.get("modo_mp3") or "preservar")
            self.dados["qualidade_mp3"] = {"320": "alta", "v0": "alta",
                                           "preservar": "automatica"}.get(antigo, "automatica")
        # Migra apenas o modelo antigo padrão; preserva modelos personalizados.
        if self.dados.get("template_organizacao") == "{artista}/{artista} - {titulo}.mp3":
            self.dados["template_organizacao"] = "{artista}/{titulo}.mp3"
        # o modo legado continua coerente com a nova chave
        self.dados["modo_mp3"] = {"automatica": "preservar", "alta": "320",
                                  "personalizada": str(self.dados.get("mp3_bitrate") or 256)}
        try:
            self.dados["downloads_simultaneos"] = max(1, min(4, int(self.dados.get("downloads_simultaneos") or 2)))
            self.dados["quantidade_padrao"] = max(1, min(20, int(self.dados.get("quantidade_padrao") or 5)))
            self.dados["mp3_bitrate"] = max(128, min(320, int(self.dados.get("mp3_bitrate") or 256)))
        except (TypeError, ValueError):
            self.dados["downloads_simultaneos"] = 2
            self.dados["quantidade_padrao"] = 5
            self.dados["mp3_bitrate"] = 256

    def salvar(self) -> None:
        tmp = self.caminho.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.dados, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.caminho)

    # -- acesso -------------------------------------------------------
    def __getitem__(self, chave: str) -> Any:
        return self.dados.get(chave, PADROES.get(chave))

    def __setitem__(self, chave: str, valor: Any) -> None:
        self.dados[chave] = valor

    def get(self, chave: str, padrao: Any = None) -> Any:
        return self.dados.get(chave, PADROES.get(chave, padrao))

    def update(self, **kwargs: Any) -> None:
        self.dados.update(kwargs)
        self.salvar()

    # -- derivados ----------------------------------------------------
    @property
    def pasta_saida(self) -> Path:
        # Ler a configuração não deve criar pastas nem impedir a interface de
        # abrir quando uma unidade removível estiver desconectada.
        return Path(self["pasta_saida"] or PASTA_DOWNLOADS)

    def garantir_pasta_saida(self) -> Path:
        """Valida o destino escolhido antes de baixar; nunca redireciona arquivos."""
        pasta = self.pasta_saida
        try:
            pasta.mkdir(parents=True, exist_ok=True)
            if not pasta.is_dir():
                raise OSError("o caminho não é uma pasta")
            # Teste temporário de escrita sem alterar arquivos do usuário.
            with tempfile.TemporaryFile(dir=str(pasta)) as teste:
                teste.write(b"RiffLab")
                teste.flush()
        except (OSError, ValueError) as exc:
            raise RuntimeError(
                f"Pasta de saída indisponível ou sem permissão: {pasta}. "
                "Conecte a unidade ou escolha outra em Configurações → Áudio e destino. "
                "Nenhum áudio foi baixado.") from exc
        return pasta

    @property
    def caminho_cookies(self) -> Path:
        c = self.get("caminho_cookies") or ""
        return Path(c) if c else ARQ_COOKIES

    @property
    def pasta_biblioteca_local(self) -> Path | None:
        b = self.get("biblioteca_local") or ""
        return Path(b) if b and Path(b).exists() else None


def preparar_ambiente() -> Config:
    """Chamado no start: cria pastas, carrega config e devolve o objeto."""
    garantir_pastas()
    cfg = Config()
    if not cfg.caminho.exists():
        cfg.salvar()
    return cfg


# Windows: evita que o console pisque ao chamar ffmpeg/yt-dlp
CRIAR_SEM_JANELA = 0x08000000 if os.name == "nt" else 0

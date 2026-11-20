"""Localização e verificação das ferramentas externas (ffmpeg, ffprobe, yt-dlp)."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from .config import CRIAR_SEM_JANELA, PASTA_FERRAMENTAS, RAIZ


@dataclass
class Ferramenta:
    nome: str
    caminho: Optional[str] = None
    versao: str = ""
    erro: str = ""

    @property
    def ok(self) -> bool:
        return bool(self.caminho)

    def como_dict(self) -> Dict[str, object]:
        return {"nome": self.nome, "caminho": self.caminho, "versao": self.versao, "ok": self.ok}


_cache: Dict[str, Ferramenta] = {}


def _candidatos(nome: str) -> list[Path]:
    nomes = [f"{nome}.exe", nome] if nome not in ("ffmpeg", "ffprobe", "yt-dlp", "ytdlp") else \
            [f"{nome}.exe", nome, f"{nome}-x86_64-pc-windows-msvc.exe"]
    pastas = [PASTA_FERRAMENTAS, RAIZ, RAIZ / "bin", Path.cwd()]
    return [p / n for p in pastas for n in nomes]


def localizar(nome: str, revalidar: bool = False) -> Ferramenta:
    """Procura a ferramenta em ./ferramentas, na raiz, no cwd e no PATH."""
    if not revalidar and nome in _cache:
        return _cache[nome]

    candidatos = []
    for cand in _candidatos(nome):
        try:
            if cand.is_file():
                candidatos.append(str(cand.resolve()))
        except OSError:
            continue
    for apelido in (nome, nome.replace('-', '')):
        achado = shutil.which(apelido)
        if achado:
            candidatos.append(str(Path(achado).resolve()))

    erros = []
    for caminho in dict.fromkeys(candidatos):
        versao, erro = _versao(caminho)
        if not erro:
            f = Ferramenta(nome=nome, caminho=caminho, versao=versao)
            _cache[nome] = f
            return f
        erros.append(f'{caminho}: {erro}')
    f = Ferramenta(nome=nome, erro='; '.join(erros) if erros else 'arquivo não encontrado')
    _cache[nome] = f
    return f


def _versao(caminho: str) -> tuple[str, str]:
    try:
        # yt-dlp usa --version; ffmpeg e ffprobe usam -version.
        nome_exe = Path(caminho).name.lower().replace("-", "")
        opcao = "--version" if "ytdlp" in nome_exe or nome_exe in ("deno", "deno.exe") else "-version"
        saida = subprocess.run(
            [caminho, opcao], capture_output=True, text=True, timeout=10,
            encoding="utf-8", errors="replace", creationflags=CRIAR_SEM_JANELA,
        )
        texto = (saida.stdout or "") + (saida.stderr or "")
        if saida.returncode != 0:
            return "", f"falhou ao verificar versão (código {saida.returncode})"
        if not texto.strip():
            return "", "não informou a versão"
        nome = Path(caminho).name.lower().replace('-', '')
        if 'ytdlp' in nome:
            m = re.search(r"(\d{4}\.\d{2}\.\d{2}(?:\.\d+)?)", texto)
        elif nome in ('deno', 'deno.exe'):
            m = re.search(r"\bdeno\s+(\d+\.\d+\.\d+(?:[-+][^\s]+)?)", texto, re.I)
        elif 'ffprobe' in nome:
            m = re.search(r"\bffprobe\s+version\s+([^\s]+)", texto, re.I)
        elif 'ffmpeg' in nome:
            m = re.search(r"\bffmpeg\s+version\s+([^\s]+)", texto, re.I)
        else:
            m = None
        if m:
            return m.group(1), ""
        return "", "resposta de versão não reconhecida para esta ferramenta"
    except FileNotFoundError:
        return "", "não executa (arquivo ausente ou sem permissão)"
    except subprocess.TimeoutExpired:
        return "", "não respondeu (-version demorou demais)"
    except Exception as e:                                   # noqa: BLE001
        return "", f"falha ao executar: {e.__class__.__name__}"


def ambiente_ferramentas() -> dict[str, str]:
    """Expõe as ferramentas desta instalação aos subprocessos, sem mudar o PATH do sistema."""
    env = os.environ.copy()
    env["PATH"] = str(PASTA_FERRAMENTAS) + os.pathsep + env.get("PATH", "")
    return env


def ffmpeg() -> Ferramenta:
    return localizar("ffmpeg")


def ffprobe() -> Ferramenta:
    """ffprobe é opcional: se não existir, usamos 'ffmpeg -i' como alternativa."""
    return localizar("ffprobe")


def ytdlp() -> Ferramenta:
    f = localizar("yt-dlp")
    if not f.ok:
        alternativa = localizar("ytdlp")
        if alternativa.ok or f.erro == 'arquivo não encontrado':
            return alternativa
    return f


def status_ferramentas(revalidar: bool = True) -> Dict[str, Ferramenta]:
    yt = localizar("yt-dlp", revalidar)
    if not yt.ok:
        alternativa = localizar("ytdlp", revalidar)
        if alternativa.ok or yt.erro == 'arquivo não encontrado':
            yt = alternativa
    return {
        "ffmpeg": localizar("ffmpeg", revalidar),
        "ffprobe": localizar("ffprobe", revalidar),
        "yt-dlp": yt,
        "deno": localizar("deno", revalidar),
    }


def garantir_ffmpeg() -> Ferramenta:
    f = ffmpeg()
    if not f.ok:
        raise RuntimeError(
            "ffmpeg não encontrado. Coloque o ffmpeg.exe em "
            f"{PASTA_FERRAMENTAS} ou instale no PATH. Detalhe: {f.erro}"
        )
    return f

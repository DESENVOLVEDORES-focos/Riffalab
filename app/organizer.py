"""Organização dos arquivos finais: nomes válidos, pastas e anti-duplicata."""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Optional, Tuple

from .models import TrackMeta

# Caracteres proibidos no Windows + caracteres de controle
_PROIBIDOS = r'<>:"/\|?*'
_RE_INVALIDOS = re.compile(f"[{re.escape(_PROIBIDOS)}]")
_RE_CONTROLE = re.compile(r"[\x00-\x1f]")
_RE_ESPACOS = re.compile(r"\s+")

PALAVRAS_RESERVADAS = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def sanitizar(nome: str, limite: int = 120, _recolher_espacos: bool = True) -> str:
    """Devolve um nome de arquivo/pasta seguro para o Windows."""
    if not nome:
        return "sem_nome"
    nome = unicodedata.normalize("NFC", str(nome))
    nome = _RE_CONTROLE.sub("", nome)
    nome = _RE_INVALIDOS.sub("_", nome)
    nome = nome.replace("\n", " ").replace("\t", " ")
    # "A_ _Live_" -> "A Live"; underscores/espacos repetidos viram um espaco
    nome = re.sub(r"[_\s]{2,}", " ", nome)
    nome = re.sub(r"(?<=[A-Za-z0-9])_(?=[A-Za-z0-9])", " ", nome)
    if _recolher_espacos:
        nome = _RE_ESPACOS.sub(" ", nome).strip()
    nome = re.sub(r"\s*([-_])\s*(?=(\.\w+)$)", "", nome)   # "- .mp3" -> ".mp3"
    nome = nome.strip(" .-_")
    if not nome:
        return "sem_nome"
    if nome.upper().split(".")[0] in PALAVRAS_RESERVADAS:
        nome = f"_{nome}"
    if len(nome) > limite:
        raiz, ponto, ext = nome.rpartition(".")
        if ponto and len(ext) <= 5:
            nome = raiz[: limite - len(ext) - 1].rstrip(" .") + "." + ext
        else:
            nome = nome[:limite].rstrip(" .")
    return nome


def aplicar_template(template: str, meta: TrackMeta, ext: str = ".mp3") -> str:
    """Preenche o template de organização (ex.: {artista}/{album}/{faixa} {titulo})."""
    artista = meta.artista or "Artista desconhecido"
    album = meta.album or "Sem álbum"
    dados = {
        "artista": sanitizar(artista),
        "album": sanitizar(album),
        "titulo": sanitizar(meta.titulo or "Sem título"),
        "ano": str(meta.ano or ""),
        "faixa": f"{meta.faixa:02d}" if meta.faixa else "",
        "faixa_num": str(meta.faixa or ""),
        "genero": sanitizar(meta.genero or ""),
        "fonte": sanitizar(meta.fonte_audio or ""),
        "ext": ext.lstrip("."),
    }
    saida = template
    for chave, valor in dados.items():
        saida = saida.replace("{" + chave + "}", valor)
    # limpa separadores duplicados que sobram de campos vazios
    saida = saida.replace("//", "/").replace(" - .", ".")
    saida = re.sub(r"/{2,}", "/", saida).strip("/ ")
    partes = [sanitizar(p, limite=110) for p in saida.split("/") if p.strip()]
    if not partes:
        partes = [sanitizar(meta.titulo or "faixa")]
    if not partes[-1].lower().endswith(ext):
        partes[-1] += ext
    return "/".join(partes)


def caminho_destino(base: Path, template: str, meta: TrackMeta, ext: str = ".mp3") -> Path:
    """Caminho completo (sem criar nada), garantindo que fica dentro de `base`."""
    relativo = aplicar_template(template, meta, ext)
    alvo = (base / relativo).resolve()
    base_r = base.resolve()
    if base_r not in alvo.parents and alvo != base_r:
        # template malicioso/estranho: cai para o nome simples
        alvo = (base_r / sanitizar(f"{meta.artista} - {meta.titulo or 'faixa'}{ext}")).resolve()
    return alvo


def resolver_conflito(destino: Path, tamanho_novo: Optional[int] = None,
                      arquivo_novo: Optional[Path] = None) -> Tuple[Path, str]:
    """Reaproveita somente arquivos idênticos; outros recebem número no nome."""
    if not destino.exists():
        return destino, "novo"
    try:
        existente = destino.stat().st_size
    except OSError:
        return destino, "novo"
    if arquivo_novo and tamanho_novo is not None and existente == tamanho_novo:
        try:
            # Comparação real sem cache de tamanho/data, que pode enganar em
            # arquivos atualizados rapidamente ou com mesmo timestamp.
            with destino.open('rb') as anterior, Path(arquivo_novo).open('rb') as novo:
                iguais = True
                while True:
                    a, b = anterior.read(1024 * 1024), novo.read(1024 * 1024)
                    if a != b:
                        iguais = False
                        break
                    if not a:
                        break
            if iguais:
                return destino, "duplicado"
        except OSError:
            pass
    for n in range(2, 100):
        alternativo = destino.with_name(f"{destino.stem} ({n}){destino.suffix}")
        if not alternativo.exists():
            return alternativo, "renomeado"
    return destino.with_name(f"{destino.stem} ({destino.stat().st_mtime_ns}){destino.suffix}"), "renomeado"


def mover(origem: Path, destino: Path) -> Path:
    import shutil
    destino.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(origem), str(destino))
    return destino


def tamanho_pasta(pasta: Path, extensoes=(".mp3", ".flac", ".m4a")) -> int:
    total = 0
    for arq in pasta.rglob("*"):
        if arq.is_file() and arq.suffix.lower() in extensoes:
            try:
                total += arq.stat().st_size
            except OSError:
                pass
    return total

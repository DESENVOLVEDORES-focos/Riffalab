"""Biblioteca local: os arquivos do próprio usuário entram na comparação.

Muito útil para comparar "tenho esta música em 128 kbps" com o que existe
em melhor qualidade em outra fonte — sem precisar tocar em nada.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Dict, List, Optional

from ..config import Config, EXTENSOES_AUDIO
from ..models import AudioFormat, TrackResult
from ..audio_probe import analisar
from ..quality import eh_lossless
from ..texto import limpar_titulo, normalizar
from .base import FonteBase, Progresso, emitir


class FonteBibliotecaLocal(FonteBase):
    id = "biblioteca_local"
    nome = "Biblioteca local"
    descricao = ("Procura nos arquivos do seu computador. Serve para comparar a "
                 "qualidade do que você já tem com as opções disponíveis.")
    autorizada = True
    aviso_legal = "Seus próprios arquivos: nada é enviado para fora."

    def __init__(self, config: Optional[Config] = None) -> None:
        self.config = config

    def _pastas(self) -> List[Path]:
        pastas: List[Path] = []
        if self.config is not None:
            base = self.config.pasta_biblioteca_local
            if base:
                pastas.append(base)
            saida = Path(self.config["pasta_saida"] or "")
            if saida.exists():
                pastas.append(saida)
        return pastas

    def disponivel(self):
        pastas = self._pastas()
        if not pastas:
            return False, "Nenhuma pasta configurada (Configurações → Biblioteca local)."
        return True, ""

    def buscar(self, consulta: str, limite: int = 20) -> List[TrackResult]:
        alvo = normalizar(consulta)
        if not alvo:
            return []
        termos = [t for t in alvo.split() if len(t) > 1]
        resultados: List[TrackResult] = []
        vistos: set[str] = set()

        for pasta in self._pastas():
            try:
                arquivos = [p for p in pasta.rglob("*") if p.suffix.lower() in EXTENSOES_AUDIO]
            except OSError:
                continue
            for arq in arquivos:
                if str(arq) in vistos:
                    continue
                nome_norm = normalizar(f"{arq.parent.name} {arq.stem}")
                if not all(t in nome_norm for t in termos):
                    continue
                info = analisar(arq)
                if info.erro:
                    continue
                vistos.add(str(arq))
                formatos = [AudioFormat(
                    codec=info.codec,
                    bitrate_kbps=info.bitrate_kbps,
                    sample_rate=info.sample_rate,
                    channels=info.canais,
                    container=info.container or arq.suffix.lstrip("."),
                    url=str(arq),
                    filesize=info.tamanho,
                    lossless=info.lossless or eh_lossless(info.codec),
                    estimado=False,
                    format_id=str(arq),
                )]
                resultados.append(TrackResult(
                    uid=f"local:{abs(hash(str(arq))) & 0xFFFFFFFF:x}",
                    fonte=self.id,
                    titulo=info.tags.get("titulo") or limpar_titulo(arq.stem),
                    artista=info.tags.get("artista") or arq.parent.name,
                    album=info.tags.get("album") or "",
                    ano=None,
                    duracao_s=info.duracao_s,
                    thumb_url="",
                    pagina_url=str(arq),
                    formatos=formatos,
                    licenca="arquivo local",
                    extra={"caminho": str(arq), "tem_capa": info.tem_capa,
                           "tags": info.tags},
                ))
                if len(resultados) >= limite:
                    return resultados
        return resultados

    def baixar(self, resultado: TrackResult, formato: AudioFormat,
               destino: Path, progresso: Progresso = None) -> Path:
        origem = Path(formato.url or resultado.pagina_url)
        if not origem.is_file():
            raise FileNotFoundError(f"arquivo local não encontrado: {origem}")
        destino = Path(destino)
        destino.parent.mkdir(parents=True, exist_ok=True)
        emitir(progresso, 10, "copiando arquivo local…")
        shutil.copy2(origem, destino)
        emitir(progresso, 100, "cópia concluída")
        return destino

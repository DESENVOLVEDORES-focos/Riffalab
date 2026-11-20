"""Conversão para MP3 com FFmpeg, preservando a qualidade da origem.

Regra de ouro: se a origem JÁ é MP3 e está dentro do limite, o áudio é
copiado (`-c:a copy`, zero perda por reencode). Só há recodificação quando
o formato é diferente ou quando o usuário escolheu um alvo fixo de bitrate.
"""
from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Optional

from .audio_probe import analisar
from .config import CRIAR_SEM_JANELA
from .models import ArquivoInfo
from .tools import garantir_ffmpeg

Progresso = Optional[Callable[[int, str], None]]

_RE_TEMPO = re.compile(r"out_time_ms=(\d+)")
_RE_TEMPO2 = re.compile(r"time=(\d+):(\d+):(\d+\.\d+)")


def _emitir(cb: Progresso, pct: int, msg: str) -> None:
    if cb:
        try:
            cb(max(0, min(100, int(pct))), msg)
        except Exception:
            pass


def planejar(info: ArquivoInfo, modo: str = "automatica", bitrate: int = 256) -> dict:
    """Decide o comando: copiar ou recodificar, e com quais parâmetros.

    Modos mostrados ao usuário (proposta §5):
      * "automatica"    — o app decide pelo que veio da origem (nunca degrada);
      * "alta"          — MP3 CBR 320 kbps;
      * "personalizada" — MP3 CBR no bitrate escolhido (128–320).
    Compatibilidade: "preservar" ≈ automatica, "320" ≈ alta, "v0" ≈ alta.
    """
    modo = {"preservar": "automatica", "320": "alta", "v0": "alta"}.get(modo, modo)
    if modo == "personalizada":
        alvo = max(128, min(320, int(bitrate or 256)))
        origem_mp3 = (info.codec or "").lower() == "mp3"
        if origem_mp3 and (info.bitrate_kbps or 0) == alvo:
            return {"acao": "copiar", "args": ["-c:a", "copy"],
                    "motivo": f"já é MP3 {alvo} kbps (sem recodificar)"}
        return {"acao": "recodificar", "args": ["-c:a", "libmp3lame", "-b:a", f"{alvo}k"],
                "motivo": f"personalizado: MP3 CBR {alvo} kbps"}
    if modo == "alta":
        if (info.codec or "").lower() == "mp3" and (info.bitrate_kbps or 0) >= 320:
            return {"acao": "copiar", "args": ["-c:a", "copy"], "motivo": "já é MP3 320 kbps"}
        return {"acao": "recodificar", "args": ["-c:a", "libmp3lame", "-b:a", "320k"],
                "motivo": "alta qualidade: MP3 CBR 320 kbps"}

    codec = (info.codec or "").lower()
    origem_mp3 = codec == "mp3" or info.caminho.lower().endswith(".mp3")
    bitrate = info.bitrate_kbps or 0

    if modo in ("automatica", "preservar"):
        if origem_mp3 and (not bitrate or bitrate <= 320):
            return {"acao": "copiar", "args": ["-c:a", "copy"], "motivo": "origem já é MP3 (sem recodificar)"}
        if origem_mp3:
            return {"acao": "recodificar", "args": ["-c:a", "libmp3lame", "-b:a", "320k"],
                    "motivo": "MP3 com bitrate incomum (>320k), normalizando para 320 kbps"}
        if info.lossless:
            return {"acao": "recodificar", "args": ["-c:a", "libmp3lame", "-b:a", "320k"],
                    "motivo": "lossless convertido para MP3 320 kbps (CBR)"}
        # Escolha heurística do bitrate de saída; não garante qualidade equivalente.
        from .quality import FATOR_EQUIV
        fator = FATOR_EQUIV.get(codec, 1.0)
        alvo_br = min(320, max(128, int(round((bitrate or 192) * fator))))
        return {"acao": "recodificar", "args": ["-c:a", "libmp3lame", "-b:a", f"{alvo_br}k"],
                "motivo": (f"{codec or 'origem'} {bitrate or '?'} kbps → MP3 {alvo_br} kbps "
                           f"(alvo heurístico; pode haver perda na conversão)")}

    return {"acao": "recodificar", "args": ["-c:a", "libmp3lame", "-b:a", "320k"],
            "motivo": "modo desconhecido: 320 kbps por segurança"}


def converter_para_mp3(
    origem: str | Path,
    destino: str | Path,
    modo: str = "automatica",
    progresso: Progresso = None,
    metadados: bool = True,
    bitrate: int = 256,
) -> dict:
    """Converte/remuxa `origem` para `destino` (.mp3). Devolve um resumo."""
    origem, destino = Path(origem), Path(destino)
    ff = garantir_ffmpeg()
    destino.parent.mkdir(parents=True, exist_ok=True)

    info = analisar(origem)
    _emitir(progresso, 2, "analisando origem…")
    plano = planejar(info, modo, bitrate)

    args = [ff.caminho, "-hide_banner", "-y", "-i", str(origem), "-vn",
            "-map", "0:a:0", *plano["args"]]
    if metadados:
        args += ["-map_metadata", "0", "-id3v2_version", "3", "-write_id3v1", "1"]
    # não fazer upsample nem mexer em canais
    if info.sample_rate:
        args += ["-ar", str(info.sample_rate)]
    args += ["-progress", "pipe:1", "-nostats", str(destino)]

    duracao = info.duracao_s or 0.0
    # Um PIPE de stderr não consumido pode encher e travar o processo. O
    # arquivo temporário permite ler o diagnóstico após o término sem bloqueio.
    with tempfile.TemporaryFile(mode="w+b") as erros:
        proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=erros, text=True,
                                creationflags=CRIAR_SEM_JANELA)
        ultimo = 0
        assert proc.stdout is not None
        for linha in proc.stdout:
            m = _RE_TEMPO.search(linha)
            if m and duracao > 0:
                seg = int(m.group(1)) / 1_000_000.0
                pct = 5 + int(seg / duracao * 90)
                if pct > ultimo:
                    ultimo = pct
                    _emitir(progresso, pct, f"convertendo… {pct}%")
        proc.stdout.close()
        proc.wait()
        if proc.returncode != 0:
            erros.seek(0, 2)
            erros.seek(max(0, erros.tell() - 2000))
            detalhe = erros.read().decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"ffmpeg falhou (código {proc.returncode}) ao converter "
                               f"{origem.name}: {detalhe}")

    _emitir(progresso, 98, "verificando resultado…")
    final_info = analisar(destino)
    if final_info.erro:
        raise RuntimeError(f"MP3 gerado inválido: {final_info.erro}")
    return {
        "acao": plano["acao"],
        "motivo": plano["motivo"],
        "origem": info.como_dict(),
        "resultado": final_info.como_dict(),
        "perda": plano["acao"] == "recodificar" and not info.lossless,
    }


def extrair_audio(caminho: str | Path, destino_wav: str | Path | None = None) -> Path:
    """Decodifica para WAV (usado em análises que exigem PCM)."""
    ff = garantir_ffmpeg()
    origem = Path(caminho)
    destino = Path(destino_wav) if destino_wav else origem.with_suffix(".wav")
    subprocess.run([ff.caminho, "-hide_banner", "-y", "-i", str(origem), "-vn",
                    "-c:a", "pcm_s16le", str(destino)],
                   capture_output=True, timeout=600, creationflags=CRIAR_SEM_JANELA)
    return destino

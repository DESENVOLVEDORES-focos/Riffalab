"""Internet Archive (archive.org): acervo público, domínio público e CC.

Sem chave de API. A busca usa a API de "advancedsearch"; depois, para cada
item, lemos /metadata para descobrir os arquivos de áudio reais (MP3/FLAC/OGG)
com tamanho e duração — é daí que sai a comparação de qualidade.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..models import AudioFormat, TrackResult, bytes_legivel, hhmmss
from ..quality import eh_lossless
from ..texto import limpar_titulo, normalizar, relevancia
from .base import FonteBase, Progresso, emitir

UA = "RiffLab/0.1 (uso local)"
SEARCH = "https://archive.org/advancedsearch.php"
META = "https://archive.org/metadata/"
BAIXAR = "https://archive.org/download/"
TIMEOUT = 30

# coleções de música (evita podcasts/audiolivros)
COLECOES_MUSICA = ("audio_music", "etree", "netlabels", "opensource_audio",
                   "78rpm", "music", "audio", "unlockedrecordings")

FORMATOS_AUDIO = {
    "vbr mp3": ("mp3", False), "mp3": ("mp3", False), "320kbps mp3": ("mp3", False),
    "128kbps mp3": ("mp3", False), "flac": ("flac", True), "24bit flac": ("flac", True),
    "ogg vorbis": ("ogg", False), "ogg": ("ogg", False), "aac": ("aac", False),
    "m4a": ("m4a", False), "wav": ("wav", True), "aiff": ("aiff", True),
    "shorten": ("shn", True), "wave": ("wav", True),
}


def _get_json(url: str, timeout: int = TIMEOUT) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def _duracao(valor: Any) -> Optional[float]:
    """Aceita 213.5, '213.5', '3:33' ou '1:02:03'."""
    if valor in (None, ""):
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = str(valor).strip()
    try:
        if ":" in texto:
            partes = [float(p) for p in texto.split(":")]
            total = 0.0
            for p in partes:
                total = total * 60 + p
            return total
        return float(texto)
    except ValueError:
        return None


def _primeiro(valor: Any) -> str:
    if isinstance(valor, list):
        return str(valor[0]) if valor else ""
    return str(valor or "")


class FonteArchiveOrg(FonteBase):
    id = "archive_org"
    nome = "Internet Archive"
    descricao = ("Acervo público (domínio público, Creative Commons e gravações "
                 "autorizadas). Oferece MP3 e FLAC com metadados completos.")
    autorizada = True
    aviso_legal = ("Conteúdo de acesso livre. Respeite a licença indicada em cada "
                   "item (muitos são CC BY/CC BY-SA ou domínio público).")

    # ------------------------------------------------------------------ busca
    def disponivel(self):
        return True, ""

    def buscar(self, consulta: str, limite: int = 20) -> List[TrackResult]:
        consulta = (consulta or "").strip()
        if not consulta:
            return []
        docs = self._pesquisar_itens(consulta, max(8, min(24, limite)))
        if not docs:
            return []

        resultados: List[TrackResult] = []
        with ThreadPoolExecutor(max_workers=6) as pool:
            for item in pool.map(self._item_para_resultados, docs):
                resultados.extend(item)

        # ordena por RELEVÂNCIA para a consulta (título/artista/álbum) e só
        # depois descarta o que está muito abaixo do melhor resultado
        pontuados = []
        for r in resultados:
            nota = relevancia(consulta, r.titulo, r.artista, r.album,
                              pesos=[1.0, 0.55, 0.30])
            pontuados.append((nota, r))
        pontuados.sort(key=lambda par: (-par[0], par[1].duracao_s or 9999))
        if pontuados:
            corte = max(0.45, pontuados[0][0] * 0.62)
            pontuados = [par for par in pontuados if par[0] >= corte]
        return [r for _nota, r in pontuados[:limite]]

    def _pesquisar_itens(self, consulta: str, limite: int) -> List[Dict[str, Any]]:
        # 1ª tentativa: título do item; 2ª: metadados completos
        tentativas = [
            f'title:("{consulta}") AND mediatype:(audio)',
            f'creator:("{consulta}") AND mediatype:(audio)',
            f'("{consulta}") AND mediatype:(audio)',
        ]
        for i, q in enumerate(tentativas):
            params = [
                ("q", q),
                ("fl[]", "identifier"), ("fl[]", "title"), ("fl[]", "creator"),
                ("fl[]", "year"), ("fl[]", "date"), ("fl[]", "downloads"),
                ("fl[]", "licenseurl"), ("fl[]", "collection"),
                ("rows", str(limite)), ("page", "1"), ("output", "json"),
                ("sort[]", "downloads desc"),
            ]
            try:
                dados = _get_json(f"{SEARCH}?{urllib.parse.urlencode(params)}")
            except Exception:
                continue
            docs = (dados.get("response") or {}).get("docs") or []
            if docs:
                return docs
        return []

    def _item_para_resultados(self, doc: Dict[str, Any]) -> List[TrackResult]:
        identificador = doc.get("identifier") or ""
        if not identificador:
            return []
        try:
            meta = _get_json(f"{META}{urllib.parse.quote(identificador)}")
        except Exception:
            return []

        arquivos = meta.get("files") or []
        info_item = meta.get("metadata") or {}
        titulo_item = limpar_titulo(_primeiro(info_item.get("title") or doc.get("title")))
        artista_item = limpar_titulo(_primeiro(info_item.get("creator") or doc.get("creator")))
        album_item = _primeiro(info_item.get("album")) or _primeiro(info_item.get("collection_title"))
        ano = info_item.get("year") or doc.get("year") or ""
        licenca = _primeiro(info_item.get("licenseurl") or doc.get("licenseurl"))
        thumb = f"https://archive.org/services/img/{identificador}"

        resultados: List[TrackResult] = []
        # agrupa por "faixa" (título do arquivo) para juntar formatos do mesmo áudio
        grupos: Dict[str, List[Dict[str, Any]]] = {}
        for arq in arquivos:
            fmt = (arq.get("format") or "").strip().lower()
            if fmt not in FORMATOS_AUDIO:
                continue
            nome = arq.get("name") or ""
            if not nome.lower().endswith((".mp3", ".flac", ".ogg", ".m4a", ".wav", ".aiff", ".aac")):
                continue
            chave = (arq.get("original") or nome.rsplit(".", 1)[0]).lower()
            grupos.setdefault(chave, []).append(arq)

        for chave, arqs in grupos.items():
            formatos: List[AudioFormat] = []
            titulo_faixa = ""
            duracao = None
            for arq in arqs:
                codec, lossless = FORMATOS_AUDIO[(arq.get("format") or "").lower()]
                dur = _duracao(arq.get("length"))
                duracao = duracao or dur
                tamanho = None
                try:
                    tamanho = int(arq.get("size") or 0) or None
                except (TypeError, ValueError):
                    tamanho = None
                if not titulo_faixa:
                    titulo_faixa = arq.get("title") or ""
                bitrate = None
                if not lossless and dur and tamanho:
                    bitrate = int(round(tamanho * 8 / dur / 1000))
                formatos.append(AudioFormat(
                    codec=codec,
                    bitrate_kbps=bitrate,
                    sample_rate=None,          # o Archive não informa por arquivo
                    channels=2,
                    container=arq.get("format") or codec,
                    url=BAIXAR + urllib.parse.quote(identificador) + "/" + urllib.parse.quote(arq.get("name") or ""),
                    filesize=tamanho,
                    lossless=lossless or eh_lossless(codec),
                    estimado=True,
                    format_id=arq.get("name") or "",
                    extra={"original": arq.get("original") or "", "private": arq.get("private")},
                ))
            if not formatos:
                continue
            # duração fora do razoável (podcasts/entrevistas) não interessa
            if duracao and (duracao < 25 or duracao > 1200):
                continue

            titulo = limpar_titulo(titulo_faixa or titulo_item)
            artista = _primeiro(info_item.get("artist")) or artista_item
            if not artista:
                artista, talvez_titulo = (("", titulo_item))
                if normalizar(talvez_titulo) and normalizar(titulo) in normalizar(talvez_titulo):
                    titulo = talvez_titulo
            resultados.append(TrackResult(
                uid=f"archive:{identificador}:{chave}",
                fonte=self.id,
                titulo=titulo or titulo_item or identificador,
                artista=artista or "Internet Archive",
                album=album_item or titulo_item,
                ano=int(str(ano)[:4]) if str(ano)[:4].isdigit() else None,
                duracao_s=duracao,
                thumb_url=thumb,
                pagina_url=f"https://archive.org/details/{identificador}",
                formatos=formatos,
                licenca=licenca,
                extra={"identificador": identificador, "thumb": thumb,
                       "downloads": doc.get("downloads")},
            ))
        return resultados

    # -------------------------------------------------------------- download
    def baixar(self, resultado: TrackResult, formato: AudioFormat,
               destino: Path, progresso: Progresso = None) -> Path:
        destino = Path(destino)
        destino.parent.mkdir(parents=True, exist_ok=True)
        emitir(progresso, 2, f"baixando do Internet Archive…")
        req = urllib.request.Request(formato.url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as resp, open(destino, "wb") as saida:
            total = int(resp.headers.get("Content-Length") or formato.filesize or 0)
            baixado = 0
            while True:
                bloco = resp.read(262144)
                if not bloco:
                    break
                saida.write(bloco)
                baixado += len(bloco)
                if total:
                    emitir(progresso, 2 + int(baixado / total * 93),
                           f"baixando… {bytes_legivel(baixado)} de {bytes_legivel(total)}")
        if destino.stat().st_size < 1024:
            raise RuntimeError("download vazio ou incompleto")
        emitir(progresso, 100, "download concluído")
        return destino

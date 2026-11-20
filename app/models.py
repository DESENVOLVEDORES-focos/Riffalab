"""Modelos de dados usados por todas as camadas (sem dependência de Qt)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


def hhmmss(segundos: Optional[float]) -> str:
    if not segundos or segundos <= 0:
        return "--:--"
    s = int(round(segundos))
    h, resto = divmod(s, 3600)
    m, s = divmod(resto, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _compacto(n: float) -> str:
    """1234567 → '1,2 mi'."""
    n = float(n or 0)
    for limite, sufixo in ((1_000_000_000, " bi"), (1_000_000, " mi"), (1_000, " mil")):
        if n >= limite:
            return f"{n / limite:.1f}".replace(".", ",") + sufixo
    return str(int(n))


def _data_br(iso: str) -> str:
    """'1989-03-14' → '14/03/1989' (só quando o formato é o esperado)."""
    partes = (iso or "").split("-")
    if len(partes) == 3 and all(x.isdigit() for x in partes):
        return f"{partes[2]}/{partes[1]}/{partes[0]}"
    return iso


def bytes_legivel(n: Optional[float]) -> str:
    if not n or n <= 0:
        return "-"
    for unidade in ("B", "KB", "MB", "GB"):
        if n < 1024 or unidade == "GB":
            return f"{n:.0f} {unidade}" if unidade == "B" else f"{n:.1f} {unidade}"
        n /= 1024.0
    return f"{n:.1f} GB"


@dataclass
class AudioFormat:
    """Um fluxo de áudio oferecido por uma fonte."""
    codec: str = "?"                       # mp3, flac, aac, opus...
    bitrate_kbps: Optional[int] = None     # None = lossless/desconhecido
    sample_rate: Optional[int] = None
    channels: Optional[int] = None
    container: str = ""
    url: str = ""
    filesize: Optional[int] = None
    lossless: bool = False
    estimado: bool = False                 # qualidade inferida, não medida
    format_id: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

    def descricao_curta(self) -> str:
        partes = [self.codec.upper() or "?"]
        if self.bitrate_kbps:
            partes.append(f"{self.bitrate_kbps} kbps")
        elif self.lossless:
            partes.append("lossless")
        if self.sample_rate:
            partes.append(f"{self.sample_rate / 1000:g} kHz")
        if self.channels == 1:
            partes.append("mono")
        elif self.channels == 2:
            partes.append("estéreo")
        return " · ".join(partes)


@dataclass
class TrackResult:
    """Um resultado de pesquisa, já com a lista de formatos disponíveis."""
    uid: str
    fonte: str                              # archive_org, biblioteca_local, ytdlp
    titulo: str
    artista: str = ""
    album: str = ""
    ano: Optional[int] = None
    duracao_s: Optional[float] = None
    thumb_url: str = ""
    pagina_url: str = ""
    formatos: List[AudioFormat] = field(default_factory=list)
    licenca: str = ""
    disponivel: bool = True
    aviso: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)
    # melhor qualidade de VÍDEO encontrada (resolucao, fps, vcodec, formato).
    # Só é informativa: o MP3 vem da melhor faixa de áudio.
    video: Dict[str, Any] = field(default_factory=dict)
    # --- dados de pesquisa (aparecem no cartão e alimentam o filtro ao vivo) ---
    canal: str = ""                         # nome do canal/uploader
    visualizacoes: Optional[int] = None
    publicado_em: str = ""                  # AAAA-MM-DD
    incorporavel: Optional[bool] = None     # playable_in_embed
    ao_vivo: bool = False                   # suspeita/confirmação de show
    ao_vivo_certeza: str = ""               # "confirmado" | "provavel" | ""
    sinais_ao_vivo: List[str] = field(default_factory=list)
    nota_musica: float = 0.0                # prioridade (estúdio > clipe > ao vivo)
    filtrado: bool = False
    motivos_filtro: List[str] = field(default_factory=list)

    # -- conveniências de pesquisa ------------------------------------
    def resumo_publico(self) -> str:
        """'1,2 mi de visualizações · 14/03/1989' (o que existir)."""
        partes = []
        if self.visualizacoes:
            partes.append(f"{_compacto(self.visualizacoes)} de visualizações")
        if self.publicado_em:
            partes.append(_data_br(self.publicado_em))
        return "  ·  ".join(partes)

    def alerta(self) -> str:
        """Aviso curto para o cartão ('' quando não há nada a avisar)."""
        if self.ao_vivo_certeza == "confirmado":
            return "gravação ao vivo confirmada pelo yt-dlp"
        if self.ao_vivo_certeza == "provavel":
            return "Possível gravação ao vivo — confira antes de selecionar"
        return ""

    # -- conveniências ------------------------------------------------
    def resumo_video(self) -> str:
        """Ex.: '1080p · 30 fps · vp9' (vazio quando não há informação)."""
        if not self.video:
            return ""
        partes = []
        resolucao = self.video.get("resolucao") or ""
        if resolucao:
            partes.append(str(resolucao))
        if self.video.get("fps"):
            partes.append(f"{self.video['fps']} fps")
        codec = (self.video.get("vcodec") or "").split(".")[0]
        if codec and codec != "none":
            partes.append(codec)
        return " · ".join(partes)

    def resumo_audio(self) -> str:
        melhor = self.melhor
        return melhor.descricao_curta() if melhor else ""

    @property
    def melhor(self) -> Optional[AudioFormat]:
        if not self.formatos:
            return None
        from .quality import pontuar
        return max(self.formatos, key=pontuar)

    def texto_qualidade(self) -> str:
        m = self.melhor
        if not m:
            return "qualidade não verificada"
        return m.descricao_curta()

    def formatos_ordenados(self) -> List[AudioFormat]:
        from .quality import pontuar
        return sorted(self.formatos, key=pontuar, reverse=True)

    def resumo(self) -> Dict[str, Any]:
        m = self.melhor
        return {
            "titulo": self.titulo, "artista": self.artista, "album": self.album,
            "ano": self.ano, "duracao": self.duracao_s, "fonte": self.fonte,
            "codec": m.codec if m else "", "bitrate": m.bitrate_kbps if m else None,
            "taxa": m.sample_rate if m else None,
        }


@dataclass
class TrackMeta:
    """Metadados que serão gravados no arquivo final."""
    titulo: str = ""
    artista: str = ""
    album: str = ""
    ano: Optional[int] = None
    faixa: Optional[int] = None
    total_faixas: Optional[int] = None
    disco: Optional[int] = None
    genero: str = ""
    capa: Optional[str] = None          # caminho do JPG
    origem_capa: str = ""
    fonte_audio: str = ""
    # --- campos detalhados (proposta §3 e §5) ---
    artista_album: str = ""             # TPE2
    artistas_participantes: List[str] = field(default_factory=list)
    compositores: List[str] = field(default_factory=list)     # TCOM
    letristas: List[str] = field(default_factory=list)        # TEXT
    produtores: List[str] = field(default_factory=list)       # TPRO
    gravadora: str = ""                 # TPUB
    data_lancamento: str = ""           # TDRC completo (AAAA-MM-DD)
    isrc: str = ""
    mbid: str = ""
    fonte_identificacao: str = ""       # "groq" | "itunes+musicbrainz" | ...

    def vazio(self) -> bool:
        return not (self.titulo or self.artista)

    def como_dict(self) -> Dict[str, Any]:
        return {
            "titulo": self.titulo, "artista": self.artista, "album": self.album,
            "ano": self.ano, "faixa": self.faixa, "genero": self.genero,
            "capa": self.capa, "origem_capa": self.origem_capa,
            "compositores": self.compositores, "letristas": self.letristas,
            "produtores": self.produtores, "gravadora": self.gravadora,
            "data_lancamento": self.data_lancamento, "isrc": self.isrc,
            "fonte_identificacao": self.fonte_identificacao,
        }


@dataclass
class Identificacao:
    """Resultado da identificação musical (Groq/Groq), com o que foi confirmado."""
    ok: bool = False
    origem: str = ""                    # "groq"
    modelo: str = ""
    confianca: float = 0.0              # 0..1 informada pela IA
    titulo: str = ""
    artista: str = ""
    artistas_participantes: List[str] = field(default_factory=list)
    banda: str = ""
    compositores: List[str] = field(default_factory=list)
    letristas: List[str] = field(default_factory=list)
    produtores: List[str] = field(default_factory=list)
    album: str = ""
    ano: Optional[int] = None
    data_lancamento: str = ""
    genero: str = ""
    faixa: Optional[int] = None
    gravadora: str = ""
    isrc: str = ""
    mbid_gravacao: str = ""
    mbid_release_group: str = ""
    versao: str = ""                    # estudio | ao vivo | remaster | cover...
    verificado_musicbrainz: bool = False
    campos_incertos: List[str] = field(default_factory=list)
    observacoes: str = ""
    erro: str = ""
    segundos: float = 0.0

    def resumo(self) -> str:
        """Linha curta para a interface."""
        pedacos = []
        if self.titulo:
            pedacos.append(f"{self.artista or '?'} — {self.titulo}")
        if self.album:
            pedacos.append(self.album + (f" ({self.ano})" if self.ano else ""))
        if self.versao and self.versao not in ("estudio", "studio"):
            pedacos.append(f"versão {self.versao}")
        return "  ·  ".join(pedacos)

    def como_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok, "origem": self.origem, "modelo": self.modelo,
            "confianca": self.confianca, "titulo": self.titulo, "artista": self.artista,
            "album": self.album, "ano": self.ano, "genero": self.genero,
            "compositores": self.compositores, "produtores": self.produtores,
            "versao": self.versao, "verificado_musicbrainz": self.verificado_musicbrainz,
            "campos_incertos": self.campos_incertos, "erro": self.erro,
            "segundos": self.segundos,
        }


@dataclass
class CoverResult:
    caminho: Optional[str] = None
    fonte: str = ""
    largura: int = 0
    altura: int = 0
    score: float = 0.0
    album: str = ""
    artista: str = ""
    ano: Optional[int] = None
    observacao: str = ""
    # outras capas válidas encontradas (para o usuário escolher, §2.1)
    alternativas: List["CoverResult"] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.caminho)

    def dimensoes(self) -> str:
        return f"{self.largura}x{self.altura}" if self.caminho else "-"

    def credito(self) -> str:
        """'Album — Artista (2003) · Cover Art Archive · 1.00'."""
        pedacos = []
        if self.album:
            pedacos.append(self.album)
        if self.artista:
            pedacos.append(self.artista)
        if self.ano:
            pedacos.append(f"({self.ano})")
        titulo = " — ".join(pedacos[:1]) if pedacos else ""
        resto = " ".join(pedacos[1:])
        texto = " ".join(t for t in (titulo, resto) if t).strip()
        fonte = self.fonte.replace("_", " ").capitalize() if self.fonte else "fonte desconhecida"
        nota = f"{self.score:.2f}" if self.score else "-"
        return f"{texto or 'sem dados do álbum'}  ·  {fonte}  ·  correspondência {nota}"


@dataclass
class ArquivoInfo:
    """Resultado da análise de um arquivo de áudio local."""
    caminho: str = ""
    codec: str = ""
    bitrate_kbps: Optional[int] = None
    sample_rate: Optional[int] = None
    canais: Optional[int] = None
    duracao_s: Optional[float] = None
    container: str = ""
    lossless: bool = False
    tamanho: int = 0
    tags: Dict[str, str] = field(default_factory=dict)
    tem_capa: bool = False
    capa_bytes: int = 0
    erro: str = ""

    def como_dict(self) -> Dict[str, Any]:
        return {
            "caminho": self.caminho, "codec": self.codec, "bitrate": self.bitrate_kbps,
            "sample_rate": self.sample_rate, "canais": self.canais, "duracao": self.duracao_s,
            "lossless": self.lossless, "tamanho": self.tamanho, "tem_capa": self.tem_capa,
        }

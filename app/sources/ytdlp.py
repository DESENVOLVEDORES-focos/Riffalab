"""Fonte opcional baseada no yt-dlp (executável local do próprio usuário).

IMPORTANTE — leia antes de ativar:
  * esta fonte é DESLIGADA por padrão e exige consentimento explícito nas
    Configurações;
  * use somente com conteúdo que você tem direito de baixar (domínio público,
    Creative Commons, canais que autorizam download, seu próprio material);
  * baixar conteúdo protegido sem autorização viola os termos das plataformas
    e a legislação de direitos autorais — a responsabilidade é de quem usa;
  * se `cookies.txt` existir, ele é passado ao yt-dlp por caminho, sem que o
    aplicativo leia, exiba ou registre o conteúdo em log.
"""
from __future__ import annotations

import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlsplit

from ..config import CRIAR_SEM_JANELA, Config
from ..models import AudioFormat, TrackResult, bytes_legivel
from ..quality import eh_lossless
from ..metadata import consulta_formatos
from ..texto import (artista_do_titulo, limpar_titulo, parece_canal,
                     separar_artista_titulo, similaridade)
from ..tools import ambiente_ferramentas, ffmpeg, ytdlp
from .base import FonteBase, Progresso, emitir

_RE_PCT = re.compile(r"\[download\]\s+([\d.]+)%")
_RE_ERRO = re.compile(r"^\s*ERROR:\s*(.+)$", re.MULTILINE)

_DICAS = (
    ("sign in to confirm", "o YouTube pediu verificação de robô — use um cookies.txt "
                           "atualizado do mesmo navegador/rede (Configurações → cookies)"),
    ("not a bot", "o YouTube pediu verificação de robô — use um cookies.txt atualizado"),
    ("private video", "o vídeo é privado"),
    ("video unavailable", "o vídeo não está disponível nesta região/conta"),
    ("age", "o vídeo tem restrição de idade — precisa de cookies de uma conta logada"),
    ("unsupported url", "o yt-dlp não reconhece esse endereço"),
    ("timed out", "a plataforma não respondeu a tempo"),
    ("http error 403", "a plataforma recusou o acesso (403)"),
    ("http error 429", "muitas consultas seguidas (429) — espere um pouco"),
)


def _motivo_erro(saida_erro: str, codigo: int = 0) -> str:
    """Transforma o stderr do yt-dlp numa frase curta e útil."""
    texto = (saida_erro or "").strip()
    achados = _RE_ERRO.findall(texto)
    base = achados[-1].strip() if achados else ""
    if not base:
        linhas = [l.strip() for l in texto.splitlines() if l.strip()]
        base = linhas[-1] if linhas else f"yt-dlp terminou com código {codigo}"
    baixo = base.lower()
    for chave, dica in _DICAS:
        if chave in baixo:
            return f"{dica} (yt-dlp: {base[:90]})"
    return base[:180]


def _aviso_extracao(stderr: str) -> str:
    """Interpreta sinais conhecidos sem expor cookies, caminhos ou URLs."""
    baixo = (stderr or "").lower()
    if any(s in baixo for s in ("no supported javascript runtime", "no supported javascript runtimes",
                                "javascript runtime could not be found", "js runtimes: none")):
        return ("o yt-dlp não encontrou um runtime JavaScript compatível; "
                "confira o Deno em Configurações → Ferramentas externas")
    if any(s in baixo for s in ("n challenge solving failed", "signature solving failed",
                                "js challenge", "challenge solver script")):
        return ("o yt-dlp informou um problema no desafio JavaScript do YouTube; "
                "isso pode acontecer mesmo com o Deno instalado")
    if "only images are available" in baixo:
        return "o yt-dlp encontrou somente imagens, sem formato de áudio disponível"
    return ""


class FonteYtDlp(FonteBase):
    id = "ytdlp"
    nome = "yt-dlp"
    descricao = ("Pesquisa em plataformas de vídeo usando o yt-dlp instalado por "
                 "você. Ative apenas para conteúdo que você pode baixar.")
    autorizada = False            # depende do conteúdo; exige consentimento
    usa_cookies = True
    aviso_legal = ("Use somente com conteúdo autorizado (CC, domínio público, seu). "
                   "O RiffLab não hospeda nem distribui mídia.")

    def __init__(self, config: Optional[Config] = None) -> None:
        self.config = config

    # ------------------------------------------------------------------ infra
    def _exe(self) -> Optional[str]:
        f = ytdlp()
        return f.caminho if f.ok else None

    def disponivel(self):
        """Disponível quando o yt-dlp.exe existe.

        A fonte só entra na pesquisa se estiver marcada em Configurações →
        Fontes (é o padrão). O aviso de uso responsável aparece na interface.
        """
        ferramenta = ytdlp()
        if not ferramenta.ok:
            return False, ("yt-dlp indisponível: coloque um executável compatível em "
                           f"ferramentas/ ou no PATH. Detalhe: {ferramenta.erro}")
        return True, ""

    def _args_base(self, tentativas: int = 3) -> List[str]:
        exe = self._exe()
        if not exe:
            raise RuntimeError("yt-dlp não encontrado")
        args = [exe, "--no-color", "--ignore-config",
                "--socket-timeout", "20", "--retries", str(tentativas)]
        cookies = self.config.caminho_cookies if self.config else None
        if self.config and self.config.get("usar_cookies") and cookies and Path(cookies).is_file():
            args += ["--cookies", str(cookies)]        # só o caminho, nunca o conteúdo
        ff = ffmpeg()
        if ff.ok:
            # O caminho do executável também funciona com espaços ou nome
            # alternativo; passar apenas a pasta pressupõe ffmpeg.exe padrão.
            args += ["--ffmpeg-location", str(ff.caminho)]
        return args

    def _rodar(self, args: List[str], timeout: int = 120) -> tuple[int, str, str]:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout,
                           creationflags=CRIAR_SEM_JANELA, encoding="utf-8", errors="replace",
                           env=ambiente_ferramentas())
        return p.returncode, p.stdout or "", p.stderr or ""

    # ------------------------------------------------------------------ busca
    def buscar(self, consulta: str, limite: int = 20) -> List[TrackResult]:
        ok, motivo = self.disponivel()
        if not ok:
            raise RuntimeError(motivo)          # a busca mostra o motivo na tela
        n = max(1, min(30, limite))
        consulta = consulta.strip()
        direto = consulta.lower().startswith(('http://', 'https://'))
        if direto:
            url = urlsplit(consulta)
            host = (url.hostname or '').lower()
            if host not in ('youtube.com', 'www.youtube.com', 'm.youtube.com',
                            'music.youtube.com', 'youtu.be', 'www.youtu.be'):
                raise ValueError('Use um link de vídeo do YouTube ou pesquise por música e artista.')
            alvo = consulta
        else:
            alvo = f"ytsearch{n}:{consulta}"
        args = self._args_base() + ["--flat-playlist", "--dump-single-json",
                                    "--no-playlist", "--", alvo]
        try:
            codigo, saida, erro = self._rodar(args, timeout=120)
        except subprocess.TimeoutExpired:
            raise RuntimeError("o yt-dlp passou de 120 s sem responder") from None
        except Exception as exc:                                  # noqa: BLE001
            raise RuntimeError(f"não foi possível executar o yt-dlp: {exc}") from None
        if codigo != 0 or not saida.strip():
            from ..logging_setup import registrar_erro
            registrar_erro('Pesquisa yt-dlp', f'código {codigo}: {erro or "resposta vazia"}')
            raise RuntimeError(_motivo_erro(erro, codigo))
        try:
            dados = json.loads(saida)
        except json.JSONDecodeError:
            raise RuntimeError("o yt-dlp devolveu uma resposta ilegível "
                               "(atualize o yt-dlp.exe)") from None

        resultados: List[TrackResult] = []
        entradas = dados.get("entries") if "entries" in dados else ([dados] if direto else [])
        for entrada in entradas or []:
            if not entrada:
                continue
            bruto = entrada.get("title") or ""
            canal = entrada.get("channel") or entrada.get("uploader") or ""
            # "Artista - Título" só vale se o lado esquerdo bater com o canal;
            # caso contrário o canal é o artista (e os metadados refinam depois)
            canal_limpo = re.sub(r"\s*[-–—]\s*Topic\s*$", "", canal, flags=re.I).strip()
            esquerda, direita = separar_artista_titulo(bruto)
            if esquerda and similaridade(esquerda, canal_limpo) >= 0.55:
                artista, titulo = esquerda, direita
            else:
                artista, titulo = canal_limpo, bruto
            duracao = entrada.get("duration")
            thumbs = entrada.get("thumbnails") or []
            thumb = ""
            if thumbs:
                thumb = (thumbs[-1].get("url") or "")
            elif entrada.get("thumbnail"):
                thumb = entrada["thumbnail"]
            ident = entrada.get("id") or ""
            url = entrada.get("webpage_url") or (consulta if direto else entrada.get("url")) or ""
            if not url and ident:
                # o --flat-playlist às vezes devolve só o id: sem URL o vídeo
                # não pode ser detalhado nem pré-visualizado
                url = f"https://www.youtube.com/watch?v={ident}"
            elif url and not url.startswith("http"):
                url = f"https://www.youtube.com/watch?v={ident or url}"
            resultado = TrackResult(
                uid=f"ytdlpid:{entrada.get('id')}",
                fonte=self.id,
                titulo=limpar_titulo(titulo or bruto),
                artista=artista or canal,
                album="",
                ano=None,
                duracao_s=float(duracao) if duracao else None,
                thumb_url=thumb,
                pagina_url=url,
                formatos=[],           # preenchidos por detalhar()
                licenca="conferir licença na origem",
                aviso="qualidade a verificar",
                extra={"canal": canal, "id": entrada.get("id"), "url": url},
            )
            # o modo --flat-playlist omite quase tudo: preenche o que vier
            # (alguns campos aparecem dependendo da versão do yt-dlp) e deixa
            # o resto para enriquecer()/detalhar().
            resultado.canal = canal or canal_limpo
            self._aplicar_metadados(resultado, entrada)
            if direto and entrada.get('formats'):
                self._aplicar_json(resultado, entrada)
            resultados.append(resultado)
        return resultados

    # ------------------------------------------------- metadados do vídeo
    def _aplicar_metadados(self, resultado: TrackResult, dados: Dict[str, Any]) -> None:
        """Copia para o TrackResult os campos que a UI usa (proposta §2.1).

        Nada é inventado: só entra o que veio no JSON do yt-dlp.
        """
        extra = resultado.extra

        def primeiro(*chaves: str) -> Any:
            for chave in chaves:
                valor = dados.get(chave)
                if valor not in (None, "", []):
                    return valor
            return None

        canal = str(primeiro("channel", "uploader", "channel_id") or "")
        if canal:
            # O sufixo Topic é um sinal útil de canal de artista; não removê-lo.
            resultado.canal = canal
        if not resultado.artista and canal:
            # usar o canal como artista gera tag e capa erradas; se o título tem
            # "Artista - Título", o lado esquerdo é o intérprete
            original = str(extra.get("titulo_original") or resultado.titulo or "")
            esquerda, direita = artista_do_titulo(original)
            if esquerda:
                resultado.artista = esquerda
                resultado.titulo = limpar_titulo(direita)
            else:
                resultado.artista = canal

        vistas = primeiro("view_count", "concurrent_view_count")
        if vistas is not None:
            try:
                resultado.visualizacoes = int(vistas)
            except (TypeError, ValueError):
                pass

        data = str(primeiro("release_date", "upload_date", "modified_date") or "")
        if re.fullmatch(r"\d{8}", data):
            data = f"{data[:4]}-{data[4:6]}-{data[6:]}"
        if data:
            resultado.publicado_em = data[:10]

        if "playable_in_embed" in dados:
            resultado.incorporavel = bool(dados.get("playable_in_embed"))
        elif "age_limit" in dados and dados.get("age_limit"):
            resultado.incorporavel = False

        if dados.get("duration") and not resultado.duracao_s:
            try:
                resultado.duracao_s = float(dados["duration"])
            except (TypeError, ValueError):
                pass

        thumb = dados.get("thumbnail")
        if not thumb:
            thumbs = dados.get("thumbnails") or []
            if thumbs:
                thumb = thumbs[-1].get("url") or ""
        if thumb and not resultado.thumb_url:
            resultado.thumb_url = thumb

        if dados.get("title") and not resultado.extra.get("titulo_original"):
            extra["titulo_original"] = str(dados["title"])[:200]
        if dados.get("description"):
            extra["descricao"] = str(dados["description"])[:600]

        # sinais de "ao vivo" — os que o yt-dlp souber responder
        for chave in ("live_status", "was_live", "is_live", "is_upcoming",
                      "availability", "age_limit", "uploader_id", "channel_id",
                      "channel_is_verified", "categories", "tags"):
            if chave in dados and dados[chave] not in (None, "", []):
                valor = dados[chave]
                extra[chave] = valor[:5] if isinstance(valor, list) else valor
        if dados.get("webpage_url"):
            extra["url"] = dados["webpage_url"]
            if not resultado.pagina_url:
                resultado.pagina_url = dados["webpage_url"]
        if dados.get("id"):
            extra.setdefault("id", dados["id"])

    # -------------------------------------------------------- formatos reais
    def _aplicar_json(self, resultado: TrackResult, dados: Dict[str, Any]) -> TrackResult:
        """Transforma o JSON completo do yt-dlp em formatos de áudio + metadados."""
        formatos: List[AudioFormat] = []
        melhor_video: Dict[str, Any] = {}
        chave_video: tuple = ()
        # av1 < vp9 < h264 em eficiência: para a MESMA altura/fps, o codec mais
        # eficiente entrega a mesma qualidade com menos bits
        preferencia_codec = {"av01": 3, "vp9": 2, "vp09": 2, "avc1": 1, "h264": 1}
        for f in dados.get("formats") or []:
            vcodec = f.get("vcodec") or "none"
            if vcodec != "none":
                altura = int(f.get("height") or 0)
                fps = int(round(float(f.get("fps") or 0)))
                taxa = float(f.get("vbr") or f.get("tbr") or 0)
                base_codec = vcodec.split(".")[0].lower()
                chave = (altura, fps, preferencia_codec.get(base_codec, 0), taxa)
                if chave > chave_video:
                    chave_video = chave
                    melhor_video = {
                        "resolucao": (f"{altura}p" if altura
                                      else str(f.get("resolution") or "")),
                        "altura": altura,
                        "fps": fps or None,
                        "vcodec": vcodec.split(".")[0],
                        "formato": (f.get("ext") or "").lower(),
                    }
            if (f.get("acodec") or "none") == "none":
                continue
            codec = (f.get("acodec") or "").split(".")[0].lower()
            codec = {"mp4a": "aac", "opus": "opus", "vorbis": "vorbis", "mp3": "mp3"}.get(codec, codec)
            tamanho = f.get("filesize") or f.get("filesize_approx")
            abr = f.get("abr")
            formatos.append(AudioFormat(
                codec=codec or "?",
                bitrate_kbps=int(round(abr)) if abr else None,
                sample_rate=f.get("asr"),
                channels=f.get("audio_channels"),
                container=(f.get("ext") or "").lower(),
                url=resultado.pagina_url or resultado.extra.get("url", ""),
                filesize=tamanho,
                lossless=eh_lossless(codec),
                estimado=not bool(abr),
                format_id=str(f.get("format_id") or ""),
                extra={"nota": f.get("format_note") or "",
                       "metodos": list(f.get("_metodos") or []),
                       "divergencias": f.get("_divergencias") or {},
                       # Apenas propriedades técnicas públicas; nunca URLs ou headers.
                       "detalhes_audio": {k: f[k] for k in (
                           "acodec", "vcodec", "abr", "tbr", "asr", "audio_channels",
                           "ext", "audio_ext", "filesize", "filesize_approx", "format_note",
                           "protocol", "language", "container", "bits_per_sample", "has_drm",
                           "_abr_da_tabela", "_asr_tabela") if k in f}},
            ))
        # Remove apenas o mesmo ID; codecs e bitrates iguais podem ter IDs distintos.
        vistos = set()
        unicos: List[AudioFormat] = []
        for fmt in sorted(formatos, key=lambda x: (-(x.bitrate_kbps or 0), -(x.sample_rate or 0))):
            marca = fmt.format_id or (fmt.codec, fmt.bitrate_kbps, fmt.sample_rate, fmt.container)
            if marca in vistos:
                continue
            vistos.add(marca)
            unicos.append(fmt)

        self._aplicar_metadados(resultado, dados)
        if melhor_video:
            resultado.video = melhor_video
            resultado.extra["video"] = melhor_video
        if not unicos:
            resultado.extra["erro_detalhe"] = ("o vídeo não expõe nenhum formato de áudio "
                                               "(talvez seja apenas imagem/ao vivo)")
            resultado.aviso = "qualidade não detectada"
            return resultado

        resultado.formatos = unicos
        resultado.aviso = ""
        resultado.extra.pop("erro_detalhe", None)
        return resultado

    def detalhar_primeiro(self, resultado: TrackResult) -> TrackResult:
        """Consulta primeiro o JSON real; os outros métodos ficam para a próxima etapa."""
        url = resultado.pagina_url or resultado.extra.get('url')
        if not url:
            resultado.extra['erro_detalhe'] = 'sem URL para consultar'
            resultado.aviso = 'qualidade não detectada'
            return resultado
        try:
            consulta = consulta_formatos.consultar(url, self._args_base(tentativas=1),
                                                   self._rodar, _aviso_extracao, indices=(1,))
            resultado.extra['metodos_consulta'] = consulta['metodos']
            resultado.extra['consulta_em_andamento'] = True
            resultado.formatos = []
            self._aplicar_json(resultado, consulta)
            if not resultado.formatos:
                # Outros métodos podem encontrar áudio; não declarar falha final.
                resultado.extra.pop('erro_detalhe', None)
                resultado.aviso = 'aguardando os outros métodos'
            return resultado
        except Exception:
            resultado.extra['consulta_em_andamento'] = True
            resultado.extra['metodos_consulta'] = [
                {'nome': n, 'estado': 'falhou' if i == 1 else 'aguardando',
                 'motivo': 'não foi possível iniciar' if i == 1 else '', 'quantidade': 0}
                for i, n in enumerate(consulta_formatos.NOMES)]
            return resultado

    def detalhar(self, resultado: TrackResult, ao_parcial=None) -> TrackResult:
        """Consulta o yt-dlp para listar os formatos de áudio reais.

        Nunca levanta exceção: se o yt-dlp falhar (verificação de robô, vídeo
        privado, filtro de região, timeout), o motivo fica em
        `resultado.extra["erro_detalhe"]` e `resultado.aviso` avisa a interface,
        para o cartão não ficar "detectando" para sempre.
        """
        metodos_anteriores = resultado.extra.get("metodos_consulta") or []
        incompleto = (resultado.extra.get("consulta_em_andamento") or
                      any(m.get('estado') in ('consultando', 'aguardando') for m in metodos_anteriores))
        if resultado.formatos and metodos_anteriores and not incompleto:
            return resultado
        url = resultado.pagina_url or resultado.extra.get("url")
        if not url:
            resultado.extra["erro_detalhe"] = "sem URL para consultar"
            resultado.aviso = "qualidade não detectada"
            return resultado
        try:
            def publicar_parcial(dados):
                if not ao_parcial:
                    return
                from copy import deepcopy
                parcial = deepcopy(resultado)
                parcial.extra["metodos_consulta"] = dados["metodos"]
                parcial.extra["consulta_em_andamento"] = True
                parcial.formatos = []
                self._aplicar_json(parcial, dados)
                if parcial.formatos:
                    ao_parcial(parcial)

            consulta = consulta_formatos.consultar(url, self._args_base(tentativas=1),
                                                   self._rodar, _aviso_extracao,
                                                   ao_parcial=publicar_parcial if ao_parcial else None)
        except Exception:
            resultado.extra.pop("consulta_em_andamento", None)
            for metodo in resultado.extra.get("metodos_consulta") or []:
                if metodo.get("estado") in ("consultando", "aguardando"):
                    metodo.update(estado="falhou", motivo="consulta interrompida")
            resultado.extra["erro_detalhe"] = "não foi possível iniciar a consulta dos formatos"
            resultado.aviso = ("formatos anteriores não confirmados" if resultado.formatos
                               else "qualidade não detectada")
            return resultado
        resultado.extra["metodos_consulta"] = consulta["metodos"]
        resultado.extra.pop("consulta_em_andamento", None)
        anteriores = list(resultado.formatos)
        resultado.formatos = []
        self._aplicar_json(resultado, consulta)
        if not resultado.formatos:
            motivos = [x.get("motivo") for x in consulta["metodos"] if x.get("motivo")]
            motivo = motivos[0] if motivos else "nenhum método encontrou áudio disponível"
            if anteriores:
                resultado.formatos = anteriores
                resultado.extra['erro_detalhe'] = ('Consulta complementar não confirmou os formatos da '
                    'primeira consulta: ' + motivo + '. Eles podem ter ficado indisponíveis.')
                resultado.aviso = 'formatos anteriores não confirmados'
            else:
                resultado.extra["erro_detalhe"] = motivo
        return resultado

    def _json_do_video(self, resultado: TrackResult) -> Optional[Dict[str, Any]]:
        """Lista formatos sem escolher nem baixar um formato do vídeo.

        -F --print-json dá a tabela e um JSON na saída. Diferentemente de -J,
        a listagem não exige que o seletor padrão encontre um formato baixável.
        Avisos vão para stderr; nunca guardamos a saída integral ou URLs assinadas.
        """
        url = resultado.pagina_url or resultado.extra.get("url")
        if not url:
            resultado.extra["erro_detalhe"] = "sem URL para consultar"
            resultado.aviso = "qualidade não detectada"
            return None
        resultado.extra.pop("diagnostico_extracao", None)
        args = self._args_base(tentativas=1) + ["-F", "--print-json", "--no-playlist", "--", url]
        try:
            codigo, saida, erro = self._rodar(args, timeout=45)
        except subprocess.TimeoutExpired:
            resultado.extra["erro_detalhe"] = "o yt-dlp passou de 45 s sem responder"
            resultado.aviso = "qualidade não detectada"
            return None
        except Exception as exc:
            resultado.extra["erro_detalhe"] = f"{exc.__class__.__name__}: falha ao executar o yt-dlp"
            resultado.aviso = "qualidade não detectada"
            return None
        diagnostico = _aviso_extracao(erro)
        if diagnostico:
            resultado.extra["diagnostico_extracao"] = diagnostico
        if codigo != 0 or not saida.strip():
            resultado.extra["erro_detalhe"] = diagnostico or _motivo_erro(erro, codigo)
            resultado.aviso = "qualidade não detectada"
            return None
        # A tabela -F precede um objeto JSON por linha. Não exibir nem salvar o
        # JSON: ele pode conter URLs temporárias e dados da sessão.
        for linha in reversed(saida.splitlines()):
            if not linha.lstrip().startswith("{"):
                continue
            try:
                dados = json.loads(linha)
            except json.JSONDecodeError:
                continue
            if isinstance(dados, dict) and isinstance(dados.get("formats"), list):
                return dados
        resultado.extra["erro_detalhe"] = diagnostico or (
            "o yt-dlp não retornou uma lista de formatos legível; verifique sua versão")
        resultado.aviso = "qualidade não detectada"
        return None

    # ------------------------------------------------------- enriquecimento
    def enriquecer(self, resultados: List[TrackResult], limite: int = 10,
                   workers: int = 4,
                   progresso: Optional[Callable[[int, int], None]] = None
                   ) -> List[TrackResult]:
        """Completa canal/visualizações/data/ao vivo dos primeiros N resultados.

        O `--flat-playlist` da busca não traz `channel`, `live_status` nem
        `view_count`; então consultamos cada vídeo em paralelo (mesmo caminho
        de `detalhar`, que tem timeout). Se um falhar, o cartão
        continua válido — só fica sem os dados extras.
        """
        alvos = [r for r in resultados[:max(0, limite)] if not r.extra.get("metodos_consulta")]
        if not alvos:
            return resultados
        feitos = 0

        def tarefa(r: TrackResult) -> TrackResult:
            try:
                return self.detalhar(r)
            except Exception:                                     # noqa: BLE001
                return r

        try:
            with ThreadPoolExecutor(max_workers=max(1, min(6, workers))) as pool:
                for _ in pool.map(tarefa, alvos):
                    feitos += 1
                    if progresso:
                        try:
                            progresso(feitos, len(alvos))
                        except Exception:                          # noqa: BLE001
                            pass
        except Exception:                                         # noqa: BLE001
            pass
        return resultados

# -------------------------------------------------------------- download
    def baixar(self, resultado: TrackResult, formato: AudioFormat,
               destino: Path, progresso: Progresso = None) -> Path:
        destino = Path(destino)
        destino.parent.mkdir(parents=True, exist_ok=True)
        url = resultado.pagina_url or formato.url
        if not url:
            raise RuntimeError("o resultado não possui link para download")
        emitir(progresso, 2, "iniciando download (yt-dlp)…")

        # baixa o melhor áudio disponível no formato nativo; a conversão para
        # MP3 é feita depois pelo módulo convert (ffmpeg), com -c:a copy quando
        # o contêiner já é compatível.
        args = self._args_base() + [
            "-f", formato.format_id or "bestaudio/best",
            "--no-playlist", "--newline", "--no-part",
            "-o", str(destino.with_name("audio_orig.%(ext)s")),
        ]
        if formato.format_id.startswith("bestaudio") or not formato.format_id:
            args[args.index("-f") + 1] = "bestaudio/best"
        args.append(url)

        # Uma escolha explícita de formato não deve ser trocada sem o usuário
        # perceber. Apenas a opção automática permite "bestaudio/best".
        escolha = formato.format_id or "bestaudio/best"
        if escolha.startswith("bestaudio"):
            escolha = "bestaudio/best"
        args[args.index("-f") + 1] = escolha
        p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, creationflags=CRIAR_SEM_JANELA,
                             encoding="utf-8", errors="replace", env=ambiente_ferramentas())
        ultimos: List[str] = []
        assert p.stdout is not None
        for linha in p.stdout:
            ultimos.append(linha.strip())
            ultimos = ultimos[-12:]
            m = _RE_PCT.search(linha)
            if m:
                emitir(progresso, 2 + int(float(m.group(1)) * 0.93),
                       f"baixando… {m.group(1)}%")
        p.stdout.close()
        p.wait()
        if p.returncode != 0:
            # --no-part pode deixar um arquivo incompleto com nome definitivo.
            for parcial in destino.parent.glob('audio_orig.*'):
                if parcial.is_file():
                    parcial.unlink()
            # Retém o diagnóstico recente; o console oculta URLs e credenciais.
            detalhe = " | ".join(l for l in ultimos if l)[-16000:]
            contexto = (f"Não foi possível baixar o formato escolhido ({escolha}); "
                        "nenhum outro formato foi usado. " if escolha != 'bestaudio/best' else "")
            raise RuntimeError(f"{contexto}yt-dlp falhou ({p.returncode}): {detalhe}")

        encontrados = sorted(destino.parent.glob("audio_orig.*"),
                             key=lambda x: x.stat().st_size, reverse=True)
        if not encontrados:
            raise RuntimeError("yt-dlp não gerou arquivo de áudio")
        return encontrados[0]

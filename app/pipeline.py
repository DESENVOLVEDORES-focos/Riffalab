"""Pipeline completo: baixar → analisar → metadados/capa → converter → tags → organizar.

Este módulo não conhece Qt: recebe callbacks de progresso e devolve um dict
com o resultado. Assim ele é testável pela linha de comando e reaproveitável.
"""
from __future__ import annotations

import hashlib
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from . import audio_probe, convert, organizer, sources, tagging, arquivos_baixados
from .texto import artista_do_titulo, limpar_titulo, parece_canal, separar_artista_titulo
from .ia import identificador
from .config import Config, PASTA_TEMP
from .metadata import covers
from .models import AudioFormat, TrackMeta, TrackResult

Progresso = Optional[Callable[[int, str], None]]


def _emitir(cb: Progresso, pct: int, msg: str) -> None:
    if cb:
        try:
            cb(max(0, min(100, int(pct))), msg)
        except Exception:
            pass


def _pasta_temp(uid: str) -> Path:
    chave = hashlib.sha1(uid.encode("utf-8")).hexdigest()[:12]
    PASTA_TEMP.mkdir(parents=True, exist_ok=True)
    # Duas tarefas da mesma música podem iniciar no mesmo segundo.
    return Path(tempfile.mkdtemp(prefix=f"{chave}_", dir=PASTA_TEMP))


def montar_metadados(resultado: TrackResult, config: Config,
                     extra: Optional[Dict[str, Any]] = None,
                     progresso: Progresso = None,
                     ident=None) -> TrackMeta:
    """Cruza fonte + iTunes/MusicBrainz + identificação por IA para fechar os dados.

    Dados explícitos do usuário são aplicados na preparação. A IA sugere
    identidade, os catálogos complementam a edição e tudo requer revisão.
    """
    extra = extra or {}
    titulo = extra.get("titulo") or resultado.titulo
    artista = extra.get("artista") or resultado.artista
    # "DisneyMusicVEVO" como artista gera arquivo e capa errados: quando o
    # título traz "Artista - Título" e o artista é um canal, fica o lado esquerdo
    if artista and parece_canal(artista) and titulo:
        candidato, resto = artista_do_titulo(titulo)
        if candidato:
            artista, titulo = candidato, limpar_titulo(resto)
    album = extra.get("album") or resultado.album
    ano = extra.get("ano") or resultado.ano

    # Antes de consultar catálogos, conferir se a sugestão da IA se refere à
    # mesma música/versão. Assim a busca pode usar grafia e álbum identificados,
    # sem consultar o álbum de outra faixa por causa de uma alucinação.
    usar_ia = (ident is not None and getattr(ident, 'ok', False)
               and float(getattr(ident, 'confianca', 0) or 0)
               >= max(0.70, float(config.get('ia_min_confianca') or 0)))
    incertos = set()
    if usar_ia:
        from .texto import normalizar, similaridade
        from .metadata.correspondencia import pontuar
        incertos = {normalizar(str(c)).replace(' ', '_') for c in (ident.campos_incertos or [])}
        artista_consulta = ident.artista if not artista or parece_canal(artista) else artista
        usar_ia = ('titulo' not in incertos and 'artista' not in incertos
                   and similaridade(titulo, ident.titulo) >= .70
                   and pontuar(titulo, artista_consulta,
                               cand={'titulo': ident.titulo, 'artista': ident.artista}).aprovado)
    titulo_busca = ident.titulo if usar_ia and ident.titulo else titulo
    artista_busca = ident.artista if usar_ia and ident.artista else artista
    album_busca = (ident.album if usar_ia and ident.album and 'album' not in incertos else album)
    ano_busca = (ident.ano if usar_ia and ident.ano and 'ano' not in incertos
                  and 'album' not in incertos else ano)
    dados: Dict[str, Any] = {}
    if config.get("gravar_tags", True):
        _emitir(progresso, 52, "consultando metadados…")
        try:
            dados = covers.metadados_completos(titulo_busca, artista_busca, album_busca, ano_busca)
        except Exception:
            dados = {}

    meta = TrackMeta(
        titulo=str(extra.get("titulo") or dados.get("titulo") or titulo or "").strip(),
        artista=str(extra.get("artista") or dados.get("artista") or artista or "").strip(),
        album=str(extra.get("album") or dados.get("album") or album or "").strip(),
        ano=extra.get("ano") or dados.get("ano") or ano,
        faixa=extra.get("faixa") or dados.get("faixa"),
        total_faixas=dados.get("total_faixas"),
        disco=dados.get("disco"),
        genero=str(extra.get("genero") or dados.get("genero") or "").strip(),
        artista_album=str(dados.get("artista_album") or "").strip(),
        fonte_identificacao="fonte + " + ("+".join(dados.get("fontes") or []) or "vídeo"),
    )

    # IA pode estar incorreta mesmo com confiança alta. Campos explicitamente
    # incertos não sobrescrevem dados; o usuário pode revisar tudo antes do lote.
    if usar_ia:
        def certo(chave):
            return chave not in incertos and bool(getattr(ident, chave, None))
        # Número e total do catálogo anterior não pertencem necessariamente ao
        # novo álbum sugerido pela IA. Nunca misturar faixas de edições diferentes.
        if certo('album') and meta.album and normalizar(ident.album) != normalizar(meta.album):
            meta.faixa = meta.total_faixas = meta.disco = None
            meta.ano = None
            meta.artista_album = ''
        for chave in ('titulo', 'artista', 'album', 'ano', 'genero', 'faixa'):
            if not certo(chave) or (chave in ('faixa', 'ano') and 'album' in incertos):
                continue
            if chave == 'faixa' and (not certo('album') or
                    normalizar(ident.album) != normalizar(meta.album)):
                continue
            # Para a mesma edição, os números e o gênero do catálogo têm
            # prioridade; a IA preenche os que permanecerem vazios.
            if chave in ('faixa', 'ano', 'genero') and getattr(meta, chave, None):
                continue
            setattr(meta, chave, getattr(ident, chave))
        if certo('artista_album') and 'album' not in incertos and not meta.artista_album:
            meta.artista_album = ident.artista_album
        for chave in ('artistas_participantes', 'compositores', 'letristas', 'produtores',
                      'gravadora', 'data_lancamento', 'isrc'):
            if not certo(chave):
                continue
            if chave == 'data_lancamento' and ('album' in incertos or not meta.ano or
                    str(ident.data_lancamento)[:4] != str(meta.ano)):
                continue
            setattr(meta, chave, getattr(ident, chave))
        meta.mbid = ident.mbid_gravacao or ident.mbid_release_group
        meta.fonte_identificacao = "groq" + (" + musicbrainz" if ident.verificado_musicbrainz else "")
    # TPE2 sem identificação específica usa o intérprete como alternativa.
    meta.artista_album = meta.artista_album or meta.artista

    return meta


def buscar_capa(meta: TrackMeta, config: Config, thumb_extra: str = "",
                progresso: Progresso = None, ident=None):
    _emitir(progresso, 60, "procurando a capa…")
    # canal não é artista: "Disney", "FulanoVEVO", "Canal Official" etc. fazem a
    # busca pegar a capa de OUTRA música com o mesmo nome. Nesses casos tenta o
    # "Artista - Título" que costuma vir no nome do vídeo.
    artista_capa = meta.artista or ""
    if artista_capa and parece_canal(artista_capa):
        candidato, _ = separar_artista_titulo(meta.titulo or "")
        if candidato and not parece_canal(candidato):
            artista_capa = candidato
    try:
        capa = covers.encontrar_capa(
            meta.titulo or "", artista_capa, meta.album or "", meta.ano,
            fontes=config.get("fontes_capa"),
            minimo_lado=int(config.get("tamanho_minimo_capa") or 300),
            thumb_extra=thumb_extra,
            identificacao=ident,
            usar_miniatura=bool(config.get("usar_thumb_como_capa", False)),
        )
    except Exception as exc:                                     # noqa: BLE001
        from .models import CoverResult
        return CoverResult(observacao=f"falha ao buscar capa: {exc}")
    return capa


def processar_resultado(
    resultado: TrackResult,
    config: Config,
    formato: Optional[AudioFormat] = None,
    progresso: Progresso = None,
    meta_extra: Optional[Dict[str, Any]] = None,
    fonte=None,
    aprovador_capa=None,
    preparacao: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Executa o fluxo completo para UM resultado. Nunca levanta exceção:
    devolve {'ok': bool, 'erro': str, ...} para a interface decidir."""
    inicio = time.time()
    try:
        config.garantir_pasta_saida()
    except RuntimeError as exc:
        return {"ok": False, "erro": str(exc)}
    fonte = fonte or sources.por_id(resultado.fonte, config)
    if fonte is None:
        return {"ok": False, "erro": f"fonte desconhecida: {resultado.fonte}"}
    formato = formato or resultado.melhor
    if not formato:
        # fontes resumidas (yt-dlp) precisam de uma segunda consulta
        try:
            resultado = fonte.detalhar(resultado) if fonte else resultado
            formato = resultado.melhor
        except Exception as exc:                                  # noqa: BLE001
            return {"ok": False, "erro": f"não foi possível obter formatos: {exc}"}
    if not formato:
        return {"ok": False, "erro": "nenhum formato de áudio disponível"}

    pasta = _pasta_temp(resultado.uid)
    bruto: Optional[Path] = None
    mp3_temp: Optional[Path] = None
    relatorio: Dict[str, Any] = {"ok": False, "uid": resultado.uid, "fonte": resultado.fonte}

    try:
        # 1) download / obtenção do áudio
        _emitir(progresso, 2, "obtendo o áudio…")
        extensao = f".{formato.container or formato.codec or 'bin'}".replace("..", ".")
        bruto = fonte.baixar(resultado, formato, pasta / f"origem{extensao}", progresso)
        relatorio["arquivo_bruto"] = str(bruto)

        # 2) análise real do que foi baixado
        _emitir(progresso, 48, "analisando qualidade…")
        info_origem = audio_probe.analisar(bruto)
        if info_origem.erro:
            raise RuntimeError(f"arquivo inválido: {info_origem.erro}")
        relatorio["origem"] = info_origem.como_dict()

        if preparacao is not None:
            # A escolha do usuário e os metadados foram preparados antes do lote.
            ident = preparacao.get("ident")
            meta = preparacao["meta"]
            capa = preparacao["capa"]
            meta.fonte_audio = fonte.nome
            if ident is not None:
                relatorio["identificacao"] = ident.como_dict()
            if capa.ok and not Path(capa.caminho).is_file():
                raise RuntimeError("A capa escolhida não está mais disponível; prepare-a novamente.")
        else:
            # 2.5) IDENTIFICAÇÃO MUSICAL COM IA (Groq) — proposta §6, passo 6
            ident = None
            ia_ligada = bool(config.get("ia_ativa"))
            if ia_ligada:
                ident = identificador.identificar(resultado, config, progresso)
                relatorio["identificacao"] = ident.como_dict()
                if ident.ok:
                    _emitir(progresso, 58, f"música identificada: {ident.resumo()}"[:120])
                else:
                    _emitir(progresso, 58, f"IA não confirmou: {(ident.erro or '')[:80]}")

            # 3) metadados + capa
            meta = montar_metadados(resultado, config, meta_extra, progresso, ident=ident)
            meta.fonte_audio = fonte.nome
            if config.get("baixar_capa", True):
                capa = buscar_capa(meta, config,
                                   resultado.thumb_url or resultado.extra.get("thumb", ""),
                                   progresso, ident=ident)
            else:
                capa = type("SemCapa", (), {"ok": False, "observacao": "busca de capa desligada",
                                            "fonte": "", "caminho": "", "score": 0})()
            # 3.5) CONFIRMAÇÃO DA CAPA (etapa 9 do fluxo) — a decisão é do usuário:
            # ele vê imagem, álbum, artista, ano, fonte e correspondência, e pode
            # trocar por outra opção ou recusar. Sem aprovador, segue a automática.
            if capa.ok and aprovador_capa is not None and config.get("confirmar_capa", True):
                _emitir(progresso, 68, "confirmando a capa…")
                try:
                    escolhida = aprovador_capa(capa, {
                        "titulo": meta.titulo, "artista": meta.artista,
                        "album": meta.album, "ano": meta.ano})
                except Exception:                                     # noqa: BLE001
                    escolhida = capa
                if escolhida is None:
                    from .models import CoverResult as _Cover
                    capa = _Cover(observacao="capa recusada pelo usuário "
                                             "(nenhuma capa foi gravada)")
                else:
                    capa = escolhida
                    if getattr(capa, "alternativas", None):
                        capa.alternativas = []


        if capa.ok:
            meta.capa = capa.caminho
            meta.origem_capa = capa.fonte
            relatorio["capa"] = {"fonte": capa.fonte, "dimensoes": capa.dimensoes(),
                                 "score": capa.score, "arquivo": capa.caminho,
                                 "album": capa.album, "artista": capa.artista}
        else:
            meta.capa = ""
            meta.origem_capa = ""
            relatorio["capa"] = {"fonte": "", "observacao": capa.observacao}

        # 4) conversão para MP3
        modo = str(config.get("qualidade_mp3") or "automatica")
        bitrate_alvo = int(config.get("mp3_bitrate") or 256)
        destino_temp = pasta / "final.mp3"
        _emitir(progresso, 70, "convertendo para MP3…")
        conv = convert.converter_para_mp3(bruto, destino_temp, modo=modo,
                                          bitrate=bitrate_alvo,
                                          progresso=lambda p, m: _emitir(progresso, 70 + int(p * 0.18), m),
                                          metadados=False)
        mp3_temp = destino_temp
        # A duração vem do MP3 convertido, não da IA nem da duração do vídeo.
        duracao_final = audio_probe.analisar(mp3_temp).duracao_s
        meta.duracao_s = duracao_final if duracao_final and duracao_final > 0 else None
        relatorio["conversao"] = {"acao": conv["acao"], "motivo": conv["motivo"]}

        # 5) tags + capa embutida
        if preparacao is not None or config.get("gravar_tags", True):
            _emitir(progresso, 90, "gravando título/artista/álbum e capa…")
            meta_sem_capa = None
            if preparacao is None and not config.get("incorporar_capa", True):
                meta_sem_capa = meta.capa
                meta.capa = ""          # tags sim, APIC não
            if preparacao is not None and not capa.ok:
                # Se a origem já era MP3, copiar pode preservar uma capa antiga.
                tagging.remover_capa(mp3_temp)
            apagar = list((preparacao or {}).get("apagar_tags", []))
            # Num MP3 copiado, tags antigas de outra edição não podem preencher
            # silenciosamente campos que a preparação deixou desconhecidos.
            if preparacao is not None:
                for campo in ('album', 'ano', 'faixa', 'genero', 'artista_album', 'duracao_s'):
                    if not getattr(meta, campo, None) and campo not in apagar:
                        apagar.append(campo)
            resultado_tags = tagging.gravar(mp3_temp, meta, id3v1=bool(config.get("gravar_id3v1", True)),
                                            apagar_campos=apagar)
            if preparacao is not None and capa.ok and not resultado_tags.get("capa"):
                raise RuntimeError(resultado_tags.get("aviso_capa") or "Não foi possível gravar a capa escolhida.")
            if meta_sem_capa:
                meta.capa = meta_sem_capa
            relatorio["tags"] = tagging.ler(mp3_temp)

        # Identificação local independente das demais opções de tags. A marca
        # fica no MP3 final, inclusive quando a gravação de outras tags está desligada.
        arquivos_baixados.marcar(mp3_temp, resultado)
        if preparacao is not None and not capa.ok:
            # Não concluir nem mover um MP3 com APIC se foi pedido sem capa;
            # falhas ao ler/gravar também precisam aparecer, não ser omitidas.
            tagging.garantir_sem_capa(mp3_temp)

        # 6) organização / deduplicação
        _emitir(progresso, 96, "organizando o arquivo…")
        base = config.pasta_saida
        template = str(config.get("template_organizacao") or "{artista}/{titulo}.mp3")
        alvo = organizer.caminho_destino(base, template, meta)
        tamanho = mp3_temp.stat().st_size
        alvo, situacao = organizer.resolver_conflito(alvo, tamanho, mp3_temp)

        if situacao == "duplicado" and not config.get("sobrescrever"):
            relatorio.update({"ok": True, "duplicado": True, "caminho": str(alvo),
                              "mensagem": "arquivo já existia (nada foi sobrescrito)"})
        else:
            organizer.mover(mp3_temp, alvo)
            mp3_temp = None
            relatorio.update({"ok": True, "duplicado": False, "caminho": str(alvo)})

        info_final = audio_probe.analisar(alvo)
        relatorio.update({
            "meta": meta.como_dict(),
            "final": info_final.como_dict(),
            "tamanho": tamanho,
            "duracao_s": info_final.duracao_s,
            "segundos": round(time.time() - inicio, 1),
        })
        _emitir(progresso, 100, "concluído")
        return relatorio

    except Exception as exc:                                      # noqa: BLE001
        relatorio.update({"ok": False, "erro": f"{exc.__class__.__name__}: {exc}"})
        _emitir(progresso, 100, f"erro: {exc}")
        return relatorio
    finally:
        manter = bool(config.get("manter_temporarios", False))
        if manter:
            relatorio["temp"] = str(pasta)
        # A pasta é exclusiva desta tarefa; remove também arquivos parciais
        # deixados por yt-dlp ou FFmpeg quando algum estágio falha.
        if not manter:
            shutil.rmtree(pasta, ignore_errors=True)


def limpar_temp(manter_dias: float = 1.0) -> int:
    """Remove pastas temporárias antigas. Devolve quantas foram apagadas."""
    if not PASTA_TEMP.exists():
        return 0
    limite = time.time() - manter_dias * 86400
    removidas = 0
    for pasta in PASTA_TEMP.iterdir():
        try:
            if pasta.is_dir() and pasta.stat().st_mtime < limite:
                shutil.rmtree(pasta, ignore_errors=True)
                removidas += 1
        except OSError:
            continue
    return removidas

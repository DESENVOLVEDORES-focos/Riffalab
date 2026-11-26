"""Serviço de pesquisa: consulta várias fontes em paralelo e unifica a lista."""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Dict, List, Optional, Tuple

from .config import Config
from .models import TrackResult
from .logging_setup import registrar_erro
from .pesquisa import filtros
from .pesquisa import resultados as resultados_mod
from .quality import pontuar
from .sources import todas_as_fontes
from .texto import normalizar, relevancia

Progresso = Optional[Callable[[int, str], None]]


def _emitir(cb: Progresso, pct: int, msg: str) -> None:
    if cb:
        try:
            cb(pct, msg)
        except Exception:
            pass


def pesquisar(consulta: str, config: Config, limite: int = 20,
              fontes_ids: Optional[List[str]] = None,
              progresso: Progresso = None,
              ordenar_por: str = "relevancia",
              enriquecer_automatico: bool = False) -> Dict[str, object]:
    """Devolve {'resultados', 'fontes', 'erros', 'segundos', 'consulta'}."""
    consulta = (consulta or "").strip()
    inicio = time.time()
    if not consulta:
        return {"resultados": [], "fontes": [], "erros": {}, "segundos": 0.0, "consulta": ""}

    # A seleção da tela é a fonte de verdade, mesmo para fontes que não estão
    # marcadas nas preferências persistentes. Nunca trocar silenciosamente por
    # outra fonte quando o yt-dlp estiver indisponível.
    todas = todas_as_fontes(config)
    selecionadas = fontes_ids if fontes_ids is not None else list(config.get("fontes_ativas") or [])
    escolhidas = {}
    erros: Dict[str, str] = {}
    for fid in selecionadas:
        fonte = todas.get(fid)
        if fonte is None:
            erros[fid] = "fonte desconhecida"
            continue
        ok, motivo = fonte.disponivel()
        if ok:
            escolhidas[fid] = fonte
        else:
            erros[fid] = motivo or "fonte indisponível"

    resultados: List[TrackResult] = []
    usadas: List[str] = []
    total = max(1, len(escolhidas))
    feitos = 0

    _emitir(progresso, 3, f"consultando {total} fonte(s)…")
    with ThreadPoolExecutor(max_workers=min(4, total)) as pool:
        futuros = {}
        for fid, fonte in escolhidas.items():
            por_fonte = max(4, limite // max(1, len(escolhidas)) + 4)
            futuros[pool.submit(fonte.buscar, consulta, por_fonte)] = (fid, fonte)
        for futuro in as_completed(futuros):
            fid, fonte = futuros[futuro]
            try:
                achados = futuro.result() or []
                resultados.extend(achados)
                if achados:
                    usadas.append(fonte.nome)
            except Exception as exc:                              # noqa: BLE001
                erros[fid] = f"{exc.__class__.__name__}: {exc}"
            feitos += 1
            _emitir(progresso, 3 + int(feitos / total * 60),
                    f"{fonte.nome}: {len(resultados)} resultado(s)")

    for fid, motivo in erros.items():
        registrar_erro(f'Pesquisa — fonte {fid}', motivo)

    # Mesmos título/artista/duração não significam o mesmo vídeo: podem ser
    # uploads ou versões diferentes. Remove apenas a mesma identidade da fonte.
    unicos: Dict[Tuple[str, str], TrackResult] = {}
    for r in resultados:
        chave = (r.fonte, r.uid)
        atual = unicos.get(chave)
        if atual is None:
            unicos[chave] = r
        else:
            # fica com o que tem melhor qualidade
            if (r.melhor and (not atual.melhor or pontuar(r.melhor) > pontuar(atual.melhor))):
                unicos[chave] = r
    lista = list(unicos.values())
    # canal NÃO é artista: se o título tem "Artista - Título" e o artista atual
    # é nome de canal/selo, usa o lado esquerdo (evita capa e tags erradas)
    lista = [resultados_mod.enriquecer(r) for r in lista]

    # ---- enriquecimento + filtro de shows (v0.5.0) -------------------
    # 1) o --flat-playlist não traz canal/visualizações/ao vivo: completa os
    #    primeiros N vídeos em paralelo (nunca bloqueia a interface)
    limite_verif = int(config.get("verificar_automatico", 10))
    fonte_ytdlp = escolhidas.get("ytdlp")
    if fonte_ytdlp is not None and limite_verif > 0 and enriquecer_automatico:
        vistos_por_id = {}
        for r in lista:
            if r.fonte == "ytdlp":
                vistos_por_id.setdefault(r.extra.get("id") or r.uid, r)
        alvos = list(vistos_por_id.values())[:limite_verif]
        if alvos:
            _emitir(progresso, 66, f"conferindo {len(alvos)} vídeo(s)…")
            try:
                fonte_ytdlp.enriquecer(
                    alvos, limite=len(alvos),
                    workers=min(4, len(alvos)),
                    progresso=lambda feito, total: _emitir(
                        progresso, 66 + int(feito / max(1, total) * 8),
                        f"conferindo vídeos: {feito}/{total}"))
            except Exception as exc:                              # noqa: BLE001
                erros.setdefault("ytdlp", f"enriquecimento: {exc}")
                registrar_erro('Pesquisa — enriquecimento yt-dlp', f'{type(exc).__name__}: {exc}')

    # 1.5) o enriquecimento pode ter descoberto o canal: refaz a separação
    # canal/artista agora que o título original está disponível
    if fonte_ytdlp is not None:
        lista = [resultados_mod.enriquecer(r) for r in lista]

    # 2) filtro de ao vivo: rebaixa/oculta SEM apagar nada (vai para `filtrados`)
    evitar = bool(config.get("evitar_ao_vivo", True))
    _emitir(progresso, 74, "separando shows e gravações ao vivo…")
    visiveis, filtrados = filtros.aplicar(lista, consulta, evitar_ao_vivo=evitar)

    _emitir(progresso, 80, "ordenando resultados…")
    if ordenar_por == "qualidade":
        visiveis.sort(key=lambda r: (pontuar(r.melhor) if r.melhor else -1,
                                     r.nota_musica), reverse=True)
    else:
        visiveis.sort(key=lambda r: (r.nota_musica,
                                     relevancia(consulta, r.titulo, r.artista, r.album)),
                      reverse=True)

    # mantém os melhores sem cortar demais (os filtrados ficam na lista à parte,
    # para o botão "Mostrar resultados filtrados")
    visiveis = [r for r in visiveis if r.titulo][:limite]
    filtrados = [r for r in filtrados if r.titulo][:limite]
    _emitir(progresso, 100, f"{len(visiveis)} resultado(s)")
    return {
        "resultados": visiveis,
        "filtrados": filtrados,
        "evitar_ao_vivo": evitar,
        "fontes": usadas,
        "erros": erros,
        "segundos": round(time.time() - inicio, 1),
        "consulta": consulta,
    }


def pesquisar_varias(consultas: List[str], config: Config, limite: int = 20,
                     fontes_ids: Optional[List[str]] = None,
                     progresso: Progresso = None,
                     ordenar_por: str = "relevancia", ao_parcial=None) -> List[Dict[str, object]]:
    """Pesquisa cada termo separadamente, com concorrência limitada e ordem estável.

    Falhas em um termo não interrompem os demais. Entradas vazias são ignoradas;
    termos repetidos são mantidos, pois correspondem aos campos do usuário.
    """
    termos = [str(c).strip() for c in consultas if str(c).strip()]
    if not termos:
        return []
    respostas: List[Optional[Dict[str, object]]] = [None] * len(termos)
    with ThreadPoolExecutor(max_workers=min(3, len(termos))) as pool:
        futuros = {pool.submit(pesquisar, termo, config, limite, fontes_ids,
                               ordenar_por=ordenar_por, enriquecer_automatico=False): i
                   for i, termo in enumerate(termos)}
        feitos = 0
        for futuro in as_completed(futuros):
            i = futuros[futuro]
            try:
                respostas[i] = futuro.result()
            except Exception as exc:  # um termo com erro não apaga os outros
                registrar_erro('Pesquisa múltipla', f'{type(exc).__name__}: {exc}')
                respostas[i] = {"consulta": termos[i], "resultados": [], "filtrados": [],
                                "fontes": [], "segundos": 0,
                                "erros": {"pesquisa": f"{type(exc).__name__}: {exc}"}}
            if ao_parcial:
                try:
                    ao_parcial(i, respostas[i])
                except Exception:
                    pass  # uma falha de notificação não interrompe pesquisas
            feitos += 1
            _emitir(progresso, int(feitos * 100 / len(termos)),
                    f"Pesquisas concluídas: {feitos}/{len(termos)}")
    return [r for r in respostas if r is not None]

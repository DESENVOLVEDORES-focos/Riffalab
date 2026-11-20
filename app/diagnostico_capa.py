"""Mostra POR QUE uma capa foi escolhida (ou por que nenhuma foi).

Uso:
    python -m app.diagnostico_capa "Christina Vidal" "Take Me Away"
    python -m app.diagnostico_capa "Christina Vidal" "Take Me Away" "Freaky Friday"

Imprime os candidatos do iTunes e do MusicBrainz com as similaridades e a
decisão final — é o jeito mais rápido de entender uma capa estranha.
"""
from __future__ import annotations

import sys
from typing import Any, Dict, List

from .config import preparar_ambiente
from .logging_setup import configurar
from .metadata import covers, itunes, musicbrainz
from .texto import similaridade


def _linha(rotulo: str, valor: Any) -> str:
    return f"  {rotulo:<26} {valor}"


def rodar(titulo: str, artista: str = "", album: str = "", ano: int | None = None) -> int:
    configurar()
    preparar_ambiente()
    print(f"\nTítulo: {titulo!r}   Artista: {artista!r}   Álbum: {album!r}\n")

    print("[iTunes] resultados encontrados e como são pontuados:")
    consulta = " ".join(x for x in (artista, titulo, album) if x) or titulo
    itens: List[Dict[str, Any]] = itunes.buscar(consulta, limite=10)
    if not itens:
        print("  (nenhum resultado)")
    for item in itens:
        s_tit = similaridade(titulo, item.get("trackName") or "")
        s_art = similaridade(artista, item.get("artistName") or "") if artista else 0.0
        s_alb = similaridade(album, item.get("collectionName") or "") if album else 0.0
        nota = s_tit * 0.6 + s_art * 0.3 + s_alb * 0.1
        marca = "ok " if (s_tit >= 0.85 and (not artista or s_art >= 0.55)
                          and (not album or s_alb >= 0.60)) else "NÃO"
        print(f"  [{marca}] {nota:5.2f}  {(item.get('trackName') or '')[:34]:34} | "
              f"{(item.get('artistName') or '')[:24]:24} | "
              f"{(item.get('collectionName') or '')[:30]}")

    escolhido = itunes.melhor_faixa(titulo, artista, album, ano)
    print(_linha("iTunes escolheu:", (escolhido or {}).get("album") or "nada"))
    if escolhido:
        print(_linha("  artista:", escolhido.get("artista")))
        print(_linha("  score:", escolhido.get("score")))

    print("\n[MusicBrainz] gravações aceitas (confiança >= 0.62):")
    try:
        gravacoes = musicbrainz.buscar_gravacao(titulo, artista, album, limite=4)
    except Exception as exc:                                     # noqa: BLE001
        gravacoes = []
        print(f"  (falhou: {exc})")
    if not gravacoes:
        print("  (nenhuma)")
    for g in gravacoes:
        print(f"  {float(g.get('confianca') or 0):5.2f}  {(g.get('titulo') or '')[:34]:34} | "
              f"{(g.get('artista') or '')[:22]:22} | {(g.get('album') or '')[:30]}")
    capa_mb = musicbrainz.melhor_capa(titulo, artista, album)
    print(_linha("MB/CAA escolheu:", capa_mb.get("album") or "nada"))

    # ---- cascata de provedores (v0.5.0): candidatos, notas e recusas ----
    from .metadata import busca_capas
    aprovadas, reprovadas = busca_capas.coletar(
        titulo, artista, album, ano, fontes=["coverartarchive", "itunes"],
        minimo_lado=300)
    print("\n[CANDIDATOS] imagem baixada, validada e pontuada:")
    if not aprovadas and not reprovadas:
        print("  (nenhum candidato)")
    for a in aprovadas:
        print(f"  [ok ] {a.score:5.2f}  {a.capa.fonte:24} {a.largura}x{a.altura}  "
              f"{(a.capa.album or '')[:34]:34} | {(a.capa.artista or '')[:20]}")
        print(f"        {a.explicacao}")
    for a in reprovadas:
        print(f"  [NÃO] {a.score:5.2f}  {a.capa.fonte:24} {(a.capa.album or '')[:34]:34}"
              f" | {a.motivo}")
    if busca_capas.ambiguidade(aprovadas):
        print("  → EMPATE TÉCNICO: a interface pergunta ao usuário qual usar.")

    print("\n[DECISÃO FINAL]")
    resultado = covers.encontrar_capa(titulo, artista, album, ano=ano,
                                     fontes=["itunes", "coverartarchive"])
    if resultado.ok:
        print(_linha("capa:", resultado.caminho))
        print(_linha("fonte:", resultado.fonte))
        print(_linha("álbum da capa:", resultado.album))
        print(_linha("artista da capa:", resultado.artista))
        print(_linha("confiança:", resultado.score))
        print(_linha("dimensões:", f"{resultado.largura}x{resultado.altura}"))
        if getattr(resultado, "alternativas", None):
            print(_linha("outras opções:", len(resultado.alternativas)))
            for alt in resultado.alternativas[:4]:
                print(f"      · {alt.fonte} {alt.dimensoes()} "
                      f"{round(alt.score, 2)} {(alt.album or '')[:40]}")
    else:
        print(_linha("resultado:", "NENHUMA CAPA APLICADA"))
        print(_linha("motivo:", resultado.observacao))
    if not artista and not album:
        print("\nDica: informe o artista (2º argumento). Sem artista o app não aplica")
        print("      capa — é o que evita a capa de outra música com o mesmo nome.")
    return 0 if resultado.ok else 1


def main(argv: List[str]) -> int:
    if len(argv) < 3:
        print(__doc__)
        return 2
    titulo = argv[2]
    artista = argv[1]
    album = argv[3] if len(argv) > 3 else ""
    ano = int(argv[4]) if len(argv) > 4 and argv[4].isdigit() else None
    return rodar(titulo, artista, album, ano)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

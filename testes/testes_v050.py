"""Bateria de testes da versão 0.5.0 (9 casos).

Rode de qualquer lugar:

    python testes/testes_v050.py          (na pasta do RiffLab)
    TESTES.bat                            (Windows, duplo clique)

Não precisa de internet: os provedores de capa são substituídos por dados de
mentira. Os casos 1 a 8 rodam só com a biblioteca padrão; o caso 9 (tags do
MP3) precisa do mutagen e de um ffmpeg para gerar o áudio de teste.
"""
from __future__ import annotations

import sys
import tempfile
import traceback
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from app.models import AudioFormat, CoverResult, TrackResult           # noqa: E402
from app.pesquisa import filtros                                        # noqa: E402
from app.pesquisa import preview as previa                              # noqa: E402
from app.texto import artista_do_titulo                                 # noqa: E402

RESULTADOS: list = []


def caso(numero: int, nome: str):
    def decorador(funcao):
        RESULTADOS.append((numero, nome, funcao))
        return funcao
    return decorador


def _fmt(bitrate: int = 128, codec: str = "opus") -> AudioFormat:
    return AudioFormat(codec=codec, bitrate_kbps=bitrate, sample_rate=48000,
                       container="webm", url="https://exemplo/v", format_id="251")


def _track(titulo: str, canal: str = "", artista: str = "", **kw) -> TrackResult:
    return TrackResult(uid=f"t{abs(hash(titulo)) % 9999}", fonte="ytdlp", titulo=titulo,
                       artista=artista, canal=canal, duracao_s=kw.pop("duracao_s", 200),
                       extra=kw.pop("extra", {}), **kw)


# ---------------------------------------------------------------- caso 1
@caso(1, "Filtro de shows: estúdio fica, ao vivo vai para a lista de filtrados")
def caso_1() -> str:
    estudio = _track("Take Me Away (Official Video)", "ArtistaVEVO", "Artista",
                     extra={"live_status": "not_live"})
    show = _track("Take Me Away (Live at Wembley)", "ConcertsLive", "Artista",
                  extra={"live_status": "was_live"})
    visiveis, filtrados = filtros.aplicar([estudio, show], "take me away")
    assert [r.titulo for r in visiveis] == [estudio.titulo], visiveis
    assert [r.titulo for r in filtrados] == [show.titulo], filtrados
    assert show.ao_vivo_certeza == "confirmado", show.ao_vivo_certeza
    assert show.motivos_filtro, "o motivo do filtro precisa ser mostrado"
    assert not estudio.ao_vivo
    return "1 visível, 1 filtrado (com motivo e certeza confirmada)"


# ---------------------------------------------------------------- caso 2
@caso(2, "Filtro por palavra-chave não esconde letras que só citam 'live'")
def caso_2() -> str:
    provavel = _track("Banda - Show completo em São Paulo (Ao Vivo)", "CanalShow", "Banda")
    falso = _track("Oasis - Live Forever (Official Video)", "OasisVEVO", "Oasis",
                   extra={"live_status": "not_live"})
    visiveis, filtrados = filtros.aplicar([provavel, falso], "oasis")
    assert provavel in filtrados, "título com 'ao vivo' precisa ser filtrado"
    assert falso in visiveis, "letra 'Live Forever' não é show"
    return "'Ao Vivo' filtrado; 'Live Forever' preservado"


# ---------------------------------------------------------------- caso 3
@caso(3, "Prioridade: estúdio > canal oficial > ao vivo (nota de música)")
def caso_3() -> str:
    estudio = _track("Musica", "ArtistaVEVO", "Artista",
                     extra={"live_status": "not_live", "playable_in_embed": True})
    topico = _track("Musica", "Artista - Topic", "Artista", extra={"live_status": "not_live"})
    show = _track("Musica (Live)", "CanalShow", "Artista", duracao_s=5400,
                  extra={"live_status": "is_live"})
    filtros.aplicar([estudio, topico, show], "musica")
    assert estudio.nota_musica > show.nota_musica, (estudio.nota_musica, show.nota_musica)
    assert topico.nota_musica > show.nota_musica
    ordem = filtros.ordenar([show, estudio, topico], "relevancia")
    assert ordem[0] is estudio or ordem[0] is topico, ordem
    return f"notas: estúdio {estudio.nota_musica} / tópico {topico.nota_musica} / show {show.nota_musica}"


# ---------------------------------------------------------------- caso 4
@caso(4, "Pré-visualização: player oficial, sem baixar, com fallback explicado")
def caso_4() -> str:
    r = _track("Musica", "ArtistaVEVO", "Artista",
               extra={"id": "abc123", "playable_in_embed": True})
    r.pagina_url = "https://www.youtube.com/watch?v=abc123"
    pode, motivo = previa.pode_incorporar(r)
    assert pode, motivo
    url = previa.url_incorporada(r)
    assert "youtube-nocookie.com/embed/abc123" in url, url
    bloqueado = _track("Musica", "Canal", "Artista", extra={"id": "xyz", "playable_in_embed": False})
    pode2, motivo2 = previa.pode_incorporar(bloqueado)
    assert not pode2 and "incorporada" in motivo2, motivo2
    # a prévia só monta URL: não existe download de arquivo nesse caminho
    assert not hasattr(previa, "baixar"), "prévia não deve baixar arquivo"
    return "embed OK; bloqueado explicado; nenhum download envolvido"


# ---------------------------------------------------------------- caso 5
@caso(5, "Capa: música certa aceita, capa de outro artista recusada")
def caso_5() -> str:
    from app.metadata import correspondencia

    certo = correspondencia.pontuar(
        "Take Me Away", "Christina Vidal", "Freaky Friday", 2003,
        cand={"titulo": "Take Me Away", "artista": "Christina Vidal",
              "album": "Freaky Friday", "ano": 2003})
    errado = correspondencia.pontuar(
        "Take Me Away", "Christina Vidal", "Freaky Friday", 2003,
        cand={"titulo": "Take Me Away", "artista": "Insane Clown Posse",
              "album": "Bizaar", "ano": 2000})
    sem_dados = correspondencia.pontuar("Take Me Away", "", "", None,
                                        cand={"titulo": "Take Me Away"})
    assert certo.aprovado, certo.como_dict()
    assert not errado.aprovado, errado.como_dict()
    assert not sem_dados.aprovado, "sem artista e sem álbum não se inventa capa"
    return f"certo {certo.total} aprovado · errado {errado.total} recusado"


# ---------------------------------------------------------------- caso 6
@caso(6, "Imagem inválida ou pequena demais não vira capa")
def caso_6() -> str:
    from app.metadata import capa_validacao

    ruim = capa_validacao.validar(b"nao sou imagem" * 200)
    vazia = capa_validacao.validar(b"")
    assert not ruim.ok and not vazia.ok
    try:
        from PIL import Image
        import io
        buffer = io.BytesIO()
        # imagem "ruidosa" para passar do mínimo de bytes e falhar pelo tamanho
        import random
        random.seed(7)
        ruido = Image.new("RGB", (120, 120))
        pixels = ruido.load()
        for y in range(120):
            for x in range(120):
                pixels[x, y] = (random.randrange(256), random.randrange(256),
                                random.randrange(256))
        ruido.save(buffer, "PNG")
        pequena = capa_validacao.validar(buffer.getvalue(), minimo_lado=300)
        assert not pequena.ok, pequena.motivo
        assert "menor" in pequena.motivo or "pequeno" in pequena.motivo, pequena.motivo
        buffer2 = io.BytesIO()
        Image.new("RGB", (600, 600), (120, 20, 220)).save(buffer2, "PNG")
        boa = capa_validacao.validar(buffer2.getvalue(), minimo_lado=300)
        assert boa.ok, boa.motivo
        return "inválida/pequena recusadas; 600x600 aprovada"
    except ImportError:
        return "inválida recusada (Pillow ausente: teste de tamanho pulado)"


# ---------------------------------------------------------------- caso 7
@caso(7, "Cover Art Archive: só capa FRONTAL entra (contracapa/encarte não)")
def caso_7() -> str:
    from app.metadata import coverartarchive as caa

    assert caa._frontal_aceita({"frontal": True, "tipos": ["Front"]})
    assert caa._frontal_aceita({"frontal": True, "tipos": []})
    assert not caa._frontal_aceita({"frontal": False, "tipos": ["Back"]})
    assert not caa._frontal_aceita({"frontal": True, "tipos": ["Booklet", "Front"]})
    assert not caa._frontal_aceita({"frontal": True, "tipos": ["Medium"]})
    return "Front aceito; Back/Booklet/Medium recusados"


# ---------------------------------------------------------------- caso 8
@caso(8, "Canal não vira artista (e título de show não vira artista)")
def caso_8() -> str:
    assert artista_do_titulo("Christina Vidal - Take Me Away") == ("Christina Vidal",
                                                                   "Take Me Away")
    assert artista_do_titulo("Take Me Away (Live at Wembley) - Christina Vidal") == ("", "")
    assert artista_do_titulo("DisneyMusicVEVO - Take Me Away") == ("", "")
    r = _track("Christina Vidal - Take Me Away", "DisneyMusicVEVO", "DisneyMusicVEVO")
    from app.pesquisa import resultados
    resultados.enriquecer(r)
    assert r.artista == "Christina Vidal" and r.titulo == "Take Me Away", (r.artista, r.titulo)
    return "artista extraído do título quando o canal é de selo/VEVO"


# ---------------------------------------------------------------- caso 9
@caso(9, "MP3 recebe TIT2/TPE1/TPE2/TALB/TCOM/TEXT/TDRC/TRCK/TCON/TPUB/APIC")
def caso_9() -> str:
    try:
        from mutagen.id3 import ID3
    except ImportError:
        return "PULADO: mutagen não instalado"
    import shutil
    import subprocess

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return "PULADO: ffmpeg não encontrado"

    from app.models import TrackMeta
    from app import tagging

    with tempfile.TemporaryDirectory() as pasta:
        mp3 = Path(pasta) / "teste.mp3"
        subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-f", "lavfi",
                        "-i", "sine=frequency=440:duration=2", "-b:a", "128k",
                        str(mp3)], check=True)
        capa = Path(pasta) / "capa.jpg"
        try:
            from PIL import Image
            Image.new("RGB", (500, 500), (40, 10, 60)).save(capa, "JPEG")
        except ImportError:
            capa = None
        meta = TrackMeta(titulo="Take Me Away", artista="Christina Vidal",
                         artista_album="Christina Vidal", album="Freaky Friday",
                         ano=2003, faixa=7, total_faixas=16, genero="Soundtrack",
                         compositores=["Dennis Matkosky"], letristas=["Dennis Matkosky"],
                         gravadora="Hollywood Records",
                         capa=str(capa) if capa else "")
        res = tagging.gravar(mp3, meta)
        tags = ID3(str(mp3))
        obrigatorios = ["TIT2", "TPE1", "TPE2", "TALB", "TCOM", "TEXT", "TDRC",
                        "TRCK", "TCON", "TPUB"]
        faltando = [f for f in obrigatorios if f not in tags]
        assert not faltando, f"faltando: {faltando}"
        assert res["ok"]
        if capa:
            assert tags.getall("APIC"), "capa (APIC) não foi embutida"
        return ("10 frames + APIC gravados" if capa else "10 frames gravados (sem Pillow)")
    return "ok"


# ---------------------------------------------------------------- executor
def main() -> int:
    falhas = 0
    print("=" * 66)
    print(" RiffLab 0.5.0 — testes")
    print("=" * 66)
    for numero, nome, funcao in sorted(RESULTADOS):
        try:
            detalhe = funcao()
            print(f" [OK]   {numero}. {nome}")
            if detalhe:
                print(f"          → {detalhe}")
        except AssertionError as exc:
            falhas += 1
            print(f" [FALHA] {numero}. {nome}\n          → {exc}")
        except Exception:                                         # noqa: BLE001
            falhas += 1
            print(f" [ERRO]  {numero}. {nome}")
            traceback.print_exc()
    print("-" * 66)
    total = len(RESULTADOS)
    print(f" {total - falhas}/{total} casos OK" + ("" if not falhas else "  ← corrija antes de usar"))
    print("=" * 66)
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())

"""Gravação de metadados ID3 (incluindo a capa em APIC) com Mutagen."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from .models import TrackMeta
from .texto import normalizar

MIME_POR_EXT = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


def _mime(caminho: Path) -> str:
    return MIME_POR_EXT.get(caminho.suffix.lower(), "image/jpeg")


def gravar(caminho: str | Path, meta: TrackMeta, id3v1: bool = True,
           apagar_campos=None) -> dict:
    """Grava título/artista/álbum/ano/faixa/gênero + capa (capa frontal).

    Usa ID3v2.3 (máxima compatibilidade: Windows Explorer, carros, players
    antigos) e opcionalmente acrescenta ID3v1.
    """
    from mutagen.id3 import (APIC, ID3, TALB, TCOM, TCON, TDRC, TEXT, TIPL, TIT2,
                             TPE1, TPE2, TPOS, TPRO, TPUB, TRCK, TYER, TLEN,
                             ID3NoHeaderError)

    p = Path(caminho)
    if not p.is_file():
        raise FileNotFoundError(f"arquivo não encontrado: {p}")

    try:
        tags = ID3(str(p))
    except ID3NoHeaderError:
        tags = ID3()

    # Campos vazios preservam tags originais, exceto se o usuário pediu
    # explicitamente para limpar um campo no editor.
    frames = {'album': 'TALB', 'genero': 'TCON', 'ano': 'TDRC',
              'faixa': 'TRCK', 'artista_album': 'TPE2', 'duracao_s': 'TLEN'}
    for campo in apagar_campos or ():
        if campo in frames:
            tags.delall(frames[campo])
        if campo == 'ano':
            tags.delall('TYER')
    if meta.titulo:
        tags.add(TIT2(encoding=3, text=meta.titulo))
    if meta.artista:
        tags.add(TPE1(encoding=3, text=meta.artista))
    if meta.artista_album or (meta.artista and 'artista_album' not in (apagar_campos or ())):
        tags.add(TPE2(encoding=3, text=meta.artista_album or meta.artista))
    if meta.album:
        tags.add(TALB(encoding=3, text=meta.album))
    # TDRC aceita AAAA ou AAAA-MM-DD (ID3v2.4) — usamos o mais completo que houver
    data = meta.data_lancamento or (str(meta.ano) if meta.ano else "")
    if data:
        tags.add(TDRC(encoding=3, text=data))
    if meta.compositores:
        tags.add(TCOM(encoding=3, text=meta.compositores))       # compositores
    if meta.letristas:
        tags.add(TEXT(encoding=3, text=meta.letristas))          # autores da letra
    if meta.produtores:
        # TPRO é frame de ID3v2.4 e seria descartado na conversão para v2.3;
        # TIPL vira IPLS (v2.3 válido) e é o que os players antigos leem.
        tags.add(TIPL(encoding=3, text=[("producer", p) for p in meta.produtores]))
    if meta.gravadora:
        tags.add(TPUB(encoding=3, text=meta.gravadora))          # gravadora
    if meta.genero:
        tags.add(TCON(encoding=3, text=meta.genero))
    if meta.artistas_participantes and meta.artista:
        # TPE1 é o campo "Artistas participantes" do Explorer. Preservar a
        # grafia e todas as participações, sem repetir nomes já creditados.
        import re
        atual = meta.artista
        existentes = normalizar(atual)
        nomes = []
        for nome in meta.artistas_participantes:
            nome = str(nome).strip()
            chave = normalizar(nome)
            if chave and not re.search(r'(?<!\w)' + re.escape(chave) + r'(?!\w)', existentes):
                nomes.append(nome)
                existentes += ' ' + chave
        if nomes:
            tags.add(TPE1(encoding=3, text=atual + ' feat. ' + ', '.join(nomes)))
    if meta.duracao_s is not None and 0 < meta.duracao_s < 7 * 24 * 3600:
        tags.add(TLEN(encoding=3, text=str(round(meta.duracao_s * 1000))))
    if meta.faixa:
        texto = f"{meta.faixa}/{meta.total_faixas}" if meta.total_faixas else str(meta.faixa)
        tags.add(TRCK(encoding=3, text=texto))
    if meta.disco:
        tags.add(TPOS(encoding=3, text=str(meta.disco)))

    capa_gravada = False
    bytes_capa = 0
    motivo_capa = ""
    if meta.capa and Path(meta.capa).is_file():
        from .image_utils import eh_imagem
        dados = Path(meta.capa).read_bytes()
        # imagem inválida/corrompida NÃO entra no MP3 (proposta §6): o arquivo
        # sairia com um APIC quebrado e o player mostraria um quadrado vazio
        if eh_imagem(dados) and len(dados) >= 1024:
            tags.delall("APIC")
            tags.add(APIC(encoding=3, mime=_mime(Path(meta.capa)), type=3,
                          desc="Cover", data=dados))
            capa_gravada = True
            bytes_capa = len(dados)
        else:
            motivo_capa = "imagem inválida: capa não foi embutida"

    # remove frames que o Windows pode achar inválidos e grava v2.3
    tags.update_to_v23()
    # ...e recoloca os frames que a conversão descarta, antes de salvar:
    if meta.produtores:
        tags.add(TPRO(encoding=3, text=meta.produtores))       # leitura em players v2.4
    if meta.ano:
        tags.add(TYER(encoding=3, text=str(meta.ano)))         # Explorer / carros antigos
    tags.save(str(p), v2_version=3, v1=2 if id3v1 else 0)

    resultado = {"ok": True, "capa": capa_gravada, "capa_bytes": bytes_capa,
                 "id3v1": id3v1}
    if motivo_capa:
        resultado["aviso_capa"] = motivo_capa
    return resultado


def ler(caminho: str | Path) -> dict:
    """Lê as tags do arquivo (dict simples, tolerante a falhas)."""
    from mutagen.id3 import ID3, ID3NoHeaderError
    try:
        tags = ID3(str(caminho))
    except (ID3NoHeaderError, Exception):
        return {}
    def _txt(chave: str) -> str:
        frame = tags.get(chave)
        if not frame:
            return ""
        try:
            return str(frame.text[0])
        except Exception:
            return str(frame)
    apics = tags.getall("APIC")
    return {
        "titulo": _txt("TIT2"), "artista": _txt("TPE1"), "album": _txt("TALB"),
        "ano": _txt("TDRC") or _txt("TYER"), "faixa": _txt("TRCK"),
        "genero": _txt("TCON"), "disco": _txt("TPOS"),
        "compositor": _txt("TCOM"), "letrista": _txt("TEXT"),
        "gravadora": _txt("TPUB"), "produtor": _txt("TPRO") or _txt("IPLS"),
        "artista_album": _txt("TPE2"), "duracao_ms": _txt("TLEN"),
        "tem_capa": bool(apics), "capa_bytes": len(apics[0].data) if apics else 0,
    }


def capa_embutida(caminho: str | Path) -> Optional[bytes]:
    from mutagen.id3 import ID3, ID3NoHeaderError
    try:
        apics = ID3(str(caminho)).getall("APIC")
        return apics[0].data if apics else None
    except (ID3NoHeaderError, Exception):
        return None


def remover_capa(caminho: str | Path) -> None:
    """Remove imagens ID3 do novo arquivo; erros de leitura/gravação não são omitidos."""
    from mutagen.id3 import ID3, ID3NoHeaderError
    try:
        tags = ID3(str(caminho))
    except ID3NoHeaderError:
        return
    if tags.getall('APIC'):
        tags.delall('APIC')
        tags.save(str(caminho), v2_version=3)


def garantir_sem_capa(caminho: str | Path) -> None:
    """Confirma no arquivo gerado que não restou nenhuma imagem APIC."""
    from mutagen.id3 import ID3, ID3NoHeaderError
    try:
        tags = ID3(str(caminho))
    except ID3NoHeaderError:
        return
    if tags.getall('APIC'):
        raise RuntimeError('Ainda há uma imagem embutida no MP3 que deveria estar sem capa.')

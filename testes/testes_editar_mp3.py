"""Edição de arquivos existentes sem recodificar nem perder tags ou imagens."""
import hashlib
import os
import struct
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest.mock import patch

from mutagen.id3 import APIC, ID3, TALB, TCON, TDRC, TIT2, TPE1, TRCK, TXXX
from app import editar_mp3


def imagem_png():
    def chunk(tipo, dados):
        return struct.pack('>I', len(dados)) + tipo + dados + struct.pack('>I', zlib.crc32(tipo + dados) & 0xffffffff)
    linhas = []
    for y in range(300):
        linha = bytearray([0])
        for x in range(300): linha.extend((x % 256, y % 256, (x * y) % 256))
        linhas.append(bytes(linha))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 300, 300, 8, 2, 0, 0, 0)) +
            chunk(b'IDAT', zlib.compress(b''.join(linhas))) + chunk(b'IEND', b''))


def criar_mp3(p: Path, ver=3):
    audio = b'\xff\xfb\x90\x64' + bytes(range(256)) * 100
    p.write_bytes(audio)
    tags = ID3()
    tags.add(TIT2(encoding=3, text='Welcome to the Jungle'))
    tags.add(TPE1(encoding=3, text="Guns N' Roses"))
    tags.add(TALB(encoding=3, text='Álbum errado'))
    tags.add(TDRC(encoding=3, text='1987-07-21'))
    tags.add(TRCK(encoding=3, text='1/12'))
    tags.add(TXXX(encoding=3, desc='origem especial', text='preservar'))
    tags.add(APIC(encoding=3, mime='image/jpeg', type=3, desc='frente', data=b'capa antiga'))
    tags.add(APIC(encoding=3, mime='image/jpeg', type=4, desc='verso', data=b'contracapa'))
    tags.save(p, v2_version=ver, v1=0)
    return audio


def audio_bytes(p):
    dados = p.read_bytes()
    offset = ID3(p).size
    return dados[offset:]


class EditarMP3(unittest.TestCase):
    def test_edita_apenas_campos_solicitados_preserva_audio_outras_tags_e_backup(self):
        for versao in (3, 4):
            with self.subTest(versao=versao), tempfile.TemporaryDirectory() as d:
                p = Path(d) / 'musica.mp3'; audio = criar_mp3(p, versao)
                original = p.read_bytes()
                snap = editar_mp3.abrir(p)
                self.assertEqual(snap['campos']['ano'], '1987-07-21')
                self.assertEqual(snap['campos']['faixa'], '1/12')
                resultado = editar_mp3.salvar(snap, {'album': 'Appetite for Destruction', 'genero': 'Hard Rock'})
                self.assertEqual(Path(resultado['backup']).read_bytes(), original)
                self.assertEqual(audio_bytes(p), audio)
                tags = ID3(p)
                self.assertEqual(str(tags['TALB']), 'Appetite for Destruction')
                self.assertEqual(str(tags['TCON']), 'Hard Rock')
                self.assertEqual(str(tags['TDRC']), '1987-07-21')
                self.assertEqual(str(tags['TRCK']), '1/12')
                self.assertEqual(str(tags['TXXX:origem especial']), 'preservar')
                self.assertEqual({(int(x.type), bytes(x.data)) for x in tags.getall('APIC')},
                                 {(3, b'capa antiga'), (4, b'contracapa')})
                self.assertEqual(tags.version[1], versao)

    def test_troca_e_remocao_somente_frontal_conservam_outros_apics(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'musica.mp3'; audio = criar_mp3(p)
            nova = imagem_png()
            primeiro = editar_mp3.salvar(editar_mp3.abrir(p), {}, 'trocar', nova)
            tags = ID3(p)
            self.assertIn((3, nova), [(int(x.type), bytes(x.data)) for x in tags.getall('APIC')])
            self.assertIn((4, b'contracapa'), [(int(x.type), bytes(x.data)) for x in tags.getall('APIC')])
            antes_segundo = p.read_bytes()
            segundo = editar_mp3.salvar(editar_mp3.abrir(p), {}, 'remover')
            self.assertNotEqual(primeiro['backup'], segundo['backup'])
            self.assertEqual(Path(segundo['backup']).read_bytes(), antes_segundo)
            self.assertEqual([(int(x.type), bytes(x.data)) for x in ID3(p).getall('APIC')], [(4, b'contracapa')])
            self.assertEqual(audio_bytes(p), audio)

    def test_cancelamento_sem_mudanca_invalido_e_arquivo_alterado_externamente(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'musica.mp3'; criar_mp3(p); original = p.read_bytes()
            snap = editar_mp3.abrir(p)
            self.assertFalse(editar_mp3.salvar(snap, {})['alterado'])
            self.assertEqual(list(Path(d).glob('*.rifflab-backup*')), [])
            with self.assertRaises(ValueError): editar_mp3.salvar(snap, {'faixa':'0/a'})
            with self.assertRaises(ValueError): editar_mp3.salvar(snap, {}, 'trocar', b'imagem quebrada')
            self.assertEqual(p.read_bytes(), original)
            p.write_bytes(original + b'modificado')
            with self.assertRaisesRegex(RuntimeError, 'mudou'): editar_mp3.salvar(snap, {'genero': 'Rock'})
            self.assertEqual(p.read_bytes(), original + b'modificado')

    def test_falhas_escrita_e_backup_nunca_substituem_original(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'musica.mp3'; criar_mp3(p); original = p.read_bytes()
            for alvo in ('app.editar_mp3._criar_backup', 'mutagen.id3.ID3.save', 'app.editar_mp3.os.replace'):
                snap = editar_mp3.abrir(p)
                with patch(alvo, side_effect=PermissionError('sem permissão')):
                    with self.assertRaises(PermissionError): editar_mp3.salvar(snap, {'genero':'Rock'})
                self.assertEqual(p.read_bytes(), original)
                self.assertFalse(list(Path(d).glob('.rifflab-edicao-*.tmp')))

    def test_apagar_campos_e_arquivo_sem_tags(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'musica.mp3'; audio = criar_mp3(p)
            editar_mp3.salvar(editar_mp3.abrir(p), {'album':'', 'ano':'', 'faixa':''})
            tags = ID3(p)
            for nome in ('TALB', 'TDRC', 'TRCK'): self.assertNotIn(nome, tags)
            self.assertEqual(audio_bytes(p), audio)
            outra = Path(d) / 'sem.mp3'; outra.write_bytes(audio)
            snap = editar_mp3.abrir(outra)
            self.assertEqual(snap['campos']['titulo'], '')
            editar_mp3.salvar(snap, {'titulo':'Uma música'})
            self.assertEqual(str(ID3(outra)['TIT2']), 'Uma música')
            self.assertEqual(audio_bytes(outra), audio)

    @unittest.skipIf(os.name == 'nt', 'criação de links pode exigir privilégios no Windows')
    def test_link_simbolico_e_fisico_sao_rejeitados(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'musica.mp3'; criar_mp3(p)
            s = Path(d) / 'simbolo.mp3'; s.symlink_to(p)
            with self.assertRaises(ValueError): editar_mp3.abrir(s)
            s.unlink(); os.link(p, s)
            with self.assertRaises(ValueError): editar_mp3.abrir(p)

    def test_mp3_com_id3v1_pode_ser_editado_com_backup_e_sem_reprocessar_audio(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'id3v1.mp3'
            audio = b'\xff\xfb\x90\x64' + b'audio' * 100
            rodape = (b'TAG' + b'Musica'.ljust(30, b'\0') + b'Artista'.ljust(30, b'\0') +
                      b'Disco'.ljust(30, b'\0') + b'1987' + b'comentario'.ljust(30, b'\0') + bytes([17]))
            p.write_bytes(audio + rodape)
            original = p.read_bytes()
            snap = editar_mp3.abrir(p)
            self.assertEqual(snap['campos']['titulo'], 'Musica')
            salvo = editar_mp3.salvar(snap, {'album': 'Outro disco'})
            self.assertEqual(Path(salvo['backup']).read_bytes(), original)
            self.assertEqual(str(ID3(p)['TALB']), 'Outro disco')
            self.assertEqual(audio_bytes(p)[:-128], audio)

    def test_audio_mp3_real_mantido_sem_recodificar(self):
        import shutil, subprocess, wave
        from mutagen.mp3 import MP3
        ffmpeg = shutil.which('ffmpeg')
        if not ffmpeg:
            self.skipTest('ffmpeg não instalado')
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'real.mp3'
            wav = Path(d) / 'origem.wav'
            with wave.open(str(wav), 'wb') as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000)
                w.writeframes(b'\0\0' * 8000)
            subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', '-i', str(wav), str(p)], check=True)
            antes = audio_bytes(p)
            duracao = MP3(p).info.length
            editar_mp3.salvar(editar_mp3.abrir(p), {'titulo':'Música', 'genero':'Rock'})
            self.assertEqual(audio_bytes(p), antes)
            self.assertEqual(MP3(p).info.length, duracao)

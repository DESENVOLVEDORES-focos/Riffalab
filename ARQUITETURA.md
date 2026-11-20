# RiffLab — Arquitetura

> Aplicativo desktop local (Windows) para **pesquisar músicas, comparar a qualidade
> das fontes, escolher manualmente e obter um MP3 finalizado com capa e metadados
> embutidos**. Python + PySide6 + FFmpeg + Mutagen + SQLite.

Versão do documento: 0.1.0 · pasta do projeto: `RiffLab\`

---

## 1. Análise da proposta (o que estava bom e o que precisava mudar)

O projeto anterior (`servidor músicas`) já tinha o essencial: um script Python,
`ffmpeg.exe` e `yt-dlp.exe` na pasta `ferramentas`, e arquivos de log
(`baixar.txt`, `erros.txt`, `falhas.txt`, `historico.txt`). Os problemas típicos
desse formato:

| Problema no formato antigo | Como o RiffLab resolve |
|---|---|
| Um único `musica.py` com tudo misturado | 25+ módulos independentes, um por responsabilidade |
| `historico.txt`/`erros.txt` como “banco” | SQLite (histórico, downloads e biblioteca indexada) |
| Interface travava durante download | Tudo em `QThreadPool`; a UI nunca bloqueia |
| Não dava para comparar fontes | Cada resultado mostra codec, bitrate, taxa, canal e uma **nota de qualidade** |
| Capa baixada “no olho” | Cascata iTunes → Cover Art Archive → miniatura, com pontuação de similaridade |
| Metadados incompletos | Título, artista, álbum, ano, faixa, disco, gênero e capa (ID3/APIC) automáticos |
| Sobrescrevia arquivos | Deduplicação por tamanho + sufixo `(2)`; nada é apagado |
| `cookies.txt` no meio do código | Módulo dedicado, somente leitura estrutural, sem log de conteúdo |
| Só YouTube | Fontes plugáveis, com o yt-dlp como fonte **padrão** |

**Uma decisão importante (revisada):** a fonte de pesquisa padrão é o
**yt-dlp** — ele encontra a música em plataformas de vídeo e devolve a melhor
qualidade de áudio disponível, que é o que o usuário pediu. As outras fontes
(**Internet Archive**, **Biblioteca local**) continuam existindo como
*plug-ins*, desmarcadas por padrão, e podem ser ligadas em Configurações.

O yt-dlp é uma ferramenta de terceiros: o RiffLab **não** a redistribui. O
usuário baixa o `yt-dlp.exe` oficial e coloca em `ferramentas\`. O app mostra o
aviso legal uma vez (guardado em `config.json → ytdlp_consentido`) e lembra, em
cada resultado, que a licença do material precisa ser conferida na origem.

---

## 2. Estrutura de pastas

```
RiffLab\
├── main.py                     # bootstrap: checa deps, cria pastas, abre a janela
├── INICIAR.bat                 # atalho p/ Windows (cria venv, instala, executa)
├── DIAGNOSTICO.bat             # mostra Python, venv, pacotes, ferramentas e log
├── TESTAR_YTDLP.bat            # testa o yt-dlp fora do app (grava teste_ytdlp.txt)
├── TESTAR_CAPA.bat             # mostra POR QUE uma capa foi escolhida (artista + título)
├── requirements.txt
├── LEIA-ME.md                  # instalação e uso
├── ANALISE-DA-PROPOSTA.md      # decisões, problemas técnicos e estrutura (leia primeiro)
├── ARQUITETURA.md              # este documento
├── cookies.txt.exemplo         # modelo (valores fictícios)
├── api.txt.exemplo             # modelo da chave da Groq (copie para api.txt)
├── config.json                 # criado no 1º start (preferências)
├── rifflab.db                  # criado no 1º start (SQLite)
├── rifflab.log                 # log rotativo (sem dados sensíveis)
├── docs\                       # capturas de tela
├── ferramentas\                # ffmpeg.exe, ffprobe.exe (opcional), yt-dlp.exe
├── downloads\                  # saída padrão dos MP3 organizados
├── capas\                      # cache de capas (cache\ = imagens baixadas)
├── api.txt                     # (opcional) chave da Groq em 1 linha — lida automaticamente
├── credenciais\                # chave da Groq (groq.dat) — nunca vai para o Git/ZIP
├── temp\                       # arquivos intermediários (limpos automaticamente)
└── app\
    ├── config.py               # caminhos, padrões, Config (JSON) .................... [núcleo]
    ├── logging_setup.py        # log rotativo + filtro de dados sensíveis
    ├── models.py               # TrackResult, AudioFormat, TrackMeta, ArquivoInfo
    ├── quality.py              # nota 0-1000, rótulos, comparação de codecs
    ├── tools.py                # localiza ffmpeg/ffprobe/yt-dlp e valida versão
    ├── audio_probe.py          # ffprobe → ffmpeg -i → mutagen (análise de arquivo)
    ├── convert.py              # plano de conversão + FFmpeg com progresso
    ├── tagging.py              # ID3v2.3 + APIC (capa) + ID3v1 opcional
    ├── organizer.py            # nomes válidos, template de pastas, anti-duplicata
    ├── cookies.py              # status do cookies.txt (sem expor conteúdo)
    ├── diagnostico_capa.py     # CLI: candidatos de capa e a decisão final, com notas
    ├── seguranca.py            # cofre da chave da Groq (DPAPI no Windows, 0600 no Linux)
    ├── db.py                   # SQLite (histórico, downloads, biblioteca)
    ├── texto.py                # normalização, similaridade, limpeza de títulos
    ├── image_utils.py          # dimensões de imagem sem dependências
    ├── workers.py              # QRunnable + Executor (pool) — nada bloqueia a UI
    ├── search_service.py       # pesquisa paralela + enriquecimento + filtro + ordenação
    ├── pipeline.py             # download → análise → capa → MP3 → tags → organização
    ├── downloader.py           # fila de jobs (QObject + sinais + persistência)
    ├── pesquisa\               # PESQUISA VISUAL (0.5.0) — sem Qt
    │   ├── filtros.py          # ao vivo? pontuação, prioridade estúdio, listas visíveis/filtrados
    │   ├── preview.py          # URL do player oficial, permissão de incorporação
    │   └── resultados.py       # normalização (canal ≠ artista, título limpo)
    ├── sources\                # FONTES DE PESQUISA/ÁUDIO
    │   ├── base.py             # contrato FonteBase (disponivel/buscar/baixar/detalhar)
    │   ├── archive_org.py      # Internet Archive (domínio público/CC)
    │   ├── local_library.py    # seus arquivos locais
    │   ├── ytdlp.py            # opcional (desligado por padrão)
    │   └── __init__.py         # registro de fontes
    ├── metadata\               # METADADOS E CAPAS
    │   ├── itunes.py           # iTunes/Apple Music (busca + arte 1200x1200)
    │   ├── musicbrainz.py      # MusicBrainz (gravação, release, release-group)
    │   ├── coverartarchive.py  # CAA: SÓ capa frontal (types/front)
    │   ├── provedores.py       # provedores independentes + prioridade + rate limit
    │   ├── correspondencia.py  # portões + pontuação título/artista/álbum/ano/ID
    │   ├── capa_validacao.py   # imagem válida? tamanho/proporção/hash
    │   ├── busca_capas.py      # orquestra provedores → candidatos validados e ordenados
    │   └── covers.py           # API pública: encontrar_capa / candidatos_capa / metadados
    └── ui\
        ├── theme.py            # paleta neon graffiti + QSS + utilidades
        ├── main_window.py      # barra lateral, páginas, toasts, status
        ├── dialogos.py         # confirmação antes de processar (etapa 5) e da capa (etapa 9)
        ├── ponte.py            # ponte thread→UI p/ confirmar capa durante o download
        ├── widgets\
        │   ├── images.py       # carregador assíncrono de miniaturas
        │   ├── result_card.py  # cartão de resultado com selos, ao vivo e prévia
        │   ├── preview_widget.py # overlay com o player oficial (QWebEngineView)
        │   └── toast.py        # aviso flutuante
        └── pages\
            ├── search_page.py     # pesquisa, filtros, resultados, seleção
            ├── downloads_page.py  # fila em tempo real
            ├── library_page.py    # indexação/consulta da biblioteca
            ├── history_page.py    # histórico de pesquisas e processamentos
            └── settings_page.py   # cookies, ferramentas, saída, capas, fontes
```

**Regra de dependência:** `ui → downloader/pipeline → sources/metadata → núcleo`.
O núcleo (`config`, `models`, `quality`, `audio_probe`, `convert`, `tagging`,
`organizer`, `db`, `cookies`) **não importa Qt** — por isso é testável pela
linha de comando, e foi (ver §14).

---

## 3. Fluxo de dados

### 3.1 Pesquisa

```
[UI]  texto + fontes marcadas + ordenação
  └─▶ search_service.pesquisar()               (thread do pool)
        ├─ ThreadPoolExecutor → cada FonteBase.buscar(consulta, limite)
        │     ├─ ytdlp (PADRÃO): yt-dlp "ytsearchN:<termo>" --flat-playlist
        │     │                  --dump-single-json → entries → TrackResult[]
        │     │                  (artista = canal, ou "Artista - Título" quando
        │     │                   o lado esquerdo bate com o canal)
        │     ├─ archive_org: advancedsearch → /metadata de cada item
        │     │                → agrupa arquivos por faixa → AudioFormat[]
        │     └─ local_library: varre pastas → audio_probe.analisar()
        ├─ remove duplicados da MESMA fonte (título+artista+duração; o mesmo
        │  som em fontes diferentes é mantido, para comparação)
        ├─ ordena por relevância (texto.relevancia) ou por qualidade
        └─▶ emit resultado(dict)                  [volta para a thread da UI]
[UI]  monta um ResultCard por resultado (miniatura carregada à parte)
       └─▶ verificação automática de qualidade:
             até 10 cartões, 3 por vez, chamam fonte.detalhar(resultado)
             → yt-dlp -J <url> → formats de áudio reais
             → o cartão troca "qualidade a verificar" por
               codec/bitrate/taxa/selos e habilita o botão Processar
             (memoizado em _CACHE_DETALHES: a mesma faixa não é consultada 2×)

       REGRAS DE OURO (para nunca "detectar eternamente"):
         • o cartão já nasce com a opção "melhor áudio disponível" e o botão
           Processar HABILITADO — a detecção é um luxo, não um pré-requisito;
         • detalhar() nunca levanta: falha → extra["erro_detalhe"] + aviso
           "qualidade não detectada" (selo vermelho, tooltip e rodapé);
         • 1 tentativa e 45 s por vídeo (antes: 3 tentativas × 20 s em cada um);
         • o stderr do yt-dlp é traduzido: "Sign in to confirm you're not a bot"
           vira "o YouTube pediu verificação de robô — use um cookies.txt…";
         • botão "tentar de novo" no cartão repete só aquela consulta.
```

**Miniatura x capa final.** O cartão mostra `resultado.thumb_url`, que vem da
plataforma (`i.ytimg.com/...` nos resultados do yt-dlp). A cascata de capas
(iTunes → Cover Art Archive → miniatura) só roda no `pipeline`, depois do
download, e o resultado vai para o APIC do MP3 — nunca para a lista de
resultados. Ou seja: a imagem da pesquisa é sempre a do vídeo.

### 3.2 Processamento (fila, um job por vez)

```
[UI] botão Processar → GerenciadorFila.adicionar(resultado, formato)
       └─ grava job no SQLite (status "na fila")  → sinal job_adicionado
       └─ _proximo(): pega o 1º da fila e roda pipeline.processar_resultado()

pipeline.processar_resultado():                ◀── callbacks de progresso (0-100)
  1. fonte.baixar()                  → temp/<ts>_<hash>/origem.<ext>
       └─ yt-dlp: tenta a faixa SÓ DE ÁUDIO escolhida (formato "251", "140"...).
          Se ela não existir/falhar, repete com "bestaudio/best", que aceita o
          arquivo muxado — o ffmpeg extrai o áudio dele. O vídeo nunca é baixado
          no caminho normal (ver ANALISE-DA-PROPOSTA.md §3.1).
  2. audio_probe.analisar()          → codec/bitrate/taxa/duração REAIS do arquivo
  2.5 ia.identificador.identificar() → (só com ia_ativa) título/artista/álbum/etc.
       └─ confere o álbum no MusicBrainz antes de aceitar; falhou? segue sem IA
  3. metadata.covers.metadados_completos()  → título/artista/álbum/ano/faixa/gênero
     metadata.covers.encontrar_capa()       → JPG do ÁLBUM (cache em capas/cache)
  4. convert.converter_para_mp3()    → -c:a copy quando já é MP3 (sem reencode)
  5. tagging.gravar()                → ID3v2.3 + APIC (capa frontal) [+ ID3v1]
  6. organizer.caminho_destino/resolver_conflito/mover()
  7. limpeza do temp               (sempre, inclusive em erro)
```

Cada etapa emite `(porcentagem, mensagem)`; o `GerenciadorFila` traduz para um
status (`baixando`, `identificando`, `metadados`, `convertendo`, `finalizando`) e atualiza o
SQLite. A página de Downloads só reflete os sinais — nenhuma chamada bloqueante
na thread da interface.

---

## 3.3 Pesquisa visual, filtro de ao vivo e prévia (v0.5.0)

Três módulos novos, todos **sem Qt** (testáveis pela linha de comando):

**`pesquisa/filtros.py`** — decide o que é gravação ao vivo:

| Sinal | Peso | Observação |
|---|---|---|
| `is_live` / `live_status` (yt-dlp) | 0,8–1,0 | prova; `was_live`, `post_live`, `is_upcoming` também contam |
| título/descrição: `live at`, `ao vivo`, `concert`, `festival`, `unplugged`, `bootleg`, `session`, `tour`, `show`… | 0,18–0,55 | só indício → aviso, não veredito |
| canal `- Topic` / VEVO / “official” / canal do próprio artista | +0,12…+0,22 | bônus de prioridade |
| duração > 25 min | −0,20 | quase sempre show/compilação |
| título entre 1,5 e 10 min | +0,12 | plausível para música |

`aplicar()` devolve **duas listas** (visíveis, filtrados) — nunca descarta nada.
A nota final ordena: estúdio > clipe oficial > oficial com áudio de estúdio >
canal oficial > ao vivo.

**`pesquisa/preview.py`** — monta `https://www.youtube-nocookie.com/embed/<id>`
e responde “pode / não pode” (por `playable_in_embed`, `availability`,
`age_limit`). Não existe caminho de download nesse módulo: a prévia **não baixa
arquivo**. O desenho do player fica em `ui/widgets/preview_widget.py`
(`QWebEngineView`, Tocar/Pausar por `postMessage` da API oficial do iframe);
sem QtWebEngine, a camada explica e oferece a página original.

**`pesquisa/resultados.py`** — separa canal de artista usando
`texto.artista_do_titulo()`: só aceita o lado esquerdo de “Artista - Título”
quando ele parece nome de artista (≤ 40 caracteres, ≤ 5 palavras, sem palavras
de “ao vivo”, não parecendo canal). É o que impede `DisneyMusicVEVO` de virar
artista — origem de tags e capas erradas.

**Fluxo em 10 etapas:** pesquisa → análise (`sources/ytdlp.enriquecer`, em
paralelo, com cache) → prévia → seleção manual → confirmação (`ui/dialogos`)
→ processamento (`pipeline`) → IA (`ia/identificador`) → capa
(`metadata/busca_capas`) → confirmação da capa (diálogo + `ui/ponte`, que
atravessa a thread do download) → finalização (tags + organização + limpeza).

---

## 4. Comparação de qualidade (`quality.py`)

Nota de 0 a 1000, para comparar **fontes diferentes** lado a lado:

```
lossless (FLAC/ALAC/WAV/AIFF/PCM)          → 1000
com perda:  min(1000, (bitrate × fator_codec) / 320 × 1000) × peso_codec
  fator_codec: opus 1.80 · aac/m4a 1.30 · vorbis 1.15 · mp3 1.00 · wma 0.85
  peso_codec : flac 1.00 · opus 0.98 · aac 0.90 · mp3 0.88 · wma 0.80
ajustes: +30 (≥96 kHz) · +15 (≥48 kHz) · −120 (≤22 kHz) · −80 (mono) · −25 (estimado)
rótulos:  Lossless · Excelente (≥850) · Boa (≥650) · Média (≥400) · Baixa
```

O fator por codec existe porque 96 kbps de Opus **não** equivale a 96 kbps de
MP3 — comparar bitrate “cru” entre codecs engana. Os selos coloridos do cartão
usam exatamente essa nota (`quality.cor_rotulo`).

---

## 5. Conversão para MP3 (`convert.py`)

Três modos, escolhidos em **Configurações → Áudio e destino** (proposta §5):

| Modo visível | Comportamento |
|---|---|
| **Automática** (padrão) | decide pela origem: copia se já é MP3; usa o bitrate equivalente em MP3 quando vem de Opus/AAC; 320 kbps para lossless |
| **Alta** | força MP3 CBR 320 kbps (copia se a origem já for 320) |
| **Personalizada** | MP3 CBR no bitrate escolhido (128–320, passo 32) |

| Origem | Ação | Argumentos |
|---|---|---|
| MP3 ≤ 320 kbps | **copiar** (zero perda) | `-c:a copy` |
| FLAC / ALAC / WAV / PCM | recodificar | `-c:a libmp3lame -b:a 320k` |
| AAC/Opus/OGG | recodificar no bitrate equivalente (128–320) | `-c:a libmp3lame -b:a Nk` |
| modo Alta | CBR 320 | `-c:a libmp3lame -b:a 320k` |
| modo Personalizada | CBR escolhido | `-c:a libmp3lame -b:a Nk` |

Sempre com `-map 0:a:0 -vn`, `-ar <taxa original>` (nunca faz upsample) e
`-map_metadata 0`. O progresso vem de `-progress pipe:1` (`out_time_ms`).
A decisão aparece no histórico (“copiar” ou “recodificar”) para o usuário saber
se houve perda.

---

## 6. Capas e metadados (`metadata/`)

**Regra de ouro:** a capa é sempre a do **álbum confirmado**, não a do vídeo.
A miniatura do YouTube é thumbnail de vídeo — não é capa oficial e só entra se
o usuário marcar *“usar a miniatura do vídeo como último recurso”*.

**Cascata de capas** (`covers.encontrar_capa`), nesta ordem:

1. **Capas do álbum confirmado** (quando a IA identificou e o MusicBrainz
   confirmou o *release group*): Cover Art Archive do grupo e dos *releases*
   dele, marcadas `confirmada=True` e ordenadas **primeiro** — mesmo que outra
   fonte tenha score maior, a capa do álbum certo vence.
2. **Cover Art Archive** via MusicBrainz para o álbum pesquisado — só aceita se
   o nome do álbum bater (evita capa de “ao vivo”/coletânea).
3. **iTunes/Apple Music** — arte até `1200x1200`; **exige álbum compatível**
   (antes ele devolvia a capa da “Deluxe Edition” ou de outro álbum).
4. **Miniatura do item** — apenas com `usar_thumb_como_capa` ligado, e o
   relatório diz que foi miniatura, não capa oficial.

**Validação (o que impede a capa de outra música).** Existem dezenas de
"Take Me Away"; até a 0.4.0 a busca só mandava o título para o MusicBrainz, e a
primeira capa frontal servia — resultado: a capa de um álbum de techno no lugar
da Christina Vidal. Agora:

| Regra | Onde |
|---|---|
| título tem que bater (similaridade ≥ 0.85) | `itunes.melhor_faixa`, `musicbrainz.buscar_gravacao` |
| artista conhecido tem que bater (≥ 0.55) | idem |
| álbum conhecido tem que bater (≥ 0.60) | idem |
| confiança da MusicBrainz ≥ 0.70 para usar a capa | `musicbrainz.melhor_capa` |
| **sem artista e sem álbum → nenhuma capa** (com o motivo no relatório) | `covers.encontrar_capa` |
| álbum errado no vídeo → repete sem o álbum, aceitando só confiança ≥ 0.90 | `covers.encontrar_capa` |
| canal não é artista ("Disney", "FulanoVEVO", "… - Topic") → tenta o "Artista - Título" do vídeo | `texto.parece_canal` + `pipeline.buscar_capa` |
| ano só soma ponto quando **bate** (antes somava só por existir) | `itunes.melhor_faixa` |

Cada candidata recebe score = similaridade(título)×0.6 + artista×0.3 +
álbum×0.1 (mais 0.05 se o ano bater) e a ordenação final é
`sort(key=(confirmada, score))`. O `CoverResult` agora carrega **artista** e
**álbum** da capa escolhida, e a fila mostra
`capa: coverartarchive · A Night at the Opera · Queen` — dá para ver na hora se
a capa é a da música certa.
Se nada oficial aparecer, o app **não inventa**: grava sem capa e escreve
“nenhuma capa oficial encontrada (thumbnail do vídeo não é usada como capa)”.

Rejeita arquivos que não são imagem, mede as dimensões sem Pillow
(`image_utils`) e exige lado mínimo configurável (padrão 300 px). Cache em
`capas/cache/<hash>.<ext>` — a mesma capa nunca é baixada duas vezes.

**Metadados** (`metadados_completos`): com IA ligada e identificação
confirmada, a IA manda (título, artista, participantes, banda, compositores,
letristas, produtores, álbum, ano, data, gênero, faixa, gravadora) e
`fonte_identificacao` = `"groq + musicbrainz"`. Sem IA, funciona como antes:
iTunes primeiro, MusicBrainz completando (inclusive faixa `A1` → 1).

**Gravação** (`tagging.py`): ID3v2.3 (compatibilidade máxima: Explorer,
Windows Media Player, som automotivo) com
`TIT2 / TPE1 / TPE2 / TALB / TCOM / TEXT / TPRO / TCON / TDRC / TYER / TRCK /
TPOS / TPUB` + `TIPL` (produtor) + `APIC` tipo 3 (capa frontal).
Detalhe de compatibilidade: `TPRO` (produtor) é frame de ID3v2.4 e
`tags.update_to_v23()` **descarta** — por isso o app grava `TIPL` antes de
converter para 2.3 e recria `TPRO` depois; `TYER` (só 4 dígitos) acompanha
`TDRC` (data completa `AAAA-MM-DD`). ID3v1 opcional. Capa antiga é removida
antes de gravar a nova (nunca fica duplicada).

---

### 6.4 Provedores independentes e pontuação de correspondência (v0.5.0)

`metadata/provedores.py` — cada fonte é uma função independente que devolve
`Capa` **sem baixar imagem**; se uma cair (timeout, 429, mudança de formato) as
outras continuam:

| Prioridade | Provedor | Portão |
|---|---|---|
| 1 | Cover Art Archive do **álbum confirmado** (IA + MusicBrainz) | `types` = Front |
| 2 | Cover Art Archive por busca | confiança MusicBrainz ≥ 0,70 |
| 3 | Apple Music / iTunes | mesmo álbum quando o álbum é conhecido |
| 4 | Deezer (API pública, sem chave) | artista igual |
| 5 | Discogs (token próprio em `discogs.txt`) | álbum no nome do lançamento |
| 6 | miniatura do vídeo | **desligada** por padrão (não é capa) |
| — | Spotify | **apenas referência** (`referencia_spotify`), nunca baixa/incorpora |

`metadata/correspondencia.py` — pontuação com **portões** (aprovado/reprovado) e
**nota** (para desempatar edições):

| Componente | Peso | Portão |
|---|---|---|
| título | 0,28 | ≥ 0,85 |
| artista | 0,28 | ≥ 0,55 (quando conhecido) |
| álbum | 0,22 | ≥ 0,60 (quando conhecido) |
| ano | 0,07 | — |
| ISRC/MBID | 0,10 | — |
| tipo de imagem (frontal) | 0,05 | frontal obrigatória |

Sem artista **e** sem álbum → **nenhuma capa** (não se inventa). Nota total mínima
0,62. Quando dois candidatos ficam a ≤ 0,06 de distância, o app **pergunta**
(`busca_capas.ambiguidade`) em vez de escolher sozinho.

`metadata/capa_validacao.py` — imagem vazia/quebrada, `< 1 KB`, menor que o
mínimo (300 px padrão), proporção > 1,35 (banner não é capa). O `tagging.gravar`
repete a checagem antes de embutir o APIC: imagem inválida nunca entra no MP3.

Cache: `capas/cache/<sha1 da URL>.<ext>` — a mesma capa nunca é baixada duas
vezes; `covers.limpar_cache(dias)` remove as antigas.

---

## 7. Identificação musical com IA (`ia/`) — opcional

Liga e desliga em **Configurações → Identificação com IA (Groq)**.
Desligada (padrão), o app é exatamente o da versão 0.2.

**O que é enviado** (só isto — `montar_pedido()`):

```json
{ "titulo_do_video": "...", "canal": "...", "url": "https://...",
  "duracao_segundos": 355, "titulo_sugerido_pela_busca": "...",
  "artista_sugerido_pela_busca": "...", "album_sugerido": null, "ano_sugerido": null }
```

**O que nunca é enviado**: cookies.txt (nem o caminho dele), a chave da API
(vai só no cabeçalho `Authorization`), arquivos do computador, histórico, banco.
O log não registra a chave (filtro em `logging_setup.py` + máscara `gsk_…cdef`).

**Como a resposta é obrigada a vir** —
`POST https://api.groq.com/openai/v1/chat/completions` (a Groq usa `/openai/v1`),
`Authorization: Bearer gsk_…`, `temperature 0`, `response_format: json_schema`
(`strict: true`), schema fechado com `additionalProperties: false` e estes campos.
Se o modelo escolhido não suportar `json_schema`, o cliente repete a chamada com
`{"type": "json_object"}` (HTTP 400 é o sinal) — assim qualquer modelo da lista
da Groq funciona. Em `HTTP 429` ele espera o `retry-after` (até 8 s) e tenta
uma vez mais, porque o plano gratuito limita requisições e tokens por minuto.

| Campo do schema | Vira | Regra imposta no prompt |
|---|---|---|
| `identificado`, `confianca` (0–1) | `Identificacao.ok`, `.confianca` | `ok` só se título **e** artista vierem preenchidos |
| `titulo`, `artista`, `banda` | TIT2, TPE1, TPE2 | não confundir intérprete / grupo / canal |
| `artistas_participantes` | `feat.` em TPE1 | convidados, sem repetir o principal |
| `compositores`, `letristas`, `produtores` | TCOM, TEXT, TPRO+TIPL | papéis separados; nunca deduzir um do outro |
| `album`, `ano`, `data_lancamento` | TALB, TDRC/TYER | álbum **original** daquela gravação |
| `genero`, `faixa`, `gravadora` | TCON, TRCK, TPUB | — |
| `isrc`, `mbid_gravacao` | relatório + conferência | identificadores só se conhecidos |
| `versao` | decide remaster/live/relançamento | `estudio\|ao vivo\|remaster\|acustico\|cover\|remix\|demo\|instrumental\|edit` |
| `campos_incertos`, `observacoes` | mostrados na UI | lista do que a IA **não** confirmou |

**Regra “não inventar”**: o prompt proíbe preencher por dedução (null é
preferível a errado) e o schema exige o campo `campos_incertos`. No Python,
tudo é normalizado (`_texto`, `_lista`, `_ano`, `_faixa`, `_data`) e o que vier
fora do formato vira vazio — não existe caminho em que um palpite vire tag.

**Conferência no MusicBrainz** (`_conferir_musicbrainz`): o álbum devolvido é
procurado em `/ws/2/release-group`; se o grupo for encontrado,
`verificado_musicbrainz = True`, o nome do álbum passa a ser o oficial e o
`mbid_release_group` é guardado — é ele que libera a capa do álbum na cascata
(§6). Se não for encontrado, o campo `album` entra em `campos_incertos` e a
capa daquele álbum não é usada como “oficial”.

**Falha da IA nunca derruba o job** — 401, timeout, JSON inválido ou texto fora
do schema viram `identificacao.erro` no relatório, a etapa mostra
“IA não confirmou: …” e o pipeline segue com iTunes + MusicBrainz como na 0.2.
Testado com servidor falso (`ok`, `401`, JSON entre cercas e resposta lixo).

**Chave da API** (`seguranca.py`) — formato da Groq, `gsk_…`: ordem de leitura
**`GROQ_API_KEY`** (ambiente) → **`api.txt`** na raiz do projeto (também
`api_key.txt` / `apikey.txt`) → **`credenciais/groq.dat`**, sempre fora do
`config.json` e cifrado com DPAPI no Windows (`0600` no Linux).
O `api.txt` é o caminho "sem interface": o usuário cria o arquivo e cola a
chave; `limpar_texto()` aceita chave pura, `GROQ_API_KEY=…`, `"…"`, `Bearer …`,
BOM do Notepad e comentários `#`/`//`. Se o `api.txt` já existe, o botão
*Salvar chave* **atualiza esse arquivo** (senão o antigo continuaria vencendo a
prioridade) e o botão *Apagar* remove `api.txt` **e** o cofre. A interface
mostra o caminho em uso (`caminho_legivel()`), só exibe a máscara (`gsk_…cdef`)
e tem **Criar/abrir api.txt**, **Testar conexão** (`GET /openai/v1/models`, que
lista os modelos da conta e alimenta o combo) e **Apagar**.
`ia_url_base` é configurável (padrão `https://api.groq.com/openai/v1`) para
quem quiser apontar para outro provedor compatível com OpenAI.

---

## 8. Organização e anti-duplicata (`organizer.py`)

* Template configurável: `{artista}/{artista} - {titulo}.mp3` (padrão),
  `{artista}/{album}/{faixa} {titulo}.mp3`, `{genero}/...`, etc.
* `sanitizar()`: remove `<>:"/\|?*`, caracteres de controle, pontos/espaços
  finais, palavras reservadas do Windows (`CON`, `NUL`, `COM1`…) e limita o
  tamanho; `"A_ _Live_"` → `"A Live"`.
* `resolver_conflito()`: se o arquivo existe e o tamanho é praticamente igual
  (<2%), considera **duplicado** e não faz nada; senão cria `nome (2).mp3`.
* `caminho_destino()` valida que o resultado fica **dentro** da pasta escolhida
  (proteção contra template estranho).

---

## 9. `cookies.txt` — tratamento

* Procurado em `RiffLab\cookies.txt` (ou caminho alternativo nas Configurações).
* Verificação na inicialização e ao abrir Configurações: existe · legível ·
  tamanho · linhas · **quantidade** de cookies/domínios · data de modificação ·
  formato Netscape válido.
* **Nunca** exibe valores, nunca grava conteúdo em log (`logging_setup` tem um
  filtro que troca `cookie: …`/`token=…` por `***`), nunca envia para terceiros.
* Só é repassado ao `yt-dlp` **por caminho de arquivo** e apenas se aquela fonte
  estiver ativa.
* Sem o arquivo, o app funciona normalmente com Internet Archive + biblioteca
  local (o estado aparece nas Configurações e no rodapé da janela).

---

## 10. Interface (paleta da arte enviada)

Extraída da referência (spray neon sobre parede roxa): fundo `#12001A`/`#1A0526`,
superfícies `#240A33`/`#2E0F40`, bordas `#4B1A66`, e os neons
**violeta `#C018E4`**, **magenta `#FF2BD0`**, **azul `#6C48F0`**,
**ciano `#22E8FF`**, **lima `#B6FF3D`**, **amarelo `#FFE13D`**,
**laranja `#FF6B3D`**, **vermelho `#FF4D6D`**.
Gradientes violeta→azul nos botões primários; selos de qualidade usam a cor do
rótulo; barra de progresso violeta→ciano.

Telas: **Pesquisar** (barra, filtros de fonte, ordenação, cartões com capa,
selos codec/bitrate/taxa/qualidade, combo de formatos e “Processar”), **Downloads**
(progresso ao vivo, abrir arquivo/pasta, cancelar), **Biblioteca** (indexação e
tabela codec/kbps/kHz/duração/capa), **Histórico** (pesquisas e processamentos),
**Configurações** (cookies, ferramentas, saída, capas, fontes).
Sem emojis dependentes de fonte: só glifos e formas.

---

## 11. Modelo de concorrência

* `QThreadPool` (via `workers.Executor`, 6 threads) para pesquisa, análise,
  indexação, miniaturas e jobs do pipeline.
* `Tarefa` (QRunnable) mantém **referência viva** no `Executor` — sem isso o
  coletor de lixo do Python destrói o objeto de sinais e a UI nunca recebe o
  resultado (bug encontrado e corrigido durante os testes).
* Sinais Qt fazem a ponte thread→UI (`Signal(object)`, `Signal(int, str)`).
* `GerenciadorFila` processa até **`downloads_simultaneos`** jobs ao mesmo tempo
  (1–4, padrão 2 — mais que isso rende HTTP 429/verificação de robô na
  plataforma) e persiste cada mudança de estado no SQLite. Estados por música:
  `na fila → analisando → baixando → metadados → convertendo → finalizando →
  finalizado | erro | cancelado`.
* Gravação de arquivo: `temp/` → move para a pasta final; se algo falhar, o
  arquivo original nunca é meio-gravado.

---

## 12. Banco de dados (SQLite, WAL)

```sql
historico(id, tipo['pesquisa'|'processamento'], consulta, fonte, detalhe, n_itens, criado_em)
downloads(id, titulo, artista, album, ano, fonte, codec, bitrate, sample_rate,
          qualidade, acao['copiar'|'recodificar'], capa_fonte, caminho, tamanho,
          status, progresso, erro, criado_em, fim_em)
biblioteca(id, caminho UNIQUE, titulo, artista, album, ano, codec, bitrate,
           sample_rate, duracao, tamanho, tem_capa, modificado, indexado_em)
```

Uma conexão compartilhada com `RLock` (`check_same_thread=False`), índices por
data e por artista.

---

## 13. Limites, licenças e responsabilidade

* **Internet Archive**: acervo público/CC; cada item traz a licença, exibida no
  cartão. Respeite a licença do item.
* **iTunes / MusicBrainz / Cover Art Archive**: APIs públicas, sem chave; uso
  pessoal e identificado (User-Agent próprio). MusicBrainz limitada a 1 req/s
  (o módulo respeita com lock + backoff).
* **yt-dlp**: fonte padrão, exige aceite (aviso mostrado uma vez). **Baixar
  conteúdo protegido sem autorização viola os termos das plataformas e a lei de
  direitos autorais** — a responsabilidade é de quem usa. Prefira CC, domínio
  público ou material próprio.
* **Por que a leitura de formatos pode falhar**: a lista de busca do yt-dlp é
  “flat” (não abre o vídeo); já `-J` abre, e é nesse passo que a plataforma
  aplica verificação de robô/região/idade. Por isso o app trata a detecção como
  opcional, mostra o motivo real e mantém o download disponível.
* **Groq** (opcional): GroqCloud tem plano gratuito (com limite de
  requisições/tokens por minuto) e planos pagos — o consumo é da sua conta;
  uma chamada por música identificada. Sem chave ou com `ia_ativa=False` nada é
  enviado. A Groq recebe só os campos do §7 (nunca cookies, chave ou arquivos).
* O app é **local**: nenhuma telemetria, nenhum servidor próprio.

---

## 14. O que foi testado (e como)

Executado neste ambiente (Linux, mesma stack; no Windows o código é o mesmo,
mudam apenas os caminhos e os `.exe`):

| Item | Resultado |
|---|---|
| `audio_probe` com ffprobe **e** sem ffprobe (`ffmpeg -i`) | FLAC/WAV/MP3 lidos corretamente |
| Conversão FLAC→MP3, WAV→MP3, MP3→MP3 | `recodificar 320k` / `copiar` (sem reencode) |
| Tags + capa | `tem_capa=True`, 449.610 bytes de APIC, faixa `7/22`, gênero `Rock` |
| Organização | `downloads/Queen/Queen - Bohemian Rhapsody.mp3` |
| Deduplicata / nomes inválidos | `"Bohemian Rhapsody: \"Live\" / 1975 <r>"` → `Bohemian Rhapsody Live 1975 r` |
| Cookies | ausente / vazio / inválido / válido → estados corretos, sem expor valores |
| Busca yt-dlp | `ytsearch` real com `--dump-single-json` → 4 resultados, artista tirado do canal |
| Qualidade automática | cartões passam de “qualidade a verificar” para `OPUS 160 kbps · 48 kHz` sem travar a UI |
| Pipeline yt-dlp | download → OPUS → MP3 (bitrate equivalente) → tags iTunes → `downloads/Queen/…mp3` |
| yt-dlp ausente | aviso em Configurações + mensagem na busca (nada de resultado vazio silencioso) |
| Detecção bloqueada (`Sign in to confirm…`) | selo “qualidade não detectada” + motivo no rodapé/toast + **download funcionando** |
| Detecção lenta (8 s por vídeo) | 3 cartões verificados em 8,5 s (paralelo), UI livre o tempo todo |
| Quantidade = 3 | 3 primeiras marcadas automaticamente; botão `BAIXAR SELECIONADOS (3)` |
| Fila com limite 4 | 3 jobs simultâneos, cada um percorrendo todos os estados, sem travar |
| Qualidade MP3 | `Automática` → equivalente; `Alta` → 320 kbps; `Personalizada 192` → 192 kbps |
| Capa ligável | `baixar_capa=False` → sem capa; `incorporar_capa=False` → tags sem APIC |
| Temporários | `manter_temporarios=True` → `temp/<uid>/audio_orig.webm` preservado |
| Melhor vídeo | `detalhar()` devolve `1080p · 30 fps · vp9` (preferência av1 > vp9 > h264) |
| Config antiga | `modo_mp3: "320"` migrado para `qualidade_mp3: "alta"`; simultâneos limitados a 4 |
| SQLite | histórico, downloads e biblioteca gravados e consultados |
| Pesquisa real (plug-in Archive) | “bohemian rhapsody” → 5 resultados com 64/128/180 kbps e FLAC |
| Pipeline completo (pela UI) | job `finalizado`, 100%, arquivo com capa e tags |
| Cofre da chave Groq | `credenciais/groq.dat` criado com permissão `0600` (DPAPI no Windows); máscara `gsk_…ghij`; `GROQ_API_KEY` e `api.txt` têm precedência |
| Caminho real da Groq | cliente chama `/openai/v1/chat/completions` e `/openai/v1/models`; `Authorization: Bearer gsk_…`; UA `RiffLab/0.4` |
| Modelo sem `json_schema` | HTTP 400 → cliente repete com `json_object` e identifica normalmente (`formatos tentados: ['json_schema', 'json_object']`) |
| Limite de uso (HTTP 429) | respeita `retry-after`, tenta de novo e conclui (2 requisições, ~1 s de espera) |
| Teste de conexão | `GET /v1/models` → 3 modelos em 0,03 s, combo preenchido, mensagem “Conexão OK” |
| Identificação (servidor falso da Groq) | `openai/gpt-oss-120b`, confiança `0.93`, compositores `['Freddie Mercury']`, produtores `['Roy Thomas Baker','Queen']`, gravadora `EMI` |
| Conferência MusicBrainz | release-group *A Night at the Opera* (1975) confirmado → `verificado_musicbrainz=True`, capa CAA `1200x1200` |
| IA com chave errada (401) | job **finalizado** mesmo assim; `identificacao.erro` = “chave da API inválida ou revogada”; capa cai para o iTunes |
| IA devolvendo JSON entre cercas / lixo | cercas ```json são aceitas; lixo → “a resposta da IA não é um JSON válido” e o job segue |
| IA desligada | pipeline idêntico à 0.2 (sem etapa `identificando`, sem `identificacao` no relatório) |
| Tags completas + relidas | `TCOM Freddie Mercury`, `TEXT`, `TPRO Roy Thomas Baker/Queen`, `TPUB EMI`, `TDRC 1975-10-31`, `TPE2 Queen` |
| Caso real: "Take Me Away" (Christina Vidal) | antes: capa do álbum *Bizaar* (Insane Clown Posse) com score fixo 0.86 vencia o iTunes; depois: `Freaky Friday: Original Soundtrack` (coverartarchive, confiança 1.0) |
| Mesma música com artista ausente | nenhuma capa aplicada, motivo no relatório: "artista e álbum não confirmados…" (antes: capa de outro álbum) |
| Mesma música com canal "Disney" | artista do canal é descartado e a busca usa o "Artista - Título" do vídeo → single oficial de 2025 |
| Álbum errado no vídeo ("Now 15") | repete sem o álbum e ainda acha o OST certo (confiança 1.0) |
| Capa do álbum × miniatura | capa do álbum confirmado vence mesmo com score menor; iTunes sem álbum compatível é recusado; miniatura só com opt-in |
| Privacidade do pedido | servidor falso falha se a palavra “cookie” aparecer no corpo enviado |

| Interface offscreen (1440×900) | 6 telas renderizadas sem erro; miniaturas carregadas |
| Fontes | yt-dlp (padrão): OK · Internet Archive: OK quando ligado · Biblioteca local: OK |

---

### 14.1 Testes da 0.5.0 (`testes/testes_v050.py` — `TESTES.bat`)

| # | Caso | Resultado |
|---|---|---|
| 1 | estúdio fica / `was_live` vai para filtrados com motivo | OK |
| 2 | “Ao vivo” no título filtra; a música “Live Forever” não | OK |
| 3 | prioridade estúdio > tópico oficial > show | OK |
| 4 | URL `youtube-nocookie/embed`, bloqueio explicado, nenhum download | OK |
| 5 | capa do artista certo aprovada; de outro artista recusada | OK |
| 6 | imagem inválida/pequena recusada, 600×600 aprovada | OK |
| 7 | CAA só frontal (Back/Booklet/Medium recusados) | OK |
| 8 | canal não vira artista (`DisneyMusicVEVO` → `Christina Vidal`) | OK |
| 9 | MP3 com TIT2/TPE1/TPE2/TALB/TCOM/TEXT/TDRC/TRCK/TCON/TPUB/APIC | OK |

Além disso, testes manuais de integração (rede real): busca por “Take Me Away”
com o yt-dlp, filtro de ao vivo ponta a ponta, cascata de capas
(CAA 300×300 × iTunes 1200×1200 → vence a maior), diálogo de confirmação,
diálogo de capa, recusa de capa (MP3 sai sem APIC) e capturas de tela em
`docs/`.

---

## 15. Próximos passos sugeridos

1. **Playlist/álbum inteiro**: processar todas as faixas de uma playlist/álbum
   (com a IA, o álbum já vem identificado: é só não pedir capa duas vezes).
2. **Análise espectral** (FFT) para detectar “MP3 320 de origem 128” (upscale).
3. **Comparação A/B** de duas fontes da mesma música (player embutido).
4. **Importar/exportar M3U** e **renomear em lote** por template.
5. **Tema claro** e escolha de cor de destaque na interface (a paleta já é
   parametrizada em `theme.DESTAQUES`).
6. **Assinatura/tamanho**: gerar executável único com PyInstaller (o `main.py`
   já detecta `sys.frozen`).

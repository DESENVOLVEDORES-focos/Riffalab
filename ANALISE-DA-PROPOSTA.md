# Análise da proposta — RiffLab 0.2

> Documento de decisão: o que a proposta pede, o que já existe, **quais problemas
> técnicos ela tem**, o que foi decidido e a estrutura final do projeto.
> Leia junto com `ARQUITETURA.md` (detalhes de cada módulo) e `LEIA-ME.md` (uso).

---

## 1. Resumo executivo

A proposta é coerente e o desenho geral (pesquisar → selecionar → baixar →
converter → capa → metadados → MP3) é exatamente o que o app já faz. Três pontos,
porém, **não podem ser implementados como estão escritos** sem prejuízo real:

| Ponto da proposta | Problema | Decisão |
|---|---|---|
| §4 "baixar melhor vídeo + melhor áudio, combinados" | Baixar vídeo para extrair MP3 joga 90% do tráfego no lixo (tabela no §3.1) | Analisar o vídeo e **mostrar** a qualidade dele, mas baixar **só a melhor faixa de áudio**; o vídeo só é baixado quando não existe faixa só de áudio (ou se ela falhar) |
| §3 "melhor qualidade = maior bitrate" | Maior bitrate bruto nem sempre é melhor áudio (tabela no §3.2) | Pontuação por **codec + bitrate equivalente + taxa de amostragem**, e não por número cru |
| §8 "Nome da Música.mp3" na raiz de `Downloads/` | Nomes colidem entre artistas e entre versões | Pasta por artista (`Artista/Artista - Título.mp3`) por padrão, com deduplicação e sufixo em conflito |

O resto da proposta está implementado como pedido — incluindo os controles
simplificados, os estados por música e a análise em segundo plano.

---

## 2. Proposta × estado atual

| § | Pedido | Estado |
|---|---|---|
| 1 | Verificar `cookies.txt` no start, tratar como sensível, não logar conteúdo | **feito** (`app/cookies.py` + `Configurações → Autenticação`) |
| 2 | Barra de pesquisa, resultados com thumb/título/canal/duração | **feito** |
| 3 | Análise de formatos em segundo plano, invisível ao usuário | **feito** (`detalhar()` em pool de threads, 3 simultâneas) |
| 3 | Info de vídeo: codec, resolução, fps | **novo** — o cartão passa a mostrar `Vídeo 1080p · 30 fps · vp9` |
| 4 | Download automático da melhor qualidade | **feito**, com a decisão do §3.1 abaixo |
| 5 | Conversão MP3 de alta qualidade + opção simples | **ajustado** — `Automática / Alta / Personalizada` |
| 6 | Capa automática incorporada (ID3/APIC) | **feito** (iTunes 1200×1200 → Cover Art Archive → miniatura) |
| 7 | Metadados título/artista/álbum/ano/faixa | **feito** (mutagen, ID3v2.3 + ID3v1 opcional) |
| 8 | Exemplo com 5 músicas do Guns N' Roses | **feito** |
| 9 | Modo em lote + seleção manual | **novo** — campo **Quantidade** (marca os N primeiros) + caixas de seleção |
| 10 | Interface simplificada (pesquisar, quantidade, resultados, baixar) | **ajustado** — 1 botão principal `BAIXAR SELECIONADOS (N)` |
| 11 | Mostrar o que o yt-dlp encontrou | **novo** — linha de resumo por música |
| 12 | Configurações: áudio, download, metadados, autenticação | **reorganizado** nessas 4 seções |
| 13 | Nada congela; estados por música | **feito** + **novo** estado "analisando" |
| 14 | `temp/` e limpeza automática | **feito** + opção **manter temporários** (debug) |
| 15 | Código modular | **feito** (ver §4; nomes diferentes, responsabilidades iguais) |
| 16 | Python, PySide6, yt-dlp, FFmpeg, Mutagen, SQLite | **feito** |
| 17 | Usuário não vê `-f`, bitrate, codec… | **feito** |
| 18 | Local, simples, profissional | **feito** |

---

## 3. Problemas técnicos identificados

### 3.1 Baixar o vídeo para extrair o áudio é desperdício de banda e de tempo

Números reais de uma música de 4 minutos no YouTube:

| O que se baixa | Tamanho típico | Tempo em 20 Mbps | Serve para o MP3? |
|---|---|---|---|
| Opus 160 kbps (só áudio) | ~4,8 MB | ~2 s | **sim**, é a fonte do MP3 |
| MP4 1080p (vídeo+áudio) | ~90–140 MB | ~40–60 s | áudio idêntico, resto é lixo |
| `bestvideo+bestaudio` (merge) | 100–200 MB | ~1 min + mux | idem |

Baixar o vídeo multiplica o tráfego por **20–40×**, aumenta a chance de o YouTube
aplicar *throttling* (é justamente o padrão que ele detecta como "download de
vídeo") e gasta disco em `temp/`. Como a saída é MP3, **o áudio é a única coisa
necessária**.

**Decisão:** o app analisa os formatos de **vídeo** (para poder informar
`Melhor vídeo: 1080p · 30 fps`) e baixa **a melhor faixa só de áudio**. Se o
vídeo não tiver faixa exclusiva de áudio (raro: transmissões antigas, alguns
uploads), o app baixa o arquivo muxado e extrai o áudio dele — ou seja, o
"vídeo + áudio combinados" da proposta continua existindo, mas **como exceção**,
não como caminho padrão. Toda essa decisão fica invisível para o usuário.

### 3.2 "Maior bitrate" não é "melhor qualidade"

O YouTube costuma oferecer dois codecs para o mesmo vídeo:

| Codec | Bitrate nominal | Qualidade percebida equivalente em MP3 |
|---|---|---|
| Opus (webm) | 160 kbps | ~288 kbps |
| AAC (m4a) | 128 kbps | ~166 kbps |

Se o app escolhesse o "maior bitrate" de forma crua, escolheria bem nesse caso,
mas há situações em que um AAC 192 kbps de um upload antigo (reencode de MP3 128)
é pior que um Opus 130 do upload oficial. Por isso a nota usa **fatores de
equivalência por codec** (`quality.FATOR_EQUIV`), taxa de amostragem e o
histórico de o arquivo ser lossless — e não só o número.

**Decisão:** ordenação por pontuação (`quality.pontuar`), com `FATOR_EQUIV`,
preferência por opus/m4a originais e desempate por taxa de amostragem. O MP3
final é gerado no **bitrate equivalente** (opus 160 → MP3 ~288 kbps), para não
jogar qualidade fora na conversão.

### 3.3 A análise de formatos é o passo caro e frágil

A lista de resultados vem de um `ytsearch` "flat" (rápido, não abre o vídeo). Ler
os formatos reais exige abrir cada vídeo (`yt-dlp -J`), e é aí que a plataforma
aplica verificação de robô, limite de requisições (`429`) e restrição de
idade/região.

**Decisão (já em vigor):** a análise roda em segundo plano (3 por vez), com
**1 tentativa e 45 s** por vídeo, nunca bloqueia o botão de baixar, e o erro é
traduzido para português (`Sign in to confirm you're not a bot` → *"o YouTube
pediu verificação de robô — use um cookies.txt atualizado"*). O cartão mostra
`melhor áudio disponível (qualidade não detectada)` e continua funcionando.

### 3.4 Downloads simultâneos: mais rápido até certo ponto

Paralelizar 6 músicas no YouTube é o caminho mais curto para `HTTP 429` e para a
verificação de robô. **Decisão:** padrão **2 simultâneos**, máximo 4, ajustável
em Configurações. O gargalo real é o ffmpeg (CPU), não a rede.

### 3.5 "Quantidade: 5" precisa de semântica explícita

Se o usuário digitar 5 e marcar 3 na mão, quem manda? **Decisão:** o campo
*Quantidade* **marca automaticamente os N primeiros** (por relevância) logo
depois da busca. Qualquer ajuste manual nas caixas passa a valer — o campo não
volta a sobrescrever a escolha. O botão principal mostra sempre o número real:
`BAIXAR SELECIONADOS (3)`.

### 3.6 Nome do arquivo e deduplicação

`Nome da Música.mp3` na raiz quebra em três casos: (a) duas músicas homônimas de
artistas diferentes; (b) a mesma música em duas versões (ao vivo/álbum);
(c) caracteres inválidos do Windows (`\ / : * ? " < > |`).
**Decisão:** template `{artista}/{artista} - {titulo}.mp3` (equivalente ao
exemplo do §8, um nível abaixo), sanitização de nome, e conflito resolvido com
`(2)` — nada é sobrescrito sem o usuário permitir.

### 3.7 A capa pode ser da música errada

APIs de metadados casam por texto. "November Rain" existe em estúdio, ao vivo,
cover e remix. **Decisão:** cascata iTunes → Cover Art Archive → miniatura do
vídeo, com **pontuação de similaridade mínima** e rejeição de imagem pequena
(< 300 px). Se nada passar, o app usa a miniatura do vídeo (que é do próprio
conteúdo baixado) em vez de uma capa duvidosa.

### 3.8 Metadados nunca degradam o que já é certo

O título do vídeo é a fonte primária. Álbum/ano/faixa/gênero vêm do iTunes e só
são aplicados quando a confiança é alta; o app **não** troca artista e título por
palpite. Se o vídeo se chama "Guns N' Roses - November Rain (Official Video)",
o arquivo sai como artista `Guns N' Roses`, título `November Rain`.

### 3.9 O yt-dlp envelhece em semanas

Plataformas mudam o player com frequência; um `yt-dlp.exe` de dois meses atrás
falha em massa. **Decisão:** o app **não** distribui o binário (licença + tamanho
+ atualização): o usuário baixa, e há um botão **Atualizar yt-dlp** nas
Configurações que roda `yt-dlp.exe -U` e mostra o resultado.

### 3.10 Cookies: sensível por definição

O arquivo dá acesso à conta do usuário. **Decisão (já em vigor):** o app lê no
máximo metadados estruturais (existe? tamanho? quantos cookies? formato
Netscape?), **nunca** o conteúdo; não aparece em tela, não vai para log e é
entregue ao yt-dlp **por caminho**. Sem o arquivo, tudo funciona.

### 3.11 Legalidade não é detalhe técnico

O app entrega uma ferramenta; o conteúdo é responsabilidade de quem baixa. O
aviso aparece uma vez (gravado em `config.json`), e cada resultado mostra
`conferir licença na origem`.

### 3.12 `temp/` órfão

Se o app for fechado no meio de um download, sobra lixo. **Decisão:** cada job usa
uma pasta própria (`temp/<uid>/`), a limpeza acontece no `finally` (inclusive em
erro) e `pipeline.limpar_temp()` remove pastas com mais de 1 dia no start.

---

## 4. Estrutura final do projeto

A árvore pedida no §15 foi mantida em **responsabilidade**, não em nome. O
projeto já é modular e cada item pedido tem um módulo equivalente (alguns
agrupados, porque 20 arquivos de 15 linhas é pior que 8 de 80):

```
RiffLab/
├── main.py                     # bootstrap: deps, pastas, janela, --debug
├── INICIAR.bat                 # Windows: venv + deps + executa
├── DIAGNOSTICO.bat             # estado do ambiente
├── TESTAR_YTDLP.bat            # testa o yt-dlp fora do app
├── cookies.txt                 # (opcional) autenticação — nunca exibido
├── config.json                 # preferências (criado no 1º start)
├── requirements.txt            # PySide6 + mutagen
├── LEIA-ME.md · ARQUITETURA.md · ANALISE-DA-PROPOSTA.md
│
├── app/
│   ├── config.py               # caminhos, padrões, Config (JSON)
│   ├── models.py               # AudioFormat, TrackResult, MetaFinal, ArquivoInfo
│   ├── quality.py              # pontuação, rótulos, equivalência de codec
│   ├── texto.py                # normalização, similaridade, limpeza de título
│   │
│   ├── cookies.py              # §1  cookies_manager  → só status, nunca conteúdo
│   ├── sources/                # §2  search          → pesquisa plugável
│   │   ├── base.py             #     (contrato FonteBase)
│   │   ├── ytdlp.py            #     ytdlp/analyzer + downloader
│   │   ├── archive_org.py      #     fonte extra opcional
│   │   └── local_library.py    #     fonte extra opcional
│   ├── search_service.py       #     orquestra fontes + dedupe + ordenação
│   │
│   ├── audio_probe.py          # §3/§5  (ffprobe/ffmpeg -i)
│   ├── convert.py              # §5  audio/converter  → MP3 (copy ou encode)
│   ├── tagging.py              # §7  metadata/manager → ID3 + capa APIC
│   ├── metadata/               # §6  metadata/cover
│   │   ├── itunes.py
│   │   ├── musicbrainz.py      #     + Cover Art Archive
│   │   └── covers.py           #     cascata + pontuação
│   ├── image_utils.py          #     recorte/validação de capa
│   ├── organizer.py            # §8  nomes, dedupe, mover
│   ├── pipeline.py             # §13 uma música: todas as etapas
│   ├── downloader.py           # §9/§12 batch_manager + fila + simultâneos
│   ├── workers.py              #     execução em threads (QThreadPool)
│   ├── db.py                   #     SQLite: downloads, histórico, biblioteca
│   ├── tools.py                #     localiza ffmpeg/ffprobe/yt-dlp
│   │
│   └── ui/                     # §10 interface
│       ├── theme.py            #     paleta neon + QSS
│       ├── main_window.py      #     janela + navegação
│       ├── widgets/            #     result_card, images, toast
│       └── pages/              #     search, downloads, library, history, settings
│
├── downloads/                  # saída organizada (Artista/…mp3)
├── capas/                      # cache de capas
├── temp/                       # intermediários (limpos sempre)
└── ferramentas/                # ffmpeg.exe, ffprobe.exe, yt-dlp.exe
```

---

## 5. Fluxo completo (o que acontece em cada música)

```
[usuário] digita "Guns N' Roses" → Enter
   └─ Estado: PESQUISANDO            search_service → yt-dlp ytsearchN
      └─ resultados na tela; campo Quantidade marca os N primeiros

[segundo plano, 3 por vez]  Estado: ANALISANDO QUALIDADE
   └─ yt-dlp -J <url> → formatos de áudio + melhor vídeo
      ├─ sucesso  → selos OPUS 160 kbps · 48 kHz · Vídeo 1080p · Excelente
      └─ falha    → "qualidade não detectada" + motivo (download segue)

[usuário] BAIXAR SELECIONADOS (N)     → fila (até 2 simultâneos)
   baixando → analisando → capa+metadados → convertendo → gravando tags → organizando
   └─ Estado final: FINALIZADO (caminho) ou ERRO (motivo em português)

[pipeline] 1 obtém melhor áudio · 2 mede o arquivo real · 3 metadados · 4 capa
           5 converte/copia para MP3 · 6 grava ID3+APIC · 7 organiza · 8 limpa temp
```

Estados exibidos por música (`app/db.py` → `downloads.status`):
`na fila · analisando · baixando · metadados · convertendo · finalizando ·
finalizado · erro · cancelado`.

---

## 6. O que o usuário controla (e o que não controla)

| Visível | Invisível (decidido pelo app) |
|---|---|
| termo de pesquisa | qual formato de áudio é o melhor |
| quantidade (1–20) | codec, bitrate, taxa de amostragem |
| quais músicas (caixas) | se precisa baixar vídeo (fallback) |
| qualidade MP3: Automática / Alta / Personalizada | parâmetros do ffmpeg (`-c:a copy`, `-b:a`, VBR) |
| pasta de destino | template de nome e deduplicação |
| downloads simultâneos (1–4) | tentativas/timeout do yt-dlp |
| manter temporários (debug) | limpeza de `temp/` |
| capa automática / incorporar capa | cascata de fontes de capa |
| status do `cookies.txt` | como o cookie é passado ao yt-dlp |

---

## 7. Limites conhecidos

* **Não é 100% garantido** obter capa/álbum/ano: depende de o iTunes/Cover Art
  Archive terem o lançamento. Sem eles, o app usa a miniatura do vídeo.
* **Vídeos com DRM, privados ou regionais** continuam falhando — o app mostra o
  motivo e não trava a fila.
* **Playlist/álbum inteiro** não está no escopo desta versão (§14 é por música);
  a fila aceita N selecionadas, que cobre o caso de uso do §9.
* **Windows-only** na prática: `INICIAR.bat`, `ferramentas\*.exe`. O núcleo roda
  em Linux (foi desenvolvido e testado nele).
* O yt-dlp e o ffmpeg **não** são distribuídos com o app.

---

## 8. Plano aplicado nesta versão (0.2)

1. `config.py` — novas chaves: `qualidade_mp3`, `mp3_bitrate`, `downloads_simultaneos`,
   `manter_temporarios`, `baixar_capa`, `incorporar_capa`, `quantidade_padrao`
   (com migração das antigas `modo_mp3`).
2. `sources/ytdlp.py` — `detalhar()` também extrai **melhor vídeo** (resolução,
   fps, codec) e escolhe o áudio por pontuação; download prefere faixa só de
   áudio com fallback para muxado.
3. `models.py` — `TrackResult.video` + resumo legível.
4. `ui/widgets/result_card.py` — selos de vídeo e linha "o que será baixado".
5. `ui/pages/search_page.py` — campo **Quantidade** (marca os N primeiros) e
   botão único **BAIXAR SELECIONADOS (N)**.
6. `ui/pages/settings_page.py` — 4 seções do §12 + botão **Atualizar yt-dlp**.
7. `downloader.py` — downloads simultâneos configuráveis.
8. `pipeline.py` — respeita `baixar_capa`, `incorporar_capa`, `manter_temporarios`.
9. `main.py` — mensagem do §1 ("nenhuma configuração de autenticação local").
10. Testes: fluxo completo com yt-dlp simulado nos três cenários (ok, sem
    formatos, lento) + UI offscreen + capturas + pacote.

---

## 9. Plano aplicado nesta versão (0.3) — identificação musical com IA

Objetivo: o Groq (API oficial da Groq) identifica a música **antes** de capa e
tags, sem tocar em nada que já funcionava (proposta §7: a IA não baixa, não
converte e não grava — quem faz isso continua sendo yt-dlp, FFmpeg e Mutagen).

| Onde | O que entrou |
|---|---|
| `models.py` | `TrackMeta` ganhou `compositores`, `letristas`, `produtores`, `artista_album`, `banda`, `participantes`, `versao`, `isrc`, `mbid`, `fonte_identificacao`; nova dataclass `Identificacao` (resposta da IA + `campos_incertos` + `verificado_musicbrainz`) |
| `seguranca.py` (novo) | onde a chave é lida: `GROQ_API_KEY` → **`api.txt` na raiz** (`limpar_texto()` aceita chave pura, `GROQ_API_KEY=…`, `"…"`, `Bearer …`, BOM e comentários) → `credenciais/groq.dat` (DPAPI no Windows, 0600 no Linux); `mascarar()` para exibir só `gsk_…cdef`; `guardar()` atualiza o `api.txt` quando ele existe e `apagar()` remove os dois |
| `ia/cliente_groq.py` (novo) | cliente HTTP com `urllib` (sem dependência nova) para a **Groq**: `/openai/v1/chat/completions` com `response_format: json_schema strict` + fallback `json_object` no 400, `temperature 0`, retry com `retry-after` no 429, erros 401/403/5xx traduzidos e `testar()` via `/openai/v1/models` |
| `ia/identificador.py` (novo) | prompt com regras “não invente / não confunda papéis”, schema fechado (`additionalProperties: false`), normalização de tudo que volta, `_conferir_musicbrainz()` |
| `metadata/musicbrainz.py` | `buscar_release_group()` para confirmar o álbum e obter o mbid |
| `metadata/covers.py` | capa do **álbum confirmado** entra como candidata prioritária; miniatura só com opt-in; iTunes só aceita álbum compatível; mensagem explícita quando não há capa oficial |
| `tagging.py` | `TCOM`, `TEXT`, `TPRO` (recriado após `update_to_v23`), `TPUB`, `TPE2`, `TDRC` completo + `TYER`, `TIPL`; `ler()` devolve os campos novos |
| `pipeline.py` | etapa `identificando` (58%) entre a análise e os metadados; `montar_metadados(..., ident=)` e `buscar_capa(..., ident=)`; `relatorio["identificacao"]` |
| `downloader.py` / `downloads_page.py` | status `identificando` e linha “IA: …” no job |
| `settings_page.py` | cartão “Identificação com IA (Groq)”: chave mascarada, modelo, **Testar conexão**, selo do estado da chave, nota de privacidade, opt-in da miniatura |
| `theme.py` | `alfa()` — o Qt lê `#AARRGGBB`; os selos usavam `#RRGGBBAA` e saíam laranja |

**Decisões que ficam registradas**

1. **Nada de IA obrigatória**: `ia_ativa=False` por padrão. Sem chave, sem
   cobrança, sem enviar nada a terceiros.
2. **Schema fechado em vez de “texto bonito”**: o modelo é obrigado a devolver
   todos os campos (com `null` quando não sabe) e a listar `campos_incertos`.
3. **MusicBrainz como juiz do álbum**: o Groq sugere, a MusicBrainz confirma.
   Sem confirmação, o álbum não é usado para escolher capa.
4. **Capa oficial ou nenhuma**: miniatura de vídeo virou opção explícita
   (desligada), porque é exatamente o erro que a proposta §4 apontava.
5. **Falha da IA não é falha do job**: qualquer erro vira texto no relatório e o
   processamento continua com iTunes/MusicBrainz.
6. **`api.txt` na raiz (0.3.1)**: o usuário pediu o caminho mais óbvio — criar um
   arquivo de texto com a chave dentro. Fica acima do cofre na prioridade, tem
   modelo pronto (`api.txt.exemplo`), botão **Criar/abrir api.txt** na interface,
   entrada no `.gitignore` e aviso de que é texto puro (quem quiser cifra usa o
   campo da interface, que grava o `groq.dat` com DPAPI).
7. **Groq, não Grok (0.4.0)**: a integração é com a **GroqCloud**
   (`api.groq.com/openai/v1`, chave `gsk_…`), não com o Grok da xAI. O que mudou:
   URL base, modelo padrão (`openai/gpt-oss-120b`, strict structured outputs),
   variável `GROQ_API_KEY`, cofre `credenciais/groq.dat` e o módulo
   `ia/cliente_groq.py`. Um `config.json` antigo com `api.x.ai`/`grok-*` é
   migrado sozinho na abertura.
8. **Compatibilidade de ID3**: `TPRO` é frame 2.4 e o app grava 2.3 — por isso
   `TIPL` antes da conversão e `TPRO` recriado depois (verificado relendo o MP3).

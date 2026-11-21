# RiffLab — começar no Windows

Este pacote contém o aplicativo em Python, os testes e as imagens de documentação.
Ele **não é um executável independente**: Python, yt-dlp e FFmpeg são necessários.
O download real do YouTube e a interface no Windows ainda precisam ser validados no seu computador.

## Abrir pela primeira vez

1. Extraia o pacote para uma **pasta nova** (não sobrescreva sua cópia antiga).
2. Instale Python 3.10 ou superior para Windows, se ainda não tiver. Marque a opção de adicionar Python ao PATH.
3. Crie a pasta `ferramentas` dentro da nova pasta do RiffLab e copie da sua instalação anterior `ffmpeg.exe` e `yt-dlp.exe`. Se tiver `ffprobe.exe`, copie também; ele é opcional. Alternativamente, instale as ferramentas no PATH.
4. Clique duas vezes em `INICIAR.bat`. Na primeira execução ele cria `.venv`, instala as dependências e tenta baixar o Deno oficial pela internet (cerca de 43 MB). Se o Deno não puder ser instalado, o RiffLab ainda abre. Veja **DENO.md**.
5. Em **Configurações → Ferramentas externas**, confira os caminhos e as versões detectadas, inclusive do Deno. Se copiar os arquivos com o programa aberto, clique em **Procurar novamente**. Um arquivo que não executa é mostrado como indisponível. Escolha também a pasta de saída e salve.
6. Opcional: em **Configurações → cookies.txt → Escolher cookies.txt**, selecione seu arquivo Netscape. Cookies são credenciais sensíveis; nunca os compartilhe. O aplicativo guarda o caminho, não copia o arquivo.
7. Opcional: configure a chave Groq em **Configurações → Identificação com IA**, teste a conexão e ative a identificação. Não compartilhe sua chave.

## Como baixar

1. Em **Pesquisa normal** ou **Várias músicas**, procure a música e o artista ou cole um link de vídeo do YouTube. Use a prévia para distinguir versões e shows e escolha o formato de áudio. Por padrão é escolhido o melhor disponível; a verificação detalhada pode levar alguns segundos. Sinais como Topic ou VEVO ajudam a priorizar resultados, mas não garantem que o canal seja oficial.
2. Marque os resultados e clique em **Adicionar a Downloads** (ou use **Adicionar** em um cartão). Isso ainda não baixa o áudio.
3. Em **Downloads**, marque ou desmarque cada música. Use **Escolher capa** para pesquisar e revisar as opções de cada uma, ou **Revisar capas selecionadas** para revisá-las em sequência. Confirme a imagem desejada ou escolha **Não usar capa**. Se não encontrar capa, você pode continuar sem ela ou cancelar e tentar novamente.
4. Quando as capas das músicas marcadas tiverem sido revisadas, clique em **Baixar selecionadas**. Elas serão processadas uma por vez, na ordem da lista, com conversão para MP3 e gravação de tags e da capa escolhida. Os itens desmarcados permanecem na lista.

As marcações e a lista de seleção de Downloads são salvas no banco local; a pesquisa exibida não é restaurada ao fechar o aplicativo. Os arquivos finalizados ficam na pasta configurada, por padrão `downloads`.

Se algo falhar, execute `DIAGNOSTICO.bat` e examine `rifflab.log`. Não envie logs sem antes remover dados pessoais ou informações sensíveis. O `TESTAR_YTDLP.bat` ajuda a diagnosticar o yt-dlp: ele usa `cookies.txt` apenas se estiver na raiz do projeto; o arquivo escolhido em Configurações não é usado por esse teste. Os arquivos de diagnóstico podem conter links e dados pessoais. Plataformas podem mudar, pedir autenticação ou bloquear consultas; manter o yt-dlp atualizado pode ajudar, mas não garante disponibilidade. Baixe somente conteúdo que você tem direito de baixar.

A conversão de uma origem com perda (como Opus ou AAC) para MP3 pode introduzir perda adicional, mesmo usando 320 kbps. No modo automático, MP3s compatíveis são copiados sem recodificar.

### Capas: fontes e busca manual

Em Configurações, confira quais fontes de capa estão ativadas. A tela de escolha também mostra as fontes ativadas; o nome junto à imagem indica apenas de qual delas veio aquela opção. Se não encontrar um single, é possível salvar uma imagem adequada no navegador e usar **Escolher imagem salva**, conferindo antes de confirmar. Nenhuma capa de álbum é usada automaticamente como substituta.

### Mais informações sobre capas

Veja **CAPAS-E-FONTES.md** para ativar o Deezer em configurações anteriores, comparar capas e pesquisar no Google Imagens pelo navegador. A imagem salva deve ser conferida e usada apenas quando você tiver direito.

### Aviso de músicas já baixadas

Cada novo MP3 recebe uma marca RiffLab. A pesquisa verifica a pasta de saída e pode verificar outra pasta escolhida, incluindo subpastas. Veja **MUSICAS-JA-BAIXADAS.md** para detalhes e limitações.

### Pesquisa de qualidade

Esta versão compara quatro métodos de consulta de formatos sem iniciar download de áudio. Veja **QUATRO-METODOS.md** para entender os resultados, instalação da biblioteca opcional e limitações.

### Detalhes de cada formato

No cartão de pesquisa, use **Comparar formatos** para ver os dados informados de cada opção e escolher uma delas. Veja **COMPARAR-FORMATOS.md**.

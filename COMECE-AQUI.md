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

A janela de capas não abre o navegador sozinha. Clique em **Pesquisar imagens no Google** quando quiser, copie a imagem no navegador e use **Colar imagem copiada**. Confira a imagem e os direitos de uso antes de confirmar. Veja **CAPAS-MANUAIS.md**; orientações de capas de versões anteriores são históricas.

### Visualizar MP3 e capas gravadas

No menu **Ver MP3 e capas**, confira as imagens ID3 embutidas e as tags dos MP3s já existentes, sem alterá-los. Veja **VISUALIZAR-MP3.md**.

### Conferir metadados e nomes dos próximos MP3s

Depois de preparar cada música em **Downloads**, confira o resumo e use **Editar dados** para corrigir título, artista principal, participações, álbum, gênero, ano, número da faixa e artista do álbum. O artista principal define a pasta e o título define o arquivo: `Artista/Título.mp3` no modelo padrão. Caracteres proibidos no Windows são substituídos; arquivos diferentes de mesmo nome recebem outro número; arquivos idênticos podem ser reaproveitados. Um modelo de organização personalizado continua valendo.

A IA (se ativada) e os catálogos podem falhar ou estar errados; não existe garantia de obter todos os campos. Confira inclusive o artista do álbum; quando o catálogo não o informa, o campo pode ficar vazio. Participações são gravadas junto ao artista (TPE1). A duração final é medida no MP3 após a conversão, não adivinhada pela IA. Em **Ver MP3 e capas**, é possível conferir os dados e a duração do arquivo gerado em modo somente leitura. Nada disso renomeia nem modifica MP3s antigos.

# Pesquisa, listas e downloads: seis melhorias

## 1. Marcações salvas
Marque **Incluir** na pesquisa. As marcações e o formato escolhido são salvos automaticamente no banco local `rifflab.db`, mesmo quando você pesquisa outra coisa ou fecha o RiffLab. Ao abrir de novo, o contador e o botão **Adicionar a Downloads** permitem transferi-las; os resultados da pesquisa em si não são restaurados na tela. A lista de músicas ainda não baixadas em **Downloads**, suas edições e escolhas de capa também são recuperadas. A recuperação não inicia downloads.

Se uma capa que estava escolhida tiver sido apagada ou movida, será preciso escolhê-la novamente. Caso apareça aviso de que não foi possível salvar ou recuperar os dados, não apague o banco: faça uma cópia dele e verifique espaço/permissões. Para fazer backup das suas marcações e listas, feche o RiffLab e copie `rifflab.db` para outro lugar; ele pode conter nomes e links das músicas. Não compartilhe o banco sem verificar seu conteúdo. O RiffLab não copia o arquivo de cookies nem a chave de API para as marcações; links informados por você podem conter dados privados.

## 2. Pesquisas aparecem conforme terminam
Na aba **Várias músicas**, cada seção surge assim que sua pesquisa termina, mesmo que outra ainda esteja procurando. Você já pode marcar resultados; as seções permanecem na ordem dos campos. Erros aparecem na seção afetada. Até três pesquisas de termos podem ocorrer em paralelo; a velocidade depende das fontes.

## 3. Editar dados
Em **Downloads**, clique em **Editar dados** em uma música para corrigir título, artista e álbum antes de baixá-la. Título e artista são necessários; álbum pode ficar vazio. Os dados escolhidos são usados nas tags e na organização do novo arquivo, por exemplo `Artista/Título.mp3` no modelo padrão. A música original selecionada não é alterada. Depois de editar é necessário revisar ou dispensar a capa novamente, pois ela pode ser de outra música.

## 4. Tentar um download novamente
Quando uma tentativa falha, clique em **Tentar novamente** no cartão do erro. Uma nova tentativa entra na fila com o mesmo formato, os dados editados e a capa escolhida; ela não apaga o registro da falha. Confira mensagens de pasta indisponível ou capa ausente antes de tentar. Esse botão vale para falhas da sessão atual: ele não recupera automaticamente trabalhos depois de fechar o aplicativo. Fechar durante um download ou com trabalhos já iniciados pode interrompê-los; espere terminar sempre que possível.

## 5. Listas de músicas
Na pesquisa, marque as músicas e clique em **Listas salvas → Salvar marcações em uma lista**. Dê um nome como “Rock para o carro”. No mesmo botão, você pode **Carregar uma lista** (ela é adicionada às marcações atuais) ou **Excluir uma lista**. Excluir uma lista não apaga músicas no computador nem outras marcações. Uma lista de mesmo nome só é substituída após confirmação. As listas ficam no banco local; não são playlists de sites externos nem arquivos M3U.

## 6. Capas em lote
Em **Downloads**, marque as músicas desejadas:
- **Revisar capas selecionadas** busca opções e permite confirmar uma capa ou escolher sem capa para cada música. Confira sempre: os catálogos podem conter erros ou usar arte igual à do álbum.
- **Preparar selecionadas sem capa** pede confirmação e prepara todas sem imagens, sem procurar capas. Isso substitui as escolhas de capa anteriores para os itens selecionados, mas não altera MP3s já baixados.

Nenhuma dessas duas ações baixa o áudio. Após a preparação, use **Baixar selecionadas**. Você continua podendo escolher ou trocar a capa individualmente.

## Testes e limites
Os testes foram feitos em Linux com Qt offscreen, fontes simuladas e FFmpeg local, inclusive reabertura da janela e gravação real de tags em um áudio de teste. Não houve teste no Windows nem testes de pesquisa/download nos serviços externos nesta sessão. As fontes e os formatos podem mudar ou ficar indisponíveis.

## Ajustes após a revisão

O formato escolhido é preservado quando uma verificação posterior não o encontra. Nesse caso ele aparece como **não confirmado**: se estiver indisponível, o download falha e informa o motivo, sem mudar para outro formato por conta própria. A opção automática **Melhor áudio disponível** continua buscando o melhor áudio. Apagar o álbum no editor também remove a tag de álbum antiga do novo arquivo, sem alterar o original.

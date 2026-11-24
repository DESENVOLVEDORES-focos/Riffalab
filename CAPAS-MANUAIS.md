# RiffLab 0.8.0 — capas do Google e conferência dos dados

A busca automática por APIs de **capas** foi desativada, inclusive para chamadas antigas do fluxo sem preparação. Os serviços de metadados e a IA, se ativada, continuam sendo usados para tentar identificar a música e preencher tags; são serviços diferentes da pesquisa de capa e podem errar. Os campos são sugestões, não uma garantia de que sejam do lançamento original. Confira sempre título, artista, álbum, gênero, ano, número da faixa, artista do álbum e participações antes de baixar. A duração final é medida depois da conversão. Use **Editar dados** para corrigir, sem alterar os MP3s já existentes.

## Escolher a capa

1. Em Downloads, clique em **Escolher capa** (ou em **Revisar capas selecionadas** para seguir uma música de cada vez). O navegador abre automaticamente a pesquisa de imagens do Google com o artista e o título daquela música. Se ele não abrir, clique em **Pesquisar imagens no Google**.
2. Escolha e confira a imagem. Para copiar, use **Copiar imagem** no navegador, volte ao RiffLab e clique em **Colar imagem copiada**. A imagem colada será salva dentro de `RiffLab/Download de Capas`, sem substituir imagens anteriores.
3. Ou use **Salvar imagem como** no navegador e selecione a pasta `RiffLab/Download de Capas`. De volta ao RiffLab, clique em **Escolher imagem salva**; o seletor começa nessa pasta. **Abrir pasta de capas** ajuda a localizá-la.
4. Confira a prévia e pressione **Usar esta capa**, ou **Não usar capa**. O download não é iniciado até sua confirmação na tela Downloads.

O navegador controla a pasta de destino do comando **Salvar imagem como**; o RiffLab não consegue mudá-la automaticamente. Se o navegador salvar em Downloads, pode mover a imagem para `Download de Capas` ou encontrá-la pelo seletor. O botão Colar precisa ser pressionado depois de copiar. JPEG, PNG e WebP são aceitos; WebP é convertido para PNG para inclusão no MP3. A imagem precisa ter no mínimo 300 pixels de cada lado e no máximo 6000, até 15 MB e proporção adequada a uma capa. Confira também os direitos de uso.

## Atualização segura

Encerre os downloads e o aplicativo, faça backup de `config.json` e `rifflab.db`, e mescle a pasta do ZIP completo com a instalação existente. Não apague configurações, banco, cookies, músicas, ferramentas, ambiente ou `Download de Capas`. O ZIP não contém esses dados locais. Arquivos de instruções das versões anteriores são históricos e podem descrever o fluxo antigo.

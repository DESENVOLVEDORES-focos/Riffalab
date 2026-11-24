# Revisão de capas — versão 0.7.0

Para cada música selecionada, a preparação pesquisa separadamente pelo título e artista identificados, priorizando os dados editados por você e usando a IA quando disponível e confiável. A identidade usada aparece na janela para conferência. Se não estiver certa, cancele e use **Editar dados** antes de preparar novamente.

Na revisão, podem aparecer capas de **Single**, **Álbum** e **Coleção (tipo não confirmado)**. O iTunes classifica coleções como “Album” mesmo quando podem ser singles: por isso a identificação é apresentada como coleção, salvo quando o nome indica single. O tipo, o vínculo com a faixa e a edição original dependem dos catálogos e podem estar incorretos. Confira a imagem antes de escolher **Usar capa**; versões remasterizadas, coletâneas e lançamentos de outros países podem ter artes diferentes. Nenhum serviço garante encontrar a original. Se faltar a capa, escolha uma imagem manualmente ou **Não usar capa**.

**Pesquisa manual:** clique em **Pesquisar imagens no Google**, abra o resultado desejado no navegador e copie a imagem (não apenas o endereço). Volte à janela e clique em **Colar imagem copiada**, confira e confirme. Alternativamente, salve a imagem no computador e use **Escolher imagem salva**. Use uma imagem de pelo menos 300 pixels de cada lado. O Google abre no navegador e não precisa de chave de API; ele pode mostrar miniaturas ou imagens não relacionadas, que devem ser conferidas, assim como os direitos de uso.

As fontes configuradas são consultadas independentemente e podem falhar ou limitar resultados; erros dos serviços continuam registrados na janela de iniciar. O modo sem revisão continua restrito a singles. As mudanças não modificam músicas existentes nem a rotina de download.

## Atualização sem apagar dados

Encerre o aplicativo após os downloads, faça backup de `config.json` e `rifflab.db` e extraia o ZIP completo mesclando a pasta do aplicativo existente. Substitua os arquivos do programa quando solicitado, mas não exclua configurações, banco, cookies, músicas, ferramentas ou ambiente. O pacote não contém esses dados locais.

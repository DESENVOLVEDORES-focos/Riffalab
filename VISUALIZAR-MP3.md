# Visualizar e editar MP3 e capas — RiffLab 0.11.7

1. No menu esquerdo, clique em **Ver MP3 e capas**. O programa lê a pasta de saída e suas subpastas; só a leitura não altera os arquivos.
2. Selecione a música. O painel mostra os dados e a imagem **ID3/APIC embutida no próprio MP3**. Se houver várias imagens, a capa frontal aparece primeiro e você pode escolher as demais na lista.
3. Use **Escolher pasta de MP3s**, **Escolher um MP3**, **Atualizar lista** ou o filtro para encontrar outros arquivos. São listados até 5.000 arquivos por vez; para ver mais, escolha uma subpasta.

## Corrigir os dados e a capa de uma música existente

1. Selecione o arquivo correto e confira o caminho. Clique em **Editar dados e capa**. O editor carrega as tags existentes; não é preciso baixar a música novamente.
2. Corrija título, artistas, álbum, gênero, ano/data, faixa ou artista do álbum. O campo de artista contém o crédito ID3 existente; o campo de participações serve para acrescentar nomes. Valores que você não modificar são preservados. Apagar um campo é uma remoção explícita. A data aceita AAAA, AAAA-MM ou AAAA-MM-DD e a faixa aceita número ou número/total.
3. Opcionalmente clique em **Pedir nova sugestão à IA**. A consulta envia título, artista, álbum e sua observação à Groq, não o áudio nem o caminho do arquivo. A IA exige ativação e chave; MusicBrainz e iTunes são consultados separadamente. Confira as sugestões: nenhuma identifica o áudio com garantia, e a IA não pesquisa a internet nem escuta a música. Você pode editar os campos ou cancelar.
4. Para mudar a imagem, clique em **Trocar ou remover capa frontal**. Você pode pesquisar imagens no navegador, colar a imagem copiada ou selecionar uma imagem do computador e confirmar. **Remover capa frontal** retira as imagens frontais, preservando outras imagens embutidas. Para não mudar a imagem atual, não escolha uma ação ou clique em **Manter a capa original**. Cancelar a janela de capa não muda sua escolha anterior.
5. Clique em **Salvar** e confirme o caminho. A operação atualiza somente o MP3 selecionado, sem baixá-lo, renomeá-lo ou recodificar seu áudio. A leitura e a gravação acontecem em segundo plano; aguarde a conclusão antes de fechar.

Antes da substituição, o RiffLab cria na mesma pasta um **backup integral do original** chamado, por exemplo, `musica.mp3.rifflab-backup` (com sufixo numérico se já existir). Guarde-o até confirmar o resultado no seu player; backups ocupam espaço. Para restaurar, feche o aplicativo, faça uma cópia do arquivo atual e renomeie uma cópia do backup para o nome original `.mp3`. Cópias extras são recomendadas, especialmente para músicas importantes.

Se o arquivo for alterado por outro programa desde a abertura do editor, ou se faltar espaço/permissão, a edição é interrompida sem substituir o original. Links simbólicos, arquivos com múltiplos links físicos e versões antigas de ID3 não suportadas são recusados por segurança. Outros programas e aparelhos podem armazenar informações e imagens fora das tags ID3; o aplicativo não os altera. O resultado pode variar com players, permissões, arquivos ou tags incomuns.

**Sem imagem ID3** significa que a leitura não encontrou imagens APIC; um player ainda pode usar uma imagem de pasta ou cache. Uma imagem grande ou inválida pode constar como existente sem ser exibida. Erros de leitura não são tratados como ausência de capa.

A opção **Preparar selecionadas sem capa** em Downloads continua afetando somente novos downloads; não altera automaticamente seus MP3s existentes.

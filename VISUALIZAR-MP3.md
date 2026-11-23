# Visualizar MP3 e capas — RiffLab 0.6.2

1. No menu esquerdo, clique em **Ver MP3 e capas**. O programa lê a pasta de saída configurada e suas subpastas, sem alterar os arquivos.
2. Clique em uma música para ver título, artista, álbum e a imagem **ID3/APIC embutida no próprio MP3**. Se houver mais de uma imagem, escolha-a na lista; a capa frontal aparece primeiro.
3. Use **Escolher pasta de MP3s**, **Escolher um MP3**, **Atualizar lista** ou o filtro para encontrar outros arquivos. São listados até 5.000 arquivos por vez; para ver mais, escolha uma subpasta.

**Sem imagem ID3** significa que a leitura não encontrou imagens APIC nas tags ID3. Isso não garante que todo aparelho mostrará uma tela vazia: players também podem usar cache, imagens de uma pasta ou outras fontes que não são tags APIC. Uma imagem embutida com formato inválido ou tamanho grande é indicada como existente mesmo quando não puder ser exibida. Erros de leitura também são mostrados; não são tratados como ausência de capa. A tela não busca imagens na internet e não escreve, move ou apaga MP3s.

## Preparar sem capa

Em Downloads, **Preparar selecionadas sem capa** prepara apenas as músicas marcadas na lista, não inicia downloads e não altera MP3s já existentes. O aplicativo confirma a quantidade marcada e desmarcada. Depois de preparar, é preciso clicar em **Baixar selecionadas**. Nas novas conversões preparadas sem capa, o programa remove e verifica as imagens ID3/APIC antes de concluir; se a remoção ou leitura falhar, avisa o erro em vez de concluir silenciosamente. Nenhum arquivo antigo é modificado automaticamente.

Se um player mostrar uma capa onde esta tela indicar ausência de APIC, verifique se você está abrindo o mesmo caminho e considere que o player pode usar uma imagem da pasta ou cache. Não apague arquivos só por esse indício. O visualizador foi testado em Linux/Qt offscreen; o funcionamento no Windows e em aparelhos externos precisa ser confirmado no seu ambiente.

O painel também mostra gênero, ano, número da faixa, artista do álbum e duração medida do MP3 quando disponíveis. O artista exibido é o campo ID3 que pode conter as participações. A leitura não altera o arquivo.

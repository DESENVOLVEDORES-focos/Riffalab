# RiffLab 0.10.1 — capa manual e revisão dos dados

A pesquisa de capas é manual: a janela **não abre o Google automaticamente** e não consulta serviços de capas. A IA opcional e os catálogos de metadados são independentes da escolha da imagem.

## Escolher a capa

1. Em Downloads, clique em **Escolher capa** ou em **Revisar capas selecionadas** para seguir uma música de cada vez.
2. A janela abre com dados provisórios enquanto a IA (se ativa) e os catálogos procuram os metadados em segundo plano. Você já pode clicar em **Pesquisar imagens no Google** e copiar a imagem; o Google não abre sozinho. Se a identidade mudar após a pesquisa, haverá um aviso: confira-a e pesquise novamente se necessário.
3. No navegador, clique com o botão direito na imagem desejada e escolha **Copiar imagem**. Volte ao RiffLab e clique em **Colar imagem copiada**. Não é preciso baixar nem selecionar um arquivo. A imagem colada será salva em `RiffLab/Download de Capas`, sem substituir imagens anteriores.
4. Aguarde a identificação dos metadados terminar, confira os dados e a prévia e pressione **Usar esta capa**, ou **Não usar capa**. O download só começa depois da confirmação na tela Downloads.

Você pode fechar a janela para cancelar enquanto os dados estão sendo identificados; a busca pode demorar mais quando os serviços estiverem lentos. Copie a imagem propriamente dita, não apenas o endereço. JPEG, PNG e WebP são aceitos; WebP é convertido para PNG na inclusão no MP3. A imagem precisa ter no mínimo 300 pixels de cada lado e no máximo 6000, até 15 MB e proporção adequada a uma capa.

## Confira os oito campos

A IA recebe instruções específicas para identificar título, artista principal, participações, álbum, gênero, ano, número da faixa e artista do álbum. As sugestões automáticas removem do título qualificadores técnicos como 4K e remasterização de ano, preservando indicações de versões musicais como ao vivo e remix. As edições feitas por você têm prioridade.

Para o álbum, o programa procura uma gravação compatível no MusicBrainz, prioriza um álbum regular associado e usa o nome do grupo de lançamento para preservar sua grafia; se não houver álbum, pode utilizar um single associado. Essa busca tem limites, e uma correspondência não garante que seja a edição original ou correta. Gêneros vêm dos catálogos e alguns nomes comuns têm grafia padronizada; não há garantia de classificação ou capitalização universal. Os números de faixa e dados de edição só são aproveitados sob verificações adicionais, mas ainda podem exigir correção.

Se não houver informações suficientes, alguns campos ficarão vazios. **Antes de baixar, use Editar dados para conferir e corrigir os oito campos.** A IA e os catálogos podem errar ou estar indisponíveis; não há garantia de acerto ou de todos os campos preenchidos. Músicas já baixadas não são alteradas. A duração final é medida depois da conversão.

## Pedir nova sugestão à IA

Em **Downloads**, abra **Editar dados** e clique em **Pedir nova sugestão à IA**. Se quiser, escreva no campo acima o que parece errado, por exemplo “o álbum está errado”. O RiffLab envia à Groq os dados da origem, os campos mostrados no editor e sua observação; não envie informações sensíveis nesse campo. Para funcionar, é preciso ter a IA ativada e a chave configurada em Configurações.

A consulta ocorre em segundo plano. A IA pode repetir a resposta, falhar ou errar; os valores sugeridos não são prova, inclusive o álbum. Confira tudo e clique em **Salvar** para aceitar no editor, ou **Cancelar** para descartar. Campos alterados enquanto aguarda não são substituídos; se mudar o título ou artista durante a consulta, peça novamente. Caso o álbum ou a música mude, dados antigos de edição sem nova sugestão são limpos para evitar misturas. Se título, artista ou álbum mudar, será necessário revisar a capa novamente antes de baixar. O botão não modifica MP3s já existentes.

## Atualização segura

Encerre os downloads e o aplicativo, faça backup de `config.json` e `rifflab.db` e mescle a pasta do ZIP completo com a instalação existente. Não apague configurações, banco, cookies, músicas, ferramentas, ambiente ou `Download de Capas`. O ZIP não contém esses dados locais. Arquivos de instruções das versões anteriores são históricos e podem descrever o fluxo antigo.

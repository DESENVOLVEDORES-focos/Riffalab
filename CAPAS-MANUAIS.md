# RiffLab 0.11.3 — capa manual e revisão dos dados

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

Em **Downloads**, abra **Editar dados**. Confira se **Título** e **Artista principal** identificam a música e não apenas o canal; corrija-os se necessário. Clique em **Pedir nova sugestão à IA**. Se quiser, escreva no campo acima o que parece errado, por exemplo “o álbum está errado”. O RiffLab envia à Groq o título original, título, artista, álbum e sua observação; não envie informações sensíveis nesse campo. A IA não escuta o áudio nem pesquisa na internet por si só. A consulta à IA requer ativação e chave em Configurações.

Em paralelo, o programa consulta separadamente MusicBrainz e, se não encontrar um lançamento compatível, iTunes. A busca usa título e artista juntos; não troca o artista informado por outro com música homônima. O álbum, ano e faixa propostos vêm do catálogo, não da confiança declarada pela IA. Uma participação sugerida pela IA é identificada como tal. Uma coleção do iTunes pode ser uma edição ou single diferente do álbum original. Mesmo uma associação de catálogo não comprova qual gravação há no vídeo; confira o resultado, especialmente versões ao vivo, remixes e diferentes edições.

Se a busca falhar, o catálogo estiver indisponível ou não houver correspondência, os campos ficam como estavam. O aplicativo informa a situação: confira o título e o artista e tente novamente ou edite manualmente. Se trocar o álbum misturaria campos antigos sem dados equivalentes, o conjunto anterior é mantido para correção manual. Campos alterados enquanto aguarda são preservados; se mudar título ou artista, peça novamente. A consulta ocorre em segundo plano; se a Groq recusar o formato da resposta, outras formas são tentadas sem trocar de modelo. **Salvar** aceita os dados no editor e **Cancelar** descarta. Se título, artista ou álbum mudar, a capa já escolhida fica guardada. Clique em **Revisar capa**: a mesma imagem aparecerá na janela, e você poderá confirmá-la, trocá-la ou escolher ficar sem capa, sem precisar copiá-la outra vez. Aguarde a atualização dos metadados antes de confirmar; se cancelar ou houver falha, a imagem continua guardada. A revisão fica pendente até a confirmação, inclusive ao reabrir o aplicativo. O botão não modifica MP3s já existentes.

## Atualização segura

Encerre os downloads e o aplicativo, faça backup de `config.json` e `rifflab.db` e mescle a pasta do ZIP completo com a instalação existente. Não apague configurações, banco, cookies, músicas, ferramentas, ambiente ou `Download de Capas`. O ZIP não contém esses dados locais. Arquivos de instruções das versões anteriores são históricos e podem descrever o fluxo antigo.

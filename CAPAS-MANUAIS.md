# RiffLab 0.11.6 — identificação automática e capa manual

A pesquisa de capas é manual: a janela **não abre o Google automaticamente** e não consulta serviços de capas. A IA opcional e os catálogos de metadados são independentes da escolha da imagem.

## Identificação automática ao transferir

Ao enviar músicas da pesquisa para Downloads, a seleção é salva antes de começar. Em segundo plano, a IA tenta identificar música e artista a partir do título original do vídeo. Em seguida, quando houver identidade suficiente, outra chamada usa título e artista para obter os demais dados, enquanto MusicBrainz e iTunes são consultados separadamente. O contador mostra quantas músicas ainda estão sendo identificadas; cada uma só aparece na lista quando essa etapa termina. Não é necessário abrir **Editar dados** para fazer as consultas. Se fechar durante a identificação, as músicas pendentes serão retomadas ao abrir novamente.

Álbum, ano e número da faixa são aproveitados do catálogo quando há correspondência compatível. A tela mostra os dados obtidos, eventuais créditos de catálogo e sugestões da IA separadas como não confirmadas. A IA não ouve o áudio nem pesquisa na internet: mesmo resultados bem avaliados podem estar errados ou incompletos. Se a IA estiver desativada, indisponível ou incerta, os dados de origem são preservados com aviso; campos sem confirmação podem ficar vazios. Se precisar corrigir algo, use **Editar dados**. Nenhuma música é baixada durante a identificação.

## Formatos em Downloads

A pesquisa não consulta mais a qualidade dos vídeos nem lista os formatos de cada resultado. Isso evita disparar verificações para todos os vídeos encontrados, inclusive nas pesquisas múltiplas e nos resultados filtrados. A ordem de pesquisa é por relevância, não por qualidade.

Depois que uma música aparecer em **Downloads**, clique em **Verificar formatos** nessa música se quiser consultar suas opções. A consulta ocorre em segundo plano, uma música por vez. Quando terminar, clique em **Comparar formatos** e escolha o formato desejado. A escolha é salva e não altera os dados ou a capa. Se a consulta falhar, a escolha anterior é mantida e você pode tentar novamente. **Áudio automático** volta à escolha automática.

A verificação é opcional. Sem selecionar um formato, o yt-dlp escolhe o melhor áudio disponível ao iniciar o download; o formato exato só será conhecido nesse momento. Os valores exibidos são informados pelas fontes, podem ser estimados e não comprovam a qualidade sonora. Uma escolha manual pode deixar de estar disponível na plataforma; nesse caso o aplicativo informa a falha em vez de trocar silenciosamente de formato.

## Escolher a capa

1. Em Downloads, clique em **Escolher capa** ou em **Revisar capas selecionadas** para seguir uma música de cada vez.
2. A janela usa os dados já identificados. Clique em **Pesquisar imagens no Google** quando desejar; o Google não abre sozinho. Se você corrigiu a identidade ou abriu uma seleção antiga, pode ser necessária uma atualização em segundo plano antes da confirmação.
3. No navegador, clique com o botão direito na imagem desejada e escolha **Copiar imagem**. Volte ao RiffLab e clique em **Colar imagem copiada**. Não é preciso baixar nem selecionar um arquivo. A imagem colada será salva em `RiffLab/Download de Capas`, sem substituir imagens anteriores.
4. Aguarde a identificação dos metadados terminar, confira os dados e a prévia e pressione **Usar esta capa**, ou **Não usar capa**. O download só começa depois da confirmação na tela Downloads.

Você pode fechar a janela para cancelar enquanto os dados estão sendo identificados; a busca pode demorar mais quando os serviços estiverem lentos. Copie a imagem propriamente dita, não apenas o endereço. JPEG, PNG e WebP são aceitos; WebP é convertido para PNG na inclusão no MP3. A imagem precisa ter no mínimo 300 pixels de cada lado e no máximo 6000, até 15 MB e proporção adequada a uma capa.

## Confira os oito campos

A IA recebe instruções específicas para identificar título, artista principal, participações, álbum, gênero, ano, número da faixa e artista do álbum. As sugestões automáticas removem do título qualificadores técnicos como 4K e remasterização de ano, preservando indicações de versões musicais como ao vivo e remix. As edições feitas por você têm prioridade.

Para o álbum, o programa procura uma gravação compatível no MusicBrainz, prioriza um álbum regular associado e usa o nome do grupo de lançamento para preservar sua grafia; se não houver álbum, pode utilizar um single associado. Essa busca tem limites, e uma correspondência não garante que seja a edição original ou correta. Gêneros vêm dos catálogos e alguns nomes comuns têm grafia padronizada; não há garantia de classificação ou capitalização universal. Os números de faixa e dados de edição só são aproveitados sob verificações adicionais, mas ainda podem exigir correção.

Se não houver informações suficientes, alguns campos ficarão vazios. **Use Editar dados somente se precisar corrigir os campos exibidos.** A IA e os catálogos podem errar ou estar indisponíveis; não há garantia de acerto ou de todos os campos preenchidos. Músicas já baixadas não são alteradas. A duração final é medida depois da conversão.

## Pedir nova sugestão à IA

Em **Downloads**, abra **Editar dados**. Confira se **Título** e **Artista principal** identificam a música e não apenas o canal; corrija-os se necessário. Clique em **Pedir nova sugestão à IA**. Se quiser, escreva no campo acima o que parece errado, por exemplo “o álbum está errado”. O RiffLab envia à Groq o título original, título, artista, álbum e sua observação; não envie informações sensíveis nesse campo. A IA não escuta o áudio nem pesquisa na internet por si só. A consulta à IA requer ativação e chave em Configurações.

Em paralelo, o programa consulta separadamente o MusicBrainz e, quando necessário, o iTunes para completar os dados. Número de faixa e artista do álbum só são combinados quando álbum e ano coincidem. A busca usa título e artista juntos; não troca o artista informado por outro com música homônima. O álbum, ano e faixa propostos vêm do catálogo, não da confiança declarada pela IA. O gênero pode ser uma sugestão da IA quando o catálogo não o informa; nesse caso, a tela identifica a origem. Uma participação sugerida pela IA é identificada como tal. Abaixo dos campos aparece um resumo organizado da resposta da IA, que não é confirmação nem pesquisa. Créditos da faixa e do álbum disponíveis no MusicBrainz aparecem separados; músicos do álbum sugeridos pela IA são marcados como não verificados e não são gravados automaticamente como participantes da música. Uma coleção do iTunes pode ser uma edição ou single diferente do álbum original. Mesmo uma associação de catálogo não comprova qual gravação há no vídeo; confira o resultado, especialmente versões ao vivo, remixes e diferentes edições.

Se a busca falhar, o catálogo estiver indisponível ou não houver correspondência, os campos ficam como estavam; quando a IA identifica a mesma música, seu resumo não confirmado ainda aparece para consulta. O aplicativo informa a situação: confira o título e o artista e tente novamente ou edite manualmente. Se trocar o álbum misturaria campos antigos sem dados equivalentes, o conjunto anterior é mantido para correção manual. Campos alterados enquanto aguarda são preservados; se mudar título ou artista, peça novamente. A consulta ocorre em segundo plano; se a Groq recusar o formato da resposta, outras formas são tentadas sem trocar de modelo. **Salvar** aceita os dados no editor e **Cancelar** descarta. Se título, artista ou álbum mudar, a capa já escolhida fica guardada. Clique em **Revisar capa**: a mesma imagem aparecerá na janela, e você poderá confirmá-la, trocá-la ou escolher ficar sem capa, sem precisar copiá-la outra vez. Aguarde a atualização dos metadados antes de confirmar; se cancelar ou houver falha, a imagem continua guardada. A revisão fica pendente até a confirmação, inclusive ao reabrir o aplicativo. O botão não modifica MP3s já existentes.

## Atualização segura

Encerre os downloads e o aplicativo, faça backup de `config.json` e `rifflab.db` e mescle a pasta do ZIP completo com a instalação existente. Não apague configurações, banco, cookies, músicas, ferramentas, ambiente ou `Download de Capas`. O ZIP não contém esses dados locais. Arquivos de instruções das versões anteriores são históricos e podem descrever o fluxo antigo.

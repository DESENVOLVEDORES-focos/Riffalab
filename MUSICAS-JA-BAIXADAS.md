# Aviso de músicas já baixadas

A partir desta versão, cada MP3 concluído pelo RiffLab recebe uma marca **RiffLab** no comentário ID3 e campos adicionais com a origem, identificador da origem, título e artista originais quando disponíveis. Comentários de outras pessoas são preservados; a aparência do comentário depende do programa usado para visualizar as propriedades do MP3.

Ao mostrar uma pesquisa, o aplicativo procura **em segundo plano**, na pasta de saída configurada e em todas as suas subpastas, MP3s com a marca RiffLab. Se seus MP3s ficam em outro lugar, vá em **Configurações → Músicas já baixadas → Escolher pasta**, selecione uma pasta adicional e salve. A pasta adicional e suas subpastas serão verificadas na próxima pesquisa. A verificação apenas lê os arquivos; não os altera, envia ou apaga. Não percorre todo o computador nem segue links de diretório automaticamente.

- **Já baixado (mesma origem):** o identificador de origem do resultado coincide com o que está no MP3. O caminho encontrado aparece no cartão.
- **Possivelmente já baixada — confira a versão:** título e artista coincidem exatamente após normalização, mas podem ser versões, gravações ou lançamentos diferentes. O aviso não garante que é a mesma gravação.

Os resultados continuam visíveis e podem ser escolhidos de novo. Quando terminar a verificação, o resumo fica abaixo do status da pesquisa; se alguma pasta ou arquivo não puder ser lido, o aviso diz que ela foi incompleta. Mover ou renomear o MP3 não atrapalha, desde que ele continue dentro de uma pasta verificada e conserve suas tags. Pesquise novamente após mover arquivos ou concluir downloads.

Arquivos baixados em versões anteriores **não são marcados retroativamente**; só aparecem na conferência se já contiverem comentário exatamente `RiffLab` e tiverem título e artista compatíveis. Outros MP3s não marcados não são identificados como downloads do aplicativo. Uma marca pode ser alterada ou removida por outros programas. A correspondência local não substitui a conferência antes de baixar novamente.

Testes nesta atualização: verificação com arquivos temporários e tags reais, pesquisa/avisos na interface Qt offscreen e um fluxo com áudio local convertido em MP3 pelo FFmpeg. Não houve execução no Windows nem teste com YouTube externo.

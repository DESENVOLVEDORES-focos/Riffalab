# Revisão de interface, links e ferramentas

Esta revisão foi feita durante o desenvolvimento, em Linux. O código usa Python e PySide6, que podem funcionar no Windows e no Linux, mas o pacote tem um iniciador `.bat` específico do Windows. As ferramentas instaladas precisam ser compatíveis com o sistema operacional em que serão executadas.

## O que foi conferido

- Inicialização do `main.py` e abertura/encerramento da janela Qt em modo sem tela no Linux.
- Botões e sinais principais em testes automáticos: pesquisa, escolha de resultados, transferência para Downloads, navegação, marcar/desmarcar, preparação de capa, remover item e início do lote; escolha de capa alternativa e cancelamento do diálogo.
- Controles de pasta de saída, cookies, gravação e ativação da chave Groq, verificação das ferramentas e prévia com abertura da página original. Escolha de arquivos e chamadas de rede foram simuladas nos testes de interface.
- A execução real de yt-dlp e FFmpeg no Linux: um arquivo de áudio de teste foi baixado de um servidor HTTP local pelo yt-dlp e convertido a MP3 pelo FFmpeg, com tags. Não foi um download do YouTube.
- Montagem dos argumentos para executáveis e cookies em caminhos com espaços, usando testes simulados. A busca por URL do YouTube e a seleção de formatos também foram exercitadas com respostas simuladas.
- Localização em `ferramentas/`, raiz, `bin/`, pasta atual e PATH. A versão é consultada para verificar se o processo inicia e retorna sucesso; se uma cópia falhar, outras localizações são tentadas. Isso não prova que o executável funcionará em todas as operações.

## Problemas corrigidos

- A pesquisa não enviava corretamente a opção de ordenação e o callback de progresso.
- A seleção de fontes da tela podia ser ignorada; uma fonte não escolhida podia ser usada sem aviso.
- Um executável inválido, que retornava erro ou não respondia, podia ser mostrado como disponível.
- O teste do yt-dlp informava que usaria o `cookies.txt` da raiz, mas não o passava ao comando.
- Um arquivo parcial da primeira tentativa de download podia ser escolhido após uma nova tentativa bem-sucedida.
- Arquivos com nomes e tamanhos parecidos podiam ser confundidos com duplicatas; agora só são considerados iguais após comparação do conteúdo.
- O botão Cancelar aparecia em downloads que já haviam começado, embora só funcionasse em itens aguardando na fila.
- O player incorporado não ativava a API para os comandos de tocar e pausar. Isso foi corrigido no endereço, mas a reprodução incorporada ainda precisa de teste real.
- A janela de resultados filtrados e detalhes de leitura de tags foram corrigidos. Salvar configurações não deve mais desfazer opções escolhidas na pesquisa. O inicializador agora tenta usar um `.venv` existente antes de procurar o Python e verifica a versão para criar um novo ambiente.

## Limitações e pendências

- Não havia máquina virtual Windows ou Wine disponível nesta revisão. O `.bat`, os executáveis `.exe`, o DPAPI e os diálogos nativos **não foram executados no Windows**. Caminhos e comandos foram revisados e simulados, mas não há garantia de funcionamento em toda instalação.
- O acesso de rede deste ambiente não permitiu testar uma pesquisa ou download real no YouTube, nem a API Groq, cookies reais ou os serviços de capas.
- O QtWebEngine não pôde ser carregado neste ambiente Linux; a prévia incorporada e seus botões precisam ser testados em uma instalação Windows. O fallback de abertura da página original foi testado com chamada simulada.
- A lista de seleção permanece durante a sessão, mas não é restaurada depois de fechar o aplicativo. Um download em andamento não tem botão de cancelamento efetivo; o botão Cancelar se aplica apenas aos itens aguardando na fila. Aguarde o processamento terminar antes de fechar.
- `INICIAR.bat` é o iniciador de desenvolvimento, não uma compilação. A criação de um `.exe` fica para uma etapa posterior.

Use apenas conteúdo que você tenha direito de baixar. Não compartilhe cookies, chaves ou diagnósticos sem remover informações sensíveis.

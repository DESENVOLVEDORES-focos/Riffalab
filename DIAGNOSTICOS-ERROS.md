# Diagnóstico de erros no RiffLab 0.6.5

Abra o aplicativo com `INICIAR.bat` e mantenha a janela preta aberta durante o uso. Falhas tratadas de pesquisa, consulta de formatos, preparação e download aparecem nela com horário e contexto, além de serem registradas em `rifflab.log` quando possível. A falha da pasta de saída também inclui o detalhe informado pelo sistema. Alguns métodos e serviços opcionais podem falhar mesmo quando outro método funciona; uma linha de erro não significa necessariamente que o download inteiro falhou.

A exibição oculta URLs e alguns padrões comuns de credenciais, mas não garante remover todo dado sensível. Mensagens podem conter nomes de músicas, nomes de usuário e caminhos. **Revise antes de enviar uma foto ou o log; nunca envie cookies, senhas, chaves ou tokens.** Caso o programa seja encerrado de forma abrupta, uma falha do Windows, de um componente nativo ou de energia pode não gerar diagnóstico no aplicativo.

Para atualizar uma instalação existente: aguarde o lote terminar e feche o RiffLab. Faça backup do banco `rifflab.db` e de `config.json`; extraia o ZIP e mescle seus arquivos com a instalação, sem excluir nem substituir os seus dados locais, cookies, músicas, ferramentas ou a pasta `.venv`. O pacote não inclui esses dados. Esta mudança não altera músicas existentes nem garante identificar a causa da falha observada no computador.

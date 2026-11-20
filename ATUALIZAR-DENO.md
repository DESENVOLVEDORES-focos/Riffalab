# Atualizar a versão de quatro métodos com Deno

Este pacote de atualização é para a versão `RiffLab-Windows-quatro-metodos.zip`. Se sua versão for diferente, use o pacote completo com Deno.

1. Feche o RiffLab.
2. Extraia este ZIP em uma pasta temporária.
3. Copie o conteúdo da pasta `RiffLab` extraída para a pasta onde estão o `INICIAR.bat` e o `main.py` da versão de quatro métodos. Confirme a substituição dos arquivos quando o Windows perguntar.
4. Abra o `INICIAR.bat`. Ele tentará baixar o Deno oficial em `ferramentas\deno.exe` (aproximadamente 43 MB). Aguarde: mesmo que a instalação falhe, o RiffLab abrirá.
5. Em Configurações → Ferramentas externas, verifique o status e a versão do Deno. Consulte `DENO.md` para limites e como tentar instalar novamente.

Este ZIP de atualização não contém `config.json`, `.venv`, cookies, banco de dados, downloads ou executáveis de ferramentas. Não apague esses arquivos da sua instalação. Caso o Windows peça para substituir uma pasta, mesclar as pastas é necessário; não apague a pasta atual. Feche o aplicativo antes da atualização para não substituir arquivos em uso.

A presença do Deno não garante que o YouTube disponibilize áudio. Os testes foram realizados fora do Windows e sem conexão real ao YouTube.

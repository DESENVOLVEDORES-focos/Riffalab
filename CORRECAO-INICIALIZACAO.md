# Correção da inicialização

Esta atualização substitui os arquivos de código do RiffLab por uma versão coerente, incluindo as seis melhorias e a revisão posterior. Ela corrige a exceção `SettingsPage` / `aviso_pasta_saida` informada após a abertura. É apropriada para atualizar instalações existentes das versões distribuídas nesta sequência.

1. Encerre o RiffLab e aguarde qualquer processamento terminar.
2. Faça uma cópia de segurança de `rifflab.db` e `config.json` em outra pasta. Preserve também seus cookies, arquivos de música e ferramentas.
3. Extraia este ZIP em uma pasta temporária. Abra a pasta `RiffLab` extraída.
4. Copie **o conteúdo** dela para dentro da pasta da sua instalação que contém `INICIAR.bat` e `main.py`; mescle as pastas e confirme a substituição dos arquivos existentes. Não apague a instalação.
5. Execute o `INICIAR.bat` da instalação atualizada.

O pacote não inclui `rifflab.db`, `config.json`, `cookies.txt`, músicas, ambiente virtual, Deno nem executáveis das ferramentas, portanto não deve substituí-los. O banco pode ser atualizado na abertura; a cópia de segurança é importante. O aviso de cookies do arquivo `.bat` se refere apenas a `cookies.txt` na pasta do programa; dentro do RiffLab pode estar selecionado um arquivo em outro caminho.

Não se trata de garantia de funcionamento em todas as instalações: esta correção foi testada em Linux, não no Windows nem em serviços online. Se surgir outro erro, envie o trecho correspondente do log, sem o conteúdo dos seus cookies ou chaves.

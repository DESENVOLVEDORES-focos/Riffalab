# Teste de sessão YouTube — RiffLab 0.6.6

Em Configurações → cookies.txt, clique em **Testar sessão no YouTube**. A verificação antiga só confere se o arquivo tem linhas no formato esperado; ela não confirma a sessão.

O botão novo pede ao yt-dlp para consultar até um item de sua lista pessoal **Assistir mais tarde**, usando uma cópia temporária do arquivo de cookies. O YouTube recebe as informações de autenticação necessárias, mas o RiffLab não exibe nem registra o título da lista, o item ou o conteúdo dos cookies. O teste não baixa áudio nem adiciona ou remove itens. A cópia é excluída ao terminar; o arquivo original não é alterado pelo teste. Outros usos do yt-dlp pelo aplicativo ainda podem atualizar o arquivo original.

Se for retornado um item da lista pessoal, o app informa que a sessão funcionou nessa consulta. Isso **não garante** acesso a todos os vídeos nem que o download de áudio evitará um erro 403. Se a lista estiver vazia ou a resposta for inesperada, o resultado é inconclusivo: para um teste mais informativo, você pode adicionar um vídeo à lista pelo próprio YouTube e repetir. Tempo esgotado, erro de rede, pedido de login ou recusa de acesso também não provam exatamente por que o teste falhou. Nunca envie cookies, senhas ou tokens.

Atualização: aguarde os downloads, faça backup de `rifflab.db` e `config.json`, feche o app e mescle os arquivos do ZIP sem apagar configurações, cookies, músicas, ferramentas ou `.venv`. A lista e os arquivos antigos não são modificados pela atualização.

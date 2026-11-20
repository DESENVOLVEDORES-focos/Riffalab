# Correção: pasta de saída indisponível

Se o RiffLab apresentava `FileNotFoundError: [WinError 3] ... 'D:\\'`, a pasta de saída configurada apontava para uma unidade ou caminho que o Windows não encontrou. Isso pode acontecer se uma unidade removível estiver desconectada ou a letra da unidade tiver mudado. Esse erro não comprova problema no Deno.

Nesta versão, abrir a interface não tenta criar a pasta configurada. O caminho antigo é preservado, sem alterar nem apagar configurações. Ao abrir o RiffLab, um aviso aparece se a pasta não estiver visível. Em **Configurações → Áudio e destino**, conecte a unidade original ou use **Escolher pasta** para escolher outra pasta existente. Clique em **Salvar configurações**. O programa não altera a pasta de saída automaticamente.

Antes de iniciar um lote de áudio, o RiffLab tenta criar/verificar o destino configurado e verifica se pode gravar nele com um arquivo temporário removido em seguida. Se falhar, mostra um aviso, mantém os itens na lista e não inicia o áudio. Também há verificação no início de cada processamento. Se a unidade for removida durante o processamento, o download pode falhar; a verificação inicial não garante que a unidade permanecerá disponível.

Nenhum arquivo de áudio, cookie, Deno ou configuração vem neste ZIP de correção. Não é necessário excluir `config.json` ou `.venv`. A correção foi exercitada em testes locais, inclusive com falha simulada de unidade e interface Qt offscreen; não foi executada no Windows nesta sessão.

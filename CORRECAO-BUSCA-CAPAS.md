# Ajustes na busca de capas — RiffLab 0.6.7

A busca separa o artista do título quando o artista detectado é um canal e o título está no formato “Artista - Música”. Isso modifica somente a consulta aos catálogos; não altera os metadados que foram escolhidos. Quando uma edição do Cover Art Archive tem apenas contracapa, o aplicativo também procura uma frontal no mesmo grupo de lançamento.

A busca automática continua limitada a lançamentos que os catálogos indicam como single e não substitui automaticamente pela capa de um álbum. O catálogo pode estar incompleto, indisponível ou errado; confira as opções na tela. A mudança não analisa nem altera músicas já baixadas, listas ou ferramentas de download. Ela não garante encontrar todas as capas.

Para atualizar, espere o lote terminar, faça backup de `rifflab.db` e `config.json`, feche o aplicativo e mescle os arquivos do ZIP com a instalação sem apagar configurações, banco, cookies, músicas, ferramentas ou `.venv`. Teste em novas preparações; suas músicas existentes não são alteradas.

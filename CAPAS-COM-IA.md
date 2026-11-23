# Busca de capas com identidade da IA — RiffLab 0.6.8

Na revisão de capas de cada música, o aplicativo consulta os catálogos com o título e o artista identificados pela IA quando a identificação está ativada, tem confiança suficiente e não marca esses campos como incertos. A tela informa exatamente qual artista e título foram usados e a origem. Cada música tem sua própria consulta, inclusive na preparação de várias músicas.

A IA recebe textos e pode se enganar: ela não escuta o áudio. Se o título/artista da busca da capa forem diferentes dos metadados que serão gravados no arquivo, aparece um aviso para conferir os dois. Edições feitas pelo usuário têm prioridade; uma possível troca de versão ao vivo/estúdio, remix, instrumental, karaokê ou acústico não é aplicada silenciosamente. Quando a IA falha, está desativada ou não tem dados confiáveis, o aplicativo informa que usa os dados disponíveis em vez de fingir que a IA identificou.

Os catálogos ainda podem não ter a imagem, estar indisponíveis ou fornecer uma identificação errada. As opções automáticas continuam restritas a lançamentos indicados como singles e precisam de revisão. A mudança não reabre nem altera MP3s antigos, nem modifica os parâmetros do yt-dlp ou os downloads já arrumados.

Atualização: aguarde o lote, faça backup de `rifflab.db` e `config.json`, feche o aplicativo e mescle o ZIP na instalação sem excluir configurações, banco, cookies, músicas, ferramentas ou `.venv`. As novas buscas acontecem ao preparar músicas; preparações já salvas mantêm sua escolha até serem novamente preparadas.

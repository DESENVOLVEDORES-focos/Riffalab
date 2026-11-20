# Correção da consulta de qualidade

A consulta de detalhes agora usa `yt-dlp --ignore-config -F --print-json --no-playlist`: ela solicita a lista de formatos e seus metadados sem escolher um formato ou baixar áudio. Antes a consulta usava `-J`, que pode falhar com “Requested format is not available” quando o seletor padrão não encontra formato baixável, inclusive quando existem apenas imagens. Listar não cria áudio onde não existe: se o yt-dlp só enxergar imagens, o RiffLab informa isso em vez de inventar qualidade.

A consulta não reutiliza cache antigo de formatos e uma falha anterior pode ser tentada novamente. Falhas não são automaticamente repetidas uma segunda vez pelo cartão. Avisos comuns do yt-dlp, inclusive sobre JavaScript e ausência de áudio, são interpretados e exibidos sem mostrar a saída integral, cookies ou URLs temporárias. Se o problema persistir, leia o motivo abaixo do resultado.

A instalação nova mantém suas próprias configurações e continua ignorando arquivos de configuração externos do yt-dlp. O `cookies.txt` usado é o escolhido no RiffLab ou o arquivo da raiz desta instalação. O `yt-dlp.exe` da pasta `ferramentas` tem prioridade; se não estiver disponível ou for inválido, o aplicativo ainda pode procurar uma instalação do sistema no PATH. Em Configurações é possível conferir o caminho usado. O FFmpeg e runtimes do sistema também podem ser usados; o app não copia dados da pasta antiga automaticamente.

O teste `TESTAR_YTDLP.bat` usa apenas `cookies.txt` na raiz do aplicativo, não o arquivo escolhido em Configurações, e por padrão testa o vídeo de exemplo. Os arquivos de diagnóstico podem conter links ou outras informações sensíveis: não os compartilhe sem revisar. Não envie cookies.

Testes realizados: 53 testes automatizados, testes originais e compilação; incluiu execução do yt-dlp real com arquivos simulados e servidor HTTP local, e interface Qt offscreen. Não foi possível testar o YouTube externo, sua conta/cookies ou o aplicativo no Windows. Não há garantia de formatos, bitrate, disponibilidade ou funcionamento de serviços externos. A alteração da consulta não cria formatos que o YouTube/yt-dlp não disponibilizem.

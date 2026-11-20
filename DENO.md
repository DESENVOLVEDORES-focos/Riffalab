# Deno no RiffLab

O Deno é um runtime JavaScript que versões recentes do yt-dlp podem utilizar na extração do YouTube. **Instalá-lo não garante que os formatos apareçam**: autenticação, limites de acesso, versões ou mudanças na plataforma também podem interferir.

Na primeira abertura, `INICIAR.bat` tenta baixar automaticamente o Deno oficial para `ferramentas\deno.exe`, sem alterar o PATH do Windows. O download tem aproximadamente 43 MB e requer internet. O instalador suporta Windows de 64 bits x86-64 e ARM64. Usa a versão oficial fixa 2.9.8 do GitHub e confere o SHA-256 do ZIP antes de copiar somente `deno.exe`. Caso já exista um `deno.exe` nessa pasta, ele é preservado. A versão pode ficar antiga com o tempo.

O RiffLab acrescenta `ferramentas` apenas ao PATH dos seus próprios processos de pesquisa, consultas e download. Assim, versões compatíveis do executável yt-dlp e da biblioteca Python conseguem encontrar o Deno local mesmo quando o yt-dlp está em outra pasta. O teste `TESTAR_YTDLP.bat` também procura nessa pasta. O RiffLab não substitui o yt-dlp: o usuário continua fornecendo o executável.

Em **Configurações → Ferramentas externas**, confira se Deno aparece como **ok** e qual versão/caminho foi detectado. O status confirma que o arquivo responde à verificação de versão; não confirma que o desafio JavaScript foi resolvido nem que o seu yt-dlp tem suporte a Deno. Use um yt-dlp recente e compatível.

Se o download falhar, o RiffLab abre mesmo assim. Para tentar novamente, feche o aplicativo e execute `INSTALAR_DENO.bat` (depois de rodar `INICIAR.bat` pelo menos uma vez para criar `.venv`). Também é possível obter o Deno da página oficial https://github.com/denoland/deno/releases e colocar `deno.exe` manualmente na pasta `ferramentas`; escolha o arquivo para a arquitetura do seu computador e confira a origem. Não é necessário copiar configurações antigas.

Os testes disponíveis executaram o yt-dlp real com um Deno simulado para comprovar sua descoberta pelo PATH; testaram também instalação com dados simulados e checksum inválido. **O download oficial, Deno real no Windows e a extração do YouTube não foram testados neste ambiente.** Se ainda não funcionar, informe o status do Deno e as mensagens dos quatro métodos no cartão. Não compartilhe cookies nem arquivos de diagnóstico sem remover informações sensíveis.

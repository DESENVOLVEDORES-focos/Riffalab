# Comparação de formatos: quatro métodos

Para cada resultado do yt-dlp exibido na pesquisa, o RiffLab consulta o **mesmo link** em segundo plano, sem iniciar o download de áudio:

1. Lista `-F` do executável `yt-dlp`.
2. JSON `-j` do mesmo executável.
3. `-F --print-json` do executável (tabela e JSON).
4. Biblioteca Python `yt-dlp`, em um processo separado.

O cartão mostra quantos formatos de áudio cada método encontrou, ou se ele falhou, não encontrou áudio ou está indisponível. Na lista de formatos aparecem os IDs; ao selecionar um formato, os nomes dos métodos que o identificaram aparecem no cartão. Resultados com o mesmo ID são cruzados, mas IDs diferentes não são descartados apenas por terem a mesma taxa ou codec. A tabela -F pode informar a coluna ABR arredondada; ela só é lida quando o cabeçalho e o alinhamento permitem identificá-la. Sem dados confiáveis, a taxa fica desconhecida. A identificação na tabela é conservadora e pode não reconhecer todos os formatos.

O programa exibe a pesquisa primeiro e consulta os formatos gradualmente. Resultados ocultos pelo filtro também são consultados quando exibidos. Se você escolher ordenar por qualidade, a lista é reordenada quando as consultas terminarem, sem desmarcar os itens. A análise de qualidade é uma estimativa; não garante melhor som, nem que o formato permanecerá acessível na hora do download. Caso a consulta posterior indique que um resultado já mostrado é ao vivo, o cartão recebe o aviso; ele não é movido automaticamente.

O `INICIAR.bat` tenta instalar a biblioteca opcional `yt-dlp[default]` no ambiente `.venv` desta instalação. Ela pode ter uma versão diferente do `yt-dlp.exe` em `ferramentas`. Se a instalação falhar, o aplicativo ainda inicia e os outros três métodos podem ser usados. O download continua usando o executável, não a biblioteca. Você precisa fornecer `yt-dlp.exe` e FFmpeg separadamente. Nesta versão, as configurações e o ambiente são próprios da pasta nova: não é preciso copiar configurações antigas. Copie apenas as ferramentas que desejar e selecione os cookies em Configurações, se necessários.

O comparador não grava áudio, mas realiza quatro consultas de rede por resultado. Elas podem demorar ou atingir limites de acesso; há limite de quatro subprocessos de consulta simultâneos. Um método pode falhar sem bloquear os outros. Quando cookies são configurados, cada processo usa uma cópia temporária, removida ao final; o original não é alterado por essas consultas. Cookies continuam sendo credenciais: não os compartilhe.

As quatro opções usam o yt-dlp e podem sofrer da mesma falha de autenticação, desafio JavaScript, bloqueio ou mudança do site. **Não há garantia de que algum método encontre áudio nem de que o download funcione.** A execução foi testada com yt-dlp e servidor HTTP locais e com a interface Qt fora do Windows; não houve teste do YouTube real nem do Windows. Para avaliar seu caso, confira o resultado de cada método no cartão e informe os nomes e mensagens exibidos, sem enviar cookies ou dados pessoais.

A partir desta versão, o RiffLab também tenta instalar o Deno em `ferramentas`. Veja **DENO.md**; a presença do Deno não comprova que a consulta funcionará.

Use **Comparar formatos** no cartão para ver os dados técnicos informados para cada ID. A ordem prioriza codecs sem perda e, em seguida, o bitrate informado; não prova qualidade sonora e não estabelece equivalência entre codecs. Consulte **COMPARAR-FORMATOS.md**.

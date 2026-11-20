@echo off
setlocal
cd /d "%~dp0"
set "PATH=%~dp0ferramentas;%PATH%"
title RiffLab - teste do yt-dlp

echo.
echo  TESTE DO YT-DLP
echo  ===============
echo  Este teste mostra, sem interface, o que o yt-dlp responde.
echo  Ele grava diagnosticos em teste_ytdlp.txt e detalhe_teste.txt.
echo  Nao compartilhe esses arquivos sem remover dados pessoais e links privados.
echo.

set "YTDLP="
if exist "ferramentas\yt-dlp.exe" set "YTDLP=ferramentas\yt-dlp.exe"
if not defined YTDLP goto procurar_no_path
goto achou

:procurar_no_path
for /f "delims=" %%i in ('where yt-dlp.exe 2^>nul') do if not defined YTDLP set "YTDLP=%%i"

:achou
if not defined YTDLP goto sem_ytdlp
echo  Usando: %YTDLP%
echo.

set "ALVO=%~1"
if "%ALVO%"=="" set "ALVO=https://www.youtube.com/watch?v=aqz-KE-bpKQ"

echo  [1/4] Versao do yt-dlp
"%YTDLP%" --version > teste_ytdlp.txt 2>&1
type teste_ytdlp.txt
echo.

echo  [2/4] cookies.txt
if exist "cookies.txt" echo         cookies.txt da pasta do app sera usado
if not exist "cookies.txt" echo         cookies.txt na pasta do app ausente: o teste vai sem cookies
echo         Arquivos escolhidos nas Configuracoes nao sao usados por este teste.
echo.

echo  [3/4] Formatos de audio do video de teste
echo         %ALVO%
if exist "cookies.txt" (
    "%YTDLP%" --ignore-config -F --no-playlist --no-color --cookies "cookies.txt" "%ALVO%" >> teste_ytdlp.txt 2>&1
) else (
    "%YTDLP%" --ignore-config -F --no-playlist --no-color "%ALVO%" >> teste_ytdlp.txt 2>&1
)
echo         resultado gravado em teste_ytdlp.txt
echo.

echo  [4/4] Leitura dos detalhes em JSON, igual ao app faz
if exist "cookies.txt" (
    "%YTDLP%" --ignore-config -F --print-json --no-playlist --no-color --retries 1 --cookies "cookies.txt" "%ALVO%" > detalhe_teste.txt 2>> teste_ytdlp.txt
) else (
    "%YTDLP%" --ignore-config -F --print-json --no-playlist --no-color --retries 1 "%ALVO%" > detalhe_teste.txt 2>> teste_ytdlp.txt
)
if errorlevel 1 goto falhou
echo.
echo  RESULTADO: o yt-dlp respondeu. Confira se a tabela contem audio.
echo  O arquivo detalhe_teste.txt inclui uma tabela e dados tecnicos do video.
echo  Pode conter URLs privadas: nao compartilhe sem revisar.
goto fim

:falhou
echo.
echo  RESULTADO: o yt-dlp NAO conseguiu ler esse video.
echo  A ultima mensagem de erro esta no fim de teste_ytdlp.txt:
echo.
powershell -NoProfile -Command "Get-Content teste_ytdlp.txt -Tail 8"
echo.
echo  Se aparecer  Sign in to confirm you're not a bot  ou  HTTP Error 429:
echo    - coloque um cookies.txt atualizado na pasta do app e marque
echo      ou selecione-o nas Configuracoes do aplicativo;
echo    - ou atualize o yt-dlp com:  ferramentas\yt-dlp.exe -U
echo  Se aparecer  Unsupported URL  ou  Video unavailable:
echo    - o link nao serve, teste outro video.
goto fim

:sem_ytdlp
echo  [ERRO] yt-dlp.exe nao encontrado.
echo         Baixe em:
echo         https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe
echo         e salve em ferramentas\yt-dlp.exe

:fim
echo.
pause
endlocal

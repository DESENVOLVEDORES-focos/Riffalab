@echo off
setlocal
chcp 65001 >nul 2>nul
cd /d "%~dp0"
title RiffLab - diagnostico

echo.
echo  ============================================================
echo    DIAGNOSTICO DO RIFFLAB
echo  ============================================================
echo.

echo  [pasta atual]
echo  %CD%
echo.

echo  [python no PATH]
where py 2>nul
where python 2>nul
py -3 --version 2>nul
python --version 2>nul
echo.

echo  [ambiente virtual]
if exist ".venv\Scripts\python.exe" goto tem_venv
echo  .venv NAO existe - rode o INICIAR.bat primeiro
goto deps

:tem_venv
.venv\Scripts\python.exe --version
echo.
echo  [pacotes instalados]
.venv\Scripts\python.exe -c "import PySide6; print('PySide6', PySide6.__version__)" 2>&1
.venv\Scripts\python.exe -c "import mutagen; print('mutagen', mutagen.version)" 2>&1

:deps
echo.
echo  [ferramentas]
if exist "ferramentas\ffmpeg.exe" echo  ferramentas\ffmpeg.exe  ... OK
if not exist "ferramentas\ffmpeg.exe" echo  ferramentas\ffmpeg.exe  ... AUSENTE
if exist "ferramentas\ffprobe.exe" echo  ferramentas\ffprobe.exe ... OK
if exist "ferramentas\yt-dlp.exe" echo  ferramentas\yt-dlp.exe  ... OK
where ffmpeg 2>nul
echo.

echo  [arquivos do app]
if exist "main.py" echo  main.py ............. OK
if not exist "main.py" echo  main.py ............. AUSENTE
if exist "app\config.py" echo  app\config.py ....... OK
if not exist "app\config.py" echo  app\config.py ....... AUSENTE
if exist "cookies.txt" echo  cookies.txt ......... presente
if not exist "cookies.txt" echo  cookies.txt ......... ausente - normal
if exist "credenciais\groq.dat" echo  chave da Groq ....... presente - conteudo nao e exibido
if not exist "credenciais\groq.dat" echo  chave da Groq ....... ausente - identificacao com IA desligada
if exist "credenciais\LEIA-ME.txt" echo  credenciais\ ........ pasta ok
if exist "api.txt" echo  api.txt ........... presente - chave lida da raiz (conteudo nao e exibido)
if not exist "api.txt" echo  api.txt ........... ausente - pode usar a interface ou GROQ_API_KEY
echo.

echo  [ultimas linhas do rifflab.log]
if exist "rifflab.log" goto mostra_log
echo  ainda nao existe log
goto fim_teste

:mostra_log
powershell -NoProfile -Command "Get-Content -Path 'rifflab.log' -Tail 15" 2>nul

:fim_teste
echo.
echo  ============================================================
echo   Antes de compartilhar, remova dados pessoais ou sensiveis.
echo  ============================================================
echo.
pause
endlocal

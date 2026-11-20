@echo off
setlocal
chcp 65001 >nul 2>nul
cd /d "%~dp0"
title RiffLab
mode con: cols=78 lines=32 >nul 2>nul

echo.
echo  ============================================================
echo    R I F F L A B      pesquisa . qualidade . metadados
echo  ============================================================
echo.

set "PYEXE=.venv\Scripts\python.exe"
set "PYCMD="

rem ---------- 1) usa o ambiente existente ou procura Python 3.10+ --------
if exist "%PYEXE%" goto instalar_deps
where py >nul 2>nul
if errorlevel 1 goto tentar_python
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if not errorlevel 1 set "PYCMD=py -3"
if defined PYCMD goto criar_venv

:tentar_python
where python >nul 2>nul
if errorlevel 1 goto sem_python
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if errorlevel 1 goto sem_python
set "PYCMD=python"

rem ---------- 2) ambiente virtual --------------------------------------
:criar_venv
if exist "%PYEXE%" goto instalar_deps
echo  [1/3] Criando o ambiente virtual .venv ...
%PYCMD% -m venv .venv
if errorlevel 1 goto erro_venv

rem ---------- 3) dependencias ------------------------------------------
:instalar_deps
"%PYEXE%" -c "import PySide6, mutagen" >nul 2>nul
if not errorlevel 1 goto verificar_biblioteca
echo  [2/3] Instalando dependencias: PySide6 e mutagen ...
echo        Isso acontece uma vez so, pode levar 1 ou 2 minutos.
"%PYEXE%" -m pip install --upgrade pip --quiet
"%PYEXE%" -m pip install -r requirements.txt
if errorlevel 1 goto erro_pip

:verificar_biblioteca
"%PYEXE%" -c "import yt_dlp, yt_dlp_ejs" >nul 2>nul
if not errorlevel 1 goto verificar_deno
echo  Instalando a biblioteca opcional de consulta de formatos...
"%PYEXE%" -m pip install "yt-dlp[default]"
if errorlevel 1 echo  [AVISO] Biblioteca opcional indisponivel. Os outros tres metodos continuam disponiveis.

rem ---------- Deno local: opcional para o yt-dlp -----------------------
:verificar_deno
if exist "ferramentas\deno.exe" goto avisos
echo.
echo  Instalando Deno oficial para o yt-dlp. Pode levar alguns minutos.
"%PYEXE%" app\instalar_deno.py
if errorlevel 1 echo  [AVISO] Deno nao instalado. O RiffLab vai abrir mesmo assim.

rem ---------- 4) avisos ------------------------------------------------
:avisos
echo  [3/3] Verificando ferramentas ...
if exist "ferramentas\ffmpeg.exe" goto checar_ytdlp
where ffmpeg >nul 2>nul
if not errorlevel 1 goto checar_ytdlp
echo  [AVISO] ffmpeg.exe nao encontrado na pasta ferramentas.
echo          Da para pesquisar e comparar, mas a conversao para MP3 nao.
echo          Baixe em https://www.gyan.dev/ffmpeg/builds/ e copie o
echo          ffmpeg.exe para a pasta ferramentas.
echo.

:checar_ytdlp
if exist "ferramentas\yt-dlp.exe" goto aviso_cookies
where yt-dlp >nul 2>nul
if not errorlevel 1 goto aviso_cookies
echo  [AVISO] yt-dlp.exe nao encontrado na pasta ferramentas.
echo          Ele e a fonte de pesquisa do RiffLab: sem ele a busca
echo          volta vazia. Baixe em:
echo          https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe
echo          e salve como ferramentas\yt-dlp.exe
echo.

:aviso_cookies
if exist "cookies.txt" goto executar
echo  [INFO] cookies.txt ausente: a pesquisa continua funcionando.
echo         Alguns videos do yt-dlp podem pedir cookies de idade ou regiao.
echo.

rem ---------- 5) abre o aplicativo -------------------------------------
:executar
echo  Abrindo o RiffLab...
echo.
"%PYEXE%" main.py %*
if errorlevel 1 goto erro_execucao
goto fim

rem ---------- erros ----------------------------------------------------
:sem_python
echo  [ERRO] Python 3.10 ou mais novo nao foi encontrado neste computador.
echo.
echo  Instale o Python 3.10 ou mais novo em:
echo      https://www.python.org/downloads/
echo  IMPORTANTE: marque a opcao "Add python.exe to PATH" durante a instalacao.
echo  Depois feche e abra este INICIAR.bat de novo.
echo.
goto fim

:erro_venv
echo.
echo  [ERRO] Nao foi possivel criar o ambiente virtual .venv
echo         Verifique se a pasta tem permissao de escrita e tente de novo.
echo.
goto fim

:erro_pip
echo.
echo  [ERRO] Falha ao instalar as dependencias PySide6 e mutagen.
echo         Verifique a conexao com a internet e tente novamente.
echo         Para ver o erro completo rode o DIAGNOSTICO.bat
echo.
goto fim

:erro_execucao
echo.
echo  [ERRO] O aplicativo encerrou com um erro.
echo         Detalhes no arquivo rifflab.log nesta mesma pasta.
echo         Para ver a mensagem na tela rode o DIAGNOSTICO.bat
echo.

:fim
echo.
pause
endlocal

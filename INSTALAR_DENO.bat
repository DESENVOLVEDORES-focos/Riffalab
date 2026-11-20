@echo off
setlocal
chcp 65001 >nul 2>nul
cd /d "%~dp0"
title RiffLab - instalar Deno
if not exist ".venv\Scripts\python.exe" goto sem_python
".venv\Scripts\python.exe" app\instalar_deno.py
if errorlevel 1 goto erro
echo.
echo Verifique Deno em Configuracoes - Ferramentas externas.
goto fim
:sem_python
echo Primeiro execute INICIAR.bat para criar o ambiente do RiffLab.
goto fim
:erro
echo O RiffLab ainda pode abrir. Confira sua internet ou instale manualmente.
:fim
echo.
pause
endlocal

@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PY="
py -c "import sys" >nul 2>nul && set "PY=py"
if not defined PY python -c "import sys" >nul 2>nul && set "PY=python"
if not defined PY (
  echo Python nao encontrado. Rode o INSTALAR.vbs primeiro.
  pause
  exit /b 1
)
if "%~1"=="" (
  echo Arraste um arquivo .f1rec.gz da pasta sessoes para cima deste arquivo.
  pause
  exit /b
)
for %%F in (%*) do %PY% relatorio.py "%%~F" --sobrescrever
pause

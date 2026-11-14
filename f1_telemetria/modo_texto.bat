@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Telemetria F1 26
set "PY="
py -c "import sys" >nul 2>nul && set "PY=py"
if not defined PY python -c "import sys" >nul 2>nul && set "PY=python"
if not defined PY (
  echo Python nao encontrado. Rode o INSTALAR.vbs primeiro.
  pause
  exit /b 1
)
%PY% gravar.py %*
if errorlevel 1 pause

@echo off
rem  Double-clique sur ce fichier pour ouvrir la veille consoles retro.
chcp 65001 >nul
cd /d "%~dp0"
title Veille consoles retro

if not exist ".venv\Scripts\python.exe" (
  echo.
  echo   Premiere ouverture : preparation de Python, patiente une minute...
  py -3 -m venv .venv 2>nul || python -m venv .venv
  if errorlevel 1 goto sanspython
)

fc /b requirements.txt .venv\requirements.installed >nul 2>&1
if errorlevel 1 (
  echo   Installation des composants necessaires...
  ".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt
  if errorlevel 1 goto erreur
  copy /y requirements.txt .venv\requirements.installed >nul
)

".venv\Scripts\python.exe" -m veille --menu
exit /b 0

:sanspython
echo.
echo   Python est introuvable. Installe-le depuis https://www.python.org/downloads/
echo   (coche "Add python.exe to PATH" pendant l'installation), puis relance.
pause
exit /b 1

:erreur
echo.
echo   L'installation a echoue. Verifie ta connexion internet puis relance.
pause
exit /b 1

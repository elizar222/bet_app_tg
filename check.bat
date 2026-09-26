@echo off
chcp 65001 >nul
title Hedge Terminal - проверка API
cd /d "%~dp0bot"
if not exist ".venv\Scripts\python.exe" (
  echo Сначала запустите start.bat - он установит всё нужное.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m app.check_apis
echo.
pause

@echo off
chcp 65001 >nul
title Hedge Terminal
cd /d "%~dp0bot"

rem --- Ищем Python 3.10+ ---
set "PY="
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1 && set "PY=py -3"
if not defined PY (
  python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1 && set "PY=python"
)
if not defined PY (
  echo Python не найден. Пробую установить Python 3.12...
  winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
  echo.
  echo Если установка прошла успешно, закройте это окно и запустите start.bat ещё раз.
  echo Если нет - скачайте Python с https://www.python.org/downloads/
  echo и при установке поставьте галочку "Add python.exe to PATH".
  pause
  exit /b 1
)

if not exist ".env" (
  echo Нет файла bot\.env с токеном бота. Скопируйте .env.example в .env и заполните.
  pause
  exit /b 1
)

rem --- Виртуальное окружение и библиотеки (первый запуск ~1-2 минуты) ---
if not exist ".venv\Scripts\python.exe" (
  echo Первый запуск: готовлю окружение...
  %PY% -m venv .venv || (echo Не удалось создать окружение & pause & exit /b 1)
)
".venv\Scripts\python.exe" -m pip install -q --disable-pip-version-check -r requirements.txt || (
  echo Не удалось установить библиотеки. Проверьте интернет.
  pause
  exit /b 1
)

echo.
echo Запускаю бота и мини-апп. Чтобы остановить - закройте окно или нажмите Ctrl+C.
echo.
".venv\Scripts\python.exe" run.py
echo.
echo Бот остановлен.
pause

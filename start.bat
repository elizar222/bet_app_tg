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

rem Библиотеки ставим только если их ещё нет или изменился requirements.txt
if exist ".venv\installed.txt" (
  fc /b requirements.txt ".venv\installed.txt" >nul 2>&1 && goto run
)

set "PIPOPT=-q --disable-pip-version-check --no-cache-dir --retries 10 --timeout 60"
echo Устанавливаю библиотеки...
if exist "wheels" (
  ".venv\Scripts\python.exe" -m pip install %PIPOPT% --no-index --find-links wheels -r requirements.txt && goto installed
)
".venv\Scripts\python.exe" -m pip install %PIPOPT% -r requirements.txt && goto installed
echo Связь с PyPI оборвалась, пробую ещё раз...
".venv\Scripts\python.exe" -m pip install %PIPOPT% -r requirements.txt && goto installed
echo Пробую зеркало PyPI...
".venv\Scripts\python.exe" -m pip install %PIPOPT% -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com -r requirements.txt && goto installed
".venv\Scripts\python.exe" -m pip install %PIPOPT% -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host pypi.tuna.tsinghua.edu.cn -r requirements.txt && goto installed
echo.
echo Не удалось скачать библиотеки: соединение обрывается.
echo Попробуйте включить или выключить VPN и запустить start.bat ещё раз.
pause
exit /b 1

:installed
copy /y requirements.txt ".venv\installed.txt" >nul

:run
rem Проверяем, что все библиотеки на месте; если нет — переустанавливаем
".venv\Scripts\python.exe" -c "import greenlet, sqlalchemy.ext.asyncio, aiosqlite, aiogram, fastapi, uvicorn, apscheduler, dotenv" >nul 2>&1 || (
  echo Доустанавливаю недостающие библиотеки...
  del ".venv\installed.txt" >nul 2>&1
  if exist "wheels" ".venv\Scripts\python.exe" -m pip install -q --disable-pip-version-check --no-index --find-links wheels -r requirements.txt
  ".venv\Scripts\python.exe" -m pip install -q --disable-pip-version-check --no-cache-dir -r requirements.txt
  copy /y requirements.txt ".venv\installed.txt" >nul
)
echo.
echo Запускаю бота и мини-апп. Чтобы остановить - закройте окно или нажмите Ctrl+C.
echo.
".venv\Scripts\python.exe" run.py
echo.
echo Бот остановлен.
pause

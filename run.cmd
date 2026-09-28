@echo off
chcp 866 >nul
rem Воспроизводимый запуск одним файлом: окружение, зависимости, фронтенд, сервер.
rem Файл хранится в кодировке CP866 - иначе cmd.exe рвёт русские строки.
rem Настройки - в .env (шаблон .env.example). Порт: run.cmd [порт], по умолчанию 8021.
setlocal
cd /d "%~dp0"

set "PORT=%~1"
if "%PORT%"=="" set "PORT=8021"
set "PYTHON=backend\.venv\Scripts\python.exe"

if not exist "%PYTHON%" (
    echo [1/4] Создаю окружение backend\.venv
    py -3.11 -m venv backend\.venv || goto :fail
    "%PYTHON%" -m pip install --quiet --upgrade pip || goto :fail
)
echo [2/4] Зависимости бэкенда
"%PYTHON%" -m pip install --quiet -r backend\requirements.txt || goto :fail
"%PYTHON%" -m pip install --quiet -e backend --no-deps || goto :fail

if not exist ".env" (
    echo [!] Файла .env нет - копирую .env.example; модель выключена, пока не заполните SD_LLM_*
    copy /y .env.example .env >nul
)

echo [3/4] Фронтенд
rem npm читает package.json из текущего каталога, а не из --prefix, поэтому
rem заходим в папку фронтенда, а не передаём её флагом.
pushd frontend
if not exist "node_modules" call npm install || goto :failpop
call npm run build || goto :failpop
popd

echo [4/4] Сервер: http://127.0.0.1:%PORT%/  (Ctrl+C - остановить)
"%PYTHON%" -m uvicorn sd.api:app --host 127.0.0.1 --port %PORT%
goto :eof

:failpop
popd

:fail
echo.
echo Запуск не удался. Нужны Python 3.11 (py -3.11), Node.js 18+ и доступ к PyPI/npm.
exit /b 1

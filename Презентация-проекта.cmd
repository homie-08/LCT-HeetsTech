@echo off
rem Собирает презентацию о самом проекте — его же движком.
rem Запуск: двойной щелчок либо "Презентация проекта.cmd" ИмяШаблона
chcp 65001 >nul
setlocal
cd /d "%~dp0"

set "TEMPLATE=%~1"
if "%TEMPLATE%"=="" set "TEMPLATE=IonBoardroomTheme"
set "PYTHON=backend\.venv\Scripts\python.exe"
set "DECK=data\out\%TEMPLATE%-pitch.pptx"

if not exist "%PYTHON%" (
    echo Не найдено окружение %PYTHON%
    echo Создайте его один раз:
    echo    py -3.11 -m venv backend\.venv
    echo    backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
    echo    backend\.venv\Scripts\python.exe -m pip install -e backend --no-deps
    goto :fail
)

if not exist "templates\deck\%TEMPLATE%.potx" (
    echo Шаблон "%TEMPLATE%" не найден. Доступные:
    for %%F in ("templates\deck\*.potx" "templates\deck\*.pptx") do echo    %%~nF
    echo.
    echo Свой шаблон положите в templates\deck и передайте имя без расширения:
    echo    "%~nx0" МойШаблон
    goto :fail
)

echo Шаблон:  %TEMPLATE%
echo Контент: data\content\pitch
echo.

"%PYTHON%" -m sd build "templates\deck\%TEMPLATE%.potx" data\content\pitch --out "%DECK%"

rem Ненулевой код возвращается и тогда, когда файл собран, но нормоконтроль
rem нашёл замечания. Судим по факту: есть файл — показываем.
if not exist "%DECK%" (
    echo.
    echo Собрать не удалось — файл не создан.
    goto :fail
)

echo.
echo Готово: %DECK%
start "" "%DECK%"
endlocal
exit /b 0

:fail
echo.
pause
endlocal
exit /b 1

@echo off
setlocal

set "PROJECT_DIR=%~dp0"
set "VENV_PYTHON=%PROJECT_DIR%.venv313\Scripts\python.exe"
set "MAIN_FILE=%PROJECT_DIR%main.py"

if not exist "%VENV_PYTHON%" (
    echo [BLAD] Nie znaleziono interpretera venv:
    echo %VENV_PYTHON%
    echo.
    echo Upewnij sie, ze folder .venv313 istnieje.
    pause
    exit /b 1
)

if not exist "%MAIN_FILE%" (
    echo [BLAD] Nie znaleziono pliku startowego:
    echo %MAIN_FILE%
    pause
    exit /b 1
)

pushd "%PROJECT_DIR%"
"%VENV_PYTHON%" "%MAIN_FILE%"
set "EXIT_CODE=%ERRORLEVEL%"
popd

if not "%EXIT_CODE%"=="0" (
    echo.
    echo Aplikacja zakonczona kodem %EXIT_CODE%.
    pause
)

exit /b %EXIT_CODE%

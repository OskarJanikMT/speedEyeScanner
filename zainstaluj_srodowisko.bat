@echo off
setlocal

set "PROJECT_DIR=%~dp0"
set "VENV_DIR=%PROJECT_DIR%.venv313"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"
set "REQUIREMENTS_FILE=%PROJECT_DIR%requirements.txt"

if not exist "%REQUIREMENTS_FILE%" (
    echo [BLAD] Nie znaleziono pliku requirements.txt:
    echo %REQUIREMENTS_FILE%
    pause
    exit /b 1
)

where py >nul 2>nul
if errorlevel 1 (
    echo [BLAD] Nie znaleziono launchera Python 'py'.
    echo Zainstaluj Python 3.13 i sproboj ponownie.
    pause
    exit /b 1
)

if not exist "%VENV_PYTHON%" (
    echo Tworzenie srodowiska virtualnego .venv313...
    py -3.13 -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo [BLAD] Nie udalo sie utworzyc srodowiska .venv313.
        pause
        exit /b 1
    )
) else (
    echo Srodowisko .venv313 juz istnieje.
)

echo Aktualizacja pip...
"%VENV_PYTHON%" -m pip install --upgrade pip
if errorlevel 1 (
    echo [BLAD] Nie udalo sie zaktualizowac pip.
    pause
    exit /b 1
)

echo Instalacja zaleznosci z requirements.txt...
"%VENV_PYTHON%" -m pip install -r "%REQUIREMENTS_FILE%"
if errorlevel 1 (
    echo [BLAD] Instalacja zaleznosci nie powiodla sie.
    pause
    exit /b 1
)

echo.
echo Instalacja zakonczona powodzeniem.
echo Aby uruchomic aplikacje, uzyj pliku:
echo %PROJECT_DIR%uruchom_speedeyescanner.bat
pause
exit /b 0

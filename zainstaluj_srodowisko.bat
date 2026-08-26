@echo off
setlocal

set "PROJECT_DIR=%~dp0"
set "VENV_DIR=%PROJECT_DIR%.venv313"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"
set "REQUIREMENTS_FILE=%PROJECT_DIR%requirements.txt"
set "PYTHON_VERSION=3.13"
set "PYTHON_WINGET_ID=Python.Python.3.13"
set "PYTORCH_INDEX_URL=https://download.pytorch.org/whl/cu128"

if not exist "%REQUIREMENTS_FILE%" (
    echo [BLAD] Nie znaleziono pliku requirements.txt:
    echo %REQUIREMENTS_FILE%
    pause
    exit /b 1
)

where py >nul 2>nul
if errorlevel 1 (
    goto install_python
)

py -%PYTHON_VERSION% --version >nul 2>nul
if errorlevel 1 (
    goto install_python
)

goto create_venv

:install_python
echo Nie znaleziono Python %PYTHON_VERSION%.
echo Proba instalacji przez winget...
where winget >nul 2>nul
if errorlevel 1 (
    echo [BLAD] Nie znaleziono winget.
    echo Zainstaluj recznie Python %PYTHON_VERSION% i uruchom ten plik ponownie.
    pause
    exit /b 1
)

winget install --id %PYTHON_WINGET_ID% -e --accept-package-agreements --accept-source-agreements
if errorlevel 1 (
    echo [BLAD] Instalacja Python %PYTHON_VERSION% przez winget nie powiodla sie.
    echo Zainstaluj recznie Python %PYTHON_VERSION% i uruchom ten plik ponownie.
    pause
    exit /b 1
)

where py >nul 2>nul
if errorlevel 1 (
    echo [BLAD] Python zostal zainstalowany, ale launcher 'py' nadal nie jest widoczny.
    echo Zamknij to okno i uruchom instalator ponownie.
    pause
    exit /b 1
)

py -%PYTHON_VERSION% --version >nul 2>nul
if errorlevel 1 (
    echo [BLAD] Python %PYTHON_VERSION% nadal nie jest widoczny dla launchera 'py'.
    echo Zamknij to okno i uruchom instalator ponownie.
    pause
    exit /b 1
)

:create_venv
if not exist "%VENV_PYTHON%" (
    echo Tworzenie srodowiska virtualnego .venv313...
    py -%PYTHON_VERSION% -m venv "%VENV_DIR%"
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

echo Instalacja PyTorch z oficjalnego repozytorium CUDA 12.8...
"%VENV_PYTHON%" -m pip install torch==2.11.0 torchvision==0.26.0 torchaudio==2.11.0 --index-url %PYTORCH_INDEX_URL%
if errorlevel 1 (
    echo [BLAD] Instalacja PyTorch nie powiodla sie.
    echo Sprawdz polaczenie z internetem i zgodnosc sterownikow GPU.
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

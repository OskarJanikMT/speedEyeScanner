@echo off
setlocal
set SCRIPT_DIR=%~dp0
set PATH=../bin;%PATH%
"%SCRIPT_DIR%\baumer_camera_update.exe" %*
exit /b %ERRORLEVEL%
endlocal

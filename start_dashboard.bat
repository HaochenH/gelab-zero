@echo off
setlocal
cd /d "%~dp0"
echo Starting gelab-zero Dashboard with gelab venv...

::: Activate gelab virtual environment
set "VENV_PATH=%~dp0gelab"
if exist "%VENV_PATH%\Scripts\activate.bat" (
    call "%VENV_PATH%\Scripts\activate.bat"
    echo [INFO] Activated virtual environment: %VENV_PATH%
) else (
    echo [ERROR] Could not find virtual environment at %VENV_PATH%
    pause
    exit /b 1
)

python server.py
if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Server failed to start. Please check the logs above.
    pause
)

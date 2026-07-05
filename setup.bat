@echo off
echo ============================================================
echo   Home Media Server - Setup
echo ============================================================
echo.

:: Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python is not installed or not in PATH.
    echo Please install Python 3.12+ from https://python.org
    pause
    exit /b 1
)

:: Create virtual environment
echo Creating virtual environment...
if not exist "venv" (
    python -m venv venv
)

:: Activate and install
echo Installing dependencies...
call venv\Scripts\activate.bat
pip install -r requirements.txt

echo.
echo ============================================================
echo   Setup complete!
echo   Run 'run.bat' to start the server.
echo ============================================================
pause

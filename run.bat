@echo off
echo ============================================================
echo   Home Media Server - Starting...
echo ============================================================
echo.

:: Activate virtual environment
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
) else (
    echo WARNING: Virtual environment not found.
    echo Run setup.bat first.
    pause
    exit /b 1
)

:: Start the dual server
python -m app.main

pause

@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel% equ 0 (
    py -3 -B run.py --smart-demo
) else (
    where python >nul 2>nul
    if errorlevel 1 (
        echo Python 3.10 or later is required. Install Python, then try again.
        pause
        exit /b 1
    )
    python -B run.py --smart-demo
)
pause

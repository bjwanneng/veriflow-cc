@echo off
echo.
echo   VeriFlow-CC Installer
echo   =====================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo   [ERROR] Python not found. Please install Python 3.10+
    pause
    exit /b 1
)

python "%~dp0install.py" %*

echo.
pause

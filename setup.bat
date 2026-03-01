@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
title Video Pipeline Setup

echo ========================================
echo   Video Pipeline - Windows Setup
echo ========================================
echo.

:: Step 0: Detect / Install Python
echo [0/6] Checking Python...
set "PYTHON_CMD="
set "PY_VER="

:: Try python first (skip Windows Store stub by actually running it)
python -c "import sys" >nul 2>nul
if not errorlevel 1 set "PYTHON_CMD=python"

:: Fallback: py launcher
if not defined PYTHON_CMD (
    py -c "import sys" >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=py"
)

if not defined PYTHON_CMD goto :python_not_found

:: Parse major.minor via sys directly (most reliable method)
for /f "tokens=1,2" %%a in ('%PYTHON_CMD% -c "import sys; print(sys.version_info.major, sys.version_info.minor)"') do (
    set "PY_MAJ=%%a"
    set "PY_MIN=%%b"
)

if "!PY_MAJ!"=="" goto :python_invalid
if !PY_MAJ! LSS 3 goto :python_invalid
if !PY_MAJ! EQU 3 if !PY_MIN! LSS 9 goto :python_invalid

for /f "tokens=2" %%v in ('%PYTHON_CMD% --version 2^>^&1') do set "PY_VER=%%v"
echo   Found Python !PY_VER! via "%PYTHON_CMD%"
echo.
goto :setup_start

:python_not_found
echo   Python not found. Attempting auto-install via winget...

where winget >nul 2>nul
if errorlevel 1 (
    echo   winget not available on this system.
    goto :manual_python
)

echo   Installing Python 3.12 (user scope)...
winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
if errorlevel 1 (
    echo   winget install failed.
    goto :manual_python
)

set "PYTHON_CMD="
where python >nul 2>nul
if not errorlevel 1 set "PYTHON_CMD=python"
if not defined PYTHON_CMD (
    where py >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=py"
)

if not defined PYTHON_CMD (
    echo.
    echo [ERROR] Python installed but current terminal cannot find it yet.
    echo Please close and reopen terminal, then run setup.bat again.
    goto :fail
)

for /f "tokens=2" %%v in ('%PYTHON_CMD% --version 2^>^&1') do set "PY_VER=%%v"
echo   Installed Python !PY_VER! via "%PYTHON_CMD%"
echo.
goto :setup_start

:python_invalid
echo.
echo [ERROR] Detected Python version !PY_VER! is too old. Python 3.9+ is required.
goto :manual_python

:manual_python
echo.
echo Please install Python 3.11+ manually, then rerun this script:
echo   https://www.python.org/downloads/
echo During install, enable: "Add python.exe to PATH".
goto :fail

:setup_start
:: Step 1: Create venv
echo [1/6] Creating virtual environment...
if exist venv\Scripts\python.exe (
    echo   Existing venv found, reusing it.
) else (
    %PYTHON_CMD% -m venv venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        goto :fail
    )
    echo   venv created.
)
echo.

set "VENV_PY=venv\Scripts\python.exe"
set "VENV_PIP=venv\Scripts\pip.exe"

:: Step 2: Upgrade pip
echo [2/6] Upgrading pip...
call %VENV_PIP% install --upgrade pip
if errorlevel 1 (
    echo [ERROR] Failed to upgrade pip.
    goto :fail
)
echo.

:: Step 3: Install PyTorch (CUDA)
echo [3/6] Installing PyTorch (CUDA 12.4 wheel)...
call %VENV_PIP% install torch --index-url https://download.pytorch.org/whl/cu124 --timeout 300
if errorlevel 1 (
    echo [ERROR] Failed to install PyTorch.
    goto :fail
)
echo.

:: Step 4: Install dependencies
echo [4/6] Installing dependencies from requirements.txt...
call %VENV_PIP% install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Failed to install requirements.
    goto :fail
)
echo.

:: Step 5: Install extras
echo [5/6] Installing extras...
call %VENV_PIP% install yt-dlp imageio-ffmpeg
if errorlevel 1 (
    echo [ERROR] Failed to install extras.
    goto :fail
)
echo.

:: Step 6: Bootstrap .env
echo [6/6] Preparing .env...
if exist .env (
    echo   .env already exists.
) else (
    if exist .env.example (
        copy /Y .env.example .env >nul
        echo   Created .env from .env.example
    ) else (
        echo   .env.example not found, skipping auto-create.
    )
)
echo.

:: Verify
echo ========================================
echo Verification
echo ========================================
call %VENV_PY% -c "import torch; print('CUDA:', torch.cuda.is_available()); print('Device:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'N/A')"
if errorlevel 1 echo [WARN] Torch/CUDA check failed.
call %VENV_PY% -c "import faster_whisper; print('faster-whisper: OK')"
if errorlevel 1 echo [WARN] faster-whisper import check failed.
call %VENV_PY% -c "import yt_dlp; print('yt-dlp: OK')"
if errorlevel 1 echo [WARN] yt-dlp import check failed.
echo.

echo ========================================
echo DONE!
echo.
echo Next:
echo 1. notepad .env
echo 2. ollama pull qwen2.5:7b-instruct-q4_K_M
echo 3. venv\Scripts\python.exe main.py "VIDEO_URL"
echo ========================================
goto :end

:fail
echo.
echo Setup did not complete.

:end
pause
exit /b

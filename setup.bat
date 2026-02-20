@echo off
chcp 65001 >nul
title Video Pipeline Setup

echo ========================================
echo   Video Pipeline - Windows Setup
echo ========================================
echo.

:: Step 1: Create venv FIRST
echo [1/5] Creating virtual environment...
if exist venv (
    echo   Removing old venv...
    rmdir /s /q venv
)
python -m venv venv
echo   Done
echo.

:: Step 2: Upgrade pip
echo [2/5] Upgrading pip...
call venv\Scripts\pip.exe install --upgrade pip
echo.

:: Step 3: Install PyTorch (CUDA) in venv
echo [3/5] Installing PyTorch with CUDA...
call venv\Scripts\pip.exe install torch --index-url https://download.pytorch.org/whl/nightly/cu124 --timeout 300
echo.

:: Step 4: Install all dependencies
echo [4/5] Installing dependencies...
call venv\Scripts\pip.exe install -r requirements.txt
echo.

:: Step 5: Install extras
echo [5/5] Installing extras...
call venv\Scripts\pip.exe install yt-dlp imageio-ffmpeg
echo.

:: Verify
echo.
echo ========================================
echo Verification
echo ========================================
call venv\Scripts\python.exe -c "import torch; print('CUDA:', torch.cuda.is_available()); print('Device:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'N/A')"
call venv\Scripts\python.exe -c "import faster_whisper; print('faster-whisper: OK')"
call venv\Scripts\python.exe -c "import yt_dlp; print('yt-dlp: OK')"
echo.

echo ========================================
echo DONE!
echo.
echo Next:
echo 1. copy .env.example .env
echo 2. notepad .env
echo 3. ollama pull qwen2.5:7b-instruct-q4_K_M
echo 4. python main.py "VIDEO_URL"
echo ========================================
pause

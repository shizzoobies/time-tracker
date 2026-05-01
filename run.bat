@echo off
title Time Tracker - Accounting Retainer
cd /d "%~dp0"

python --version >nul 2>&1
if errorlevel 1 (
    echo Python not found. Please install Python 3.9+ from python.org
    pause
    exit /b 1
)

python -c "import customtkinter" >nul 2>&1
if errorlevel 1 (
    echo Installing required packages...
    pip install -r requirements.txt
)

python main.py

@echo off

echo Building Ongaku...

REM Check if VLC is installed
where vlc >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: VLC is not installed on this system!
    echo Please install VLC first from https://www.videolan.org/vlc/
    echo.
    echo NOTE: Windows support is experimental - the application is primarily designed for Linux
    pause
    exit /b 1
)

echo VLC found - proceeding with build...
echo NOTE: Windows support is experimental

REM Create temporary virtual environment
echo Creating temporary virtual environment...
python -m venv .build_venv

REM Activate virtual environment
call .build_venv\Scripts\activate.bat

REM Upgrade pip
python -m pip install --upgrade pip

REM Install requirements
echo Installing requirements...
pip install pyinstaller yt-dlp python-vlc

REM Clean previous builds
rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul

REM Build the executable
echo Building executable...
pyinstaller ongaku.spec --clean

REM Check if build was successful
if exist "dist\ongaku.exe" (
    echo Build successful! Executable is in dist\
    
    REM Deactivate virtual environment
    call deactivate
    
    REM Clean up virtual environment
    rmdir /s /q .build_venv
    
    echo Done! Cleaned up temporary environment.
) else (
    echo Build failed!
    
    REM Deactivate virtual environment
    call deactivate
    
    REM Clean up virtual environment
    rmdir /s /q .build_venv
    
    exit /b 1
)

pause
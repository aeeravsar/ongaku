#!/bin/bash

# Build script for Ongaku

echo "Building Ongaku..."

# Check if VLC is installed
if ! command -v vlc &> /dev/null && ! [ -f "/usr/lib/vlc/libvlc.so" ] && ! [ -f "/usr/lib64/vlc/libvlc.so" ]; then
    echo "ERROR: VLC is not installed on this system!"
    echo "Please install VLC first:"
    echo "  Ubuntu/Debian: sudo apt install vlc"
    echo "  Fedora: sudo dnf install vlc"
    echo "  Arch: sudo pacman -S vlc"
    exit 1
fi

echo "VLC found - proceeding with build..."

# Create temporary virtual environment
echo "Creating temporary virtual environment..."
python3 -m venv .build_venv

# Activate virtual environment
source .build_venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install requirements
echo "Installing requirements..."
pip install pyinstaller yt-dlp python-vlc

# Clean previous builds
rm -rf build dist

# Build the executable
echo "Building executable..."
pyinstaller ongaku.spec --clean

# Check if build was successful
if [ -f "dist/ongaku" ] || [ -f "dist/ongaku.exe" ]; then
    echo "Build successful! Executable is in dist/"
    
    # Make it executable on Unix systems
    if [ -f "dist/ongaku" ]; then
        chmod +x dist/ongaku
    fi
else
    echo "Build failed!"
    deactivate
    rm -rf .build_venv
    exit 1
fi

# Deactivate and clean up virtual environment
deactivate
rm -rf .build_venv

echo "Done! Cleaned up temporary environment."
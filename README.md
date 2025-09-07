# Ongaku 🎵

Search for music, play it, save your favorites, create playlists, and enjoy. All from your terminal.

[![asciicast](https://asciinema.org/a/5KO9cwlQq36O2HLDGaCJ6f4iY.svg)](https://asciinema.org/a/5KO9cwlQq36O2HLDGaCJ6f4iY)

## Requirements

- VLC media player (must be installed on your system)
- Python 3.7+

## Installation

### System Requirements

First, install VLC:

```bash
# Ubuntu/Debian
sudo apt install vlc

# Fedora
sudo dnf install vlc

# Arch Linux
sudo pacman -S vlc

# macOS
brew install vlc

# Windows
# Download from https://www.videolan.org/vlc/
```

### Install Dependencies

```bash
pip install -r requirements.txt
```

## Usage

### Run from Source

```bash
python ongaku.py
```

### Build Standalone Executable

For Linux:
```bash
./build.sh
sudo cp dist/ongaku /usr/bin
```

For Windows (experimental):
```bash
build.bat
```

The build scripts will check for VLC installation and create a standalone executable in the `dist/` directory. Then you can copy the generated executable to your system path.


## License

[GPL-2.0](LICENSE)

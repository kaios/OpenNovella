#!/bin/sh
# Build the Windows .exe on Linux by running packaging/build_exe.py with Windows Python under Wine.
#
# One-time setup (Debian/Ubuntu):
#   sudo dpkg --add-architecture i386 && sudo apt update
#   sudo apt install wine wine64 wine32:i386 xvfb
#   export WINEPREFIX=~/.wine-opennovella-build
#   winecfg -v win10                       # Python 3.12 needs Windows 8.1 or newer
#   wine python-3.12.7-amd64.exe /quiet InstallAllUsers=0 TargetDir='C:\Python312' Include_test=0
#   # Wine 8 lacks propsys.VariantToString (crashes pip via _wmi) and CopyFile2 (crashes
#   # shutil.copy2), so turn both off for this build-only Python:
#   printf 'import sys, _winapi\nsys.modules["_wmi"] = None\ndel _winapi.CopyFile2\n' \
#       > "$WINEPREFIX/drive_c/Python312/Lib/site-packages/sitecustomize.py"
#   wine 'C:\Python312\python.exe' -m ensurepip
#   wine 'C:\Python312\python.exe' -m pip install pyinstaller pygame Pillow
set -e
ROOT=$(cd "$(dirname "$0")/.." && pwd)
export WINEPREFIX="${WINEPREFIX:-$HOME/.wine-opennovella-build}"
export WINEDEBUG="${WINEDEBUG:--all}"
PYTHON="${WINE_PYTHON:-C:\\Python312\\python.exe}"
# Output is piped: Wine can't give Python console handles when stdout is a file
xvfb-run -a wine "$PYTHON" "$(winepath -w "$ROOT/packaging/build_exe.py")" 2>&1 | cat

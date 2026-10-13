#!/usr/bin/env bash
# Build standalone executables for the hub and the student agent.
#
# Run this ON the target OS: PyInstaller does not cross-compile, so build the
# Windows .exe on Windows, the Linux binary on Linux, the macOS binary on macOS.
#
#   Windows:  packaging\build.bat     (see build.bat)
#   Linux/mac: bash packaging/build.sh
#
# Output lands in packaging/dist/.

set -euo pipefail
cd "$(dirname "$0")"

python -m pip install --upgrade pyinstaller >/dev/null

echo ">> Building hub (teacher console)…"
python -m PyInstaller hub.spec --distpath ./dist --workpath ./build --noconfirm

echo ">> Building student agent…"
python -m PyInstaller student.spec --distpath ./dist --workpath ./build --noconfirm

echo ""
echo "Done. Executables in packaging/dist/:"
ls -1 ./dist

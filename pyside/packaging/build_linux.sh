#!/usr/bin/env bash
# Сборка NIT-360 HMI под Linux: AppImage x86_64.
# Запускать на Linux из корня репозитория:  ./pyside/packaging/build_linux.sh
# Результат: dist/NIT-360-HMI-x86_64.AppImage
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

PY="${PYTHON:-python3}"
VENV="$ROOT/.venv-build"
TOOLS="$ROOT/pyside/packaging/tools"
APPDIR="$ROOT/build/AppDir"
OUT="$ROOT/dist/NIT-360-HMI-x86_64.AppImage"

if [ ! -x "$VENV/bin/python" ]; then
  echo "Создаю окружение сборки $VENV..."
  "$PY" -m venv "$VENV"
fi
"$VENV/bin/python" -m pip install --upgrade pip
"$VENV/bin/python" -m pip install -r pyside/requirements.txt -r pyside/requirements-build.txt

# AppImage требует каталог со всеми файлами, поэтому onedir, а не onefile
NIT360_BUILD_MODE=onedir "$VENV/bin/python" -m PyInstaller pyside/nit360.spec --noconfirm --clean

rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/share/applications" "$APPDIR/usr/share/icons/hicolor/256x256/apps"
cp -a dist/NIT-360-HMI/. "$APPDIR/usr/bin/"
cp pyside/assets/icon.png "$APPDIR/usr/share/icons/hicolor/256x256/apps/nit360-hmi.png"
cp pyside/assets/icon.png "$APPDIR/nit360-hmi.png"

cat > "$APPDIR/usr/share/applications/nit360-hmi.desktop" <<'DESKTOP'
[Desktop Entry]
Type=Application
Name=NIT-360 HMI
Comment=Пульт управления тепловизором NIT-360 (RS-422)
Exec=NIT-360-HMI
Icon=nit360-hmi
Categories=Utility;Engineering;
Terminal=false
DESKTOP
cp "$APPDIR/usr/share/applications/nit360-hmi.desktop" "$APPDIR/nit360-hmi.desktop"

cat > "$APPDIR/AppRun" <<'APPRUN'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/bin/NIT-360-HMI" "$@"
APPRUN
chmod +x "$APPDIR/AppRun"

# appimagetool: берём локальную копию, скачиваем только если её нет
TOOL="$TOOLS/appimagetool-x86_64.AppImage"
if [ ! -x "$TOOL" ]; then
  mkdir -p "$TOOLS"
  echo "Скачиваю appimagetool..."
  curl -fL -o "$TOOL" \
    https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage
  chmod +x "$TOOL"
fi

mkdir -p "$ROOT/dist"
# --appimage-extract-and-run: на машинах без FUSE запуск AppImage-инструмента иначе падает
ARCH=x86_64 "$TOOL" --appimage-extract-and-run "$APPDIR" "$OUT"
chmod +x "$OUT"
echo "Готово: $OUT ($(du -h "$OUT" | cut -f1))"

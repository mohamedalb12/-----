#!/bin/bash
# ------------------------------------------------------------------
# بناء تطبيق macOS (Disk Cleaner Pro.app) وملف تثبيت DMG
#
#   ./build_mac.sh
#
# النتيجة:  dist/Disk Cleaner Pro.app  و  dist/DiskCleanerPro-<version>-<arch>.dmg
# ------------------------------------------------------------------
set -euo pipefail
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"
APP_NAME="Disk Cleaner Pro"
VERSION="$("$PYTHON" -c 'import cleaner; print(cleaner.__version__)')"
ARCH="$(uname -m)"

echo "==> بيئة بناء معزولة"
"$PYTHON" -m venv .build-venv
# shellcheck disable=SC1091
source .build-venv/bin/activate
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt pyinstaller
python -c "import tkinter; print('Tk', tkinter.TkVersion)"

echo "==> بناء التطبيق (v$VERSION, $ARCH)"
rm -rf build "dist/$APP_NAME" "dist/$APP_NAME.app" dist/dmg
pyinstaller --noconfirm --clean DiskCleanerPro.spec

APP="dist/$APP_NAME.app"
echo "==> توقيع محلي (ad-hoc)"
codesign --force --deep --sign - "$APP"

echo "==> إنشاء ملف DMG"
mkdir -p dist/dmg
cp -R "$APP" dist/dmg/
ln -sf /Applications dist/dmg/Applications
DMG="dist/DiskCleanerPro-$VERSION-$ARCH.dmg"
rm -f "$DMG"
hdiutil create -volname "$APP_NAME" -srcfolder dist/dmg -ov -format UDZO "$DMG"
rm -rf dist/dmg

echo ""
echo "✅ تم: $APP"
echo "✅ تم: $DMG"

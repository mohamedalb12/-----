# -*- mode: python ; coding: utf-8 -*-
# إعدادات PyInstaller لبناء تطبيق macOS:  pyinstaller DiskCleanerPro.spec

import os
import sys

from PyInstaller.utils.hooks import collect_data_files

sys.path.insert(0, SPECPATH)
from cleaner import APP_NAME, BUNDLE_ID, __version__  # noqa: E402

ICON = os.path.join(SPECPATH, "assets", "icon.icns")

a = Analysis(
    ["main.py"],
    pathex=[SPECPATH],
    datas=collect_data_files("customtkinter") + [(os.path.join(SPECPATH, "assets"), "assets")],
    hiddenimports=["PIL._tkinter_finder", "send2trash", "psutil", "certifi"],
    excludes=["numpy", "matplotlib", "pytest", "IPython"],
    noarchive=False,
)
# ---------------------------------------------------------------------------
# حماية الكود: إن وُجد مجلد build_native (من tools/compile_native.py) نستبدل
# ملفات Python المقروءة بنسخها المُجمّعة إلى كود آلة (.so).
# التحليل يتم على الكود الأصلي أولاً حتى يكتشف PyInstaller كل المكتبات المطلوبة.
# ---------------------------------------------------------------------------
NATIVE_DIR = os.path.join(SPECPATH, "build_native")
if os.path.isdir(NATIVE_DIR):
    compiled = {}
    for root, _dirs, files in os.walk(NATIVE_DIR):
        for f in files:
            if f.endswith((".so", ".pyd")):
                rel = os.path.relpath(os.path.join(root, f), NATIVE_DIR)
                module = rel.split(".")[0].replace(os.sep, ".")
                compiled[module] = (rel, os.path.join(root, f))
    before = len(a.pure)
    a.pure = [entry for entry in a.pure if entry[0] not in compiled]
    a.binaries += [(rel, path, "BINARY") for rel, path in compiled.values()]
    leftover = [e[0] for e in a.pure if e[0].startswith("cleaner.") and not e[0].endswith("__init__")
                and e[0] not in ("cleaner.core", "cleaner.ui", "cleaner.ui.pages")]
    if leftover:
        raise SystemExit(f"وحدات غير محمية: {leftover}")
    print(f"🔒 حماية الكود: {len(compiled)} وحدة مُجمّعة (أُزيلت {before - len(a.pure)} وحدة مقروءة)")

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    console=False,
    argv_emulation=False,
    icon=ICON,
)

coll = COLLECT(exe, a.binaries, a.datas, name=APP_NAME)

app = BUNDLE(
    coll,
    name=f"{APP_NAME}.app",
    icon=ICON,
    bundle_identifier=BUNDLE_ID,
    version=__version__,
    info_plist={
        "CFBundleName": APP_NAME,
        "CFBundleDisplayName": APP_NAME,
        "CFBundleShortVersionString": __version__,
        "CFBundleVersion": __version__,
        "CFBundleDevelopmentRegion": "ar",
        "LSApplicationCategoryType": "public.app-category.utilities",
        "LSMinimumSystemVersion": "11.0",
        "NSHighResolutionCapable": True,
        "NSRequiresAquaSystemAppearance": False,   # دعم الوضع الداكن
        "NSAppleEventsUsageDescription":
            "يحتاج البرنامج إلى Finder لنقل الملفات إلى سلة المحذوفات وإفراغها.",
        "NSHumanReadableCopyright": "© Disk Cleaner Pro. All rights reserved.",
    },
)

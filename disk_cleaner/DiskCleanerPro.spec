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
    hiddenimports=["PIL._tkinter_finder", "send2trash"],
    excludes=["numpy", "matplotlib", "pytest", "IPython"],
    noarchive=False,
)
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
        "NSHumanReadableCopyright": "Open source — Disk Cleaner Pro",
    },
)

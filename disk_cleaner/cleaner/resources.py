"""تحديد مسار ملفات الموارد (الأيقونات) سواء شُغّل البرنامج من الكود أو كتطبيق .app."""

from __future__ import annotations

import os
import sys


def base_dir() -> str:
    if getattr(sys, "frozen", False):  # داخل التطبيق المبني بـ PyInstaller
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def asset_path(*parts: str) -> str:
    return os.path.join(base_dir(), "assets", *parts)

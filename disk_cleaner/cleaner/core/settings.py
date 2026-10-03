"""settings.py — حفظ إعدادات البرنامج وإحصاءاته في ملف JSON."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field, fields
from typing import List


def settings_dir() -> str:
    if sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    elif sys.platform.startswith("win"):
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
    else:
        base = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    return os.path.join(base, "Disk Cleaner Pro")


@dataclass
class Settings:
    appearance: str = "System"          # System / Dark / Light
    delete_mode: str = "trash"          # trash / permanent
    smart_large_mb: int = 500           # حد الملفات الكبيرة في الفحص الذكي
    duplicates_min_kb: int = 1024
    excluded: List[str] = field(default_factory=list)
    total_cleaned: int = 0              # إجمالي المساحة المحرَّرة منذ تثبيت البرنامج
    clean_count: int = 0
    last_smart_scan: float = 0.0

    @classmethod
    def path(cls) -> str:
        return os.path.join(settings_dir(), "settings.json")

    @classmethod
    def load(cls) -> "Settings":
        try:
            with open(cls.path(), encoding="utf-8") as f:
                data = json.load(f)
            known = {f.name for f in fields(cls)}
            return cls(**{k: v for k, v in data.items() if k in known})
        except Exception:
            return cls()

    def save(self) -> None:
        try:
            os.makedirs(settings_dir(), exist_ok=True)
            tmp = self.path() + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(asdict(self), f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path())
        except OSError:
            pass

"""
smart.py — الفحص الذكي (مثل Smart Care في CleanMyMac):
التنظيف + الحماية + السرعة في خطوة واحدة.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List

from .apps import find_orphans
from .jobs import JobContext
from .junk import scan_junk
from .large import scan_large_old
from .models import Category, FileItem


@dataclass
class SmartResult:
    junk: Dict[Category, List[FileItem]] = field(default_factory=dict)
    large: List[FileItem] = field(default_factory=list)
    orphans: List[FileItem] = field(default_factory=list)
    threats: List[FileItem] = field(default_factory=list)
    protection_issues: List[str] = field(default_factory=list)
    startup_running: int = 0
    startup_broken: int = 0
    mem_percent: float = 0.0

    @property
    def junk_size(self) -> int:
        return sum(i.size for items in self.junk.values() for i in items)

    @property
    def large_size(self) -> int:
        return sum(i.size for i in self.large)

    @property
    def orphans_size(self) -> int:
        return sum(i.size for i in self.orphans)

    def size_of(self, category: Category) -> int:
        return sum(i.size for i in self.junk.get(category, []))


def smart_scan(ctx: JobContext, large_min_bytes: int, extra_excludes=()) -> SmartResult:
    result = SmartResult()
    ctx.progress(0.0, "🧹 البحث عن المهملات...", force=True)
    result.junk = scan_junk(ctx.sub(0.0, 0.45), smart=True)
    if ctx.cancelled:
        return result
    result.large = scan_large_old(ctx.sub(0.45, 0.8), os.path.expanduser("~"), large_min_bytes,
                                  extra_excludes=extra_excludes)
    if ctx.cancelled:
        return result
    result.orphans = find_orphans(ctx.sub(0.8, 0.86))
    if ctx.cancelled:
        return result

    # الحماية
    from .security import protection_checks, scan_threats
    ctx.progress(0.86, "🛡 فحص التهديدات...", force=True)
    try:
        result.threats = [t for t in scan_threats(ctx.sub(0.86, 0.96))
                          if t.note.split("|", 1)[0] in ("high", "medium")]
        result.protection_issues = [c.title for c in protection_checks() if c.ok is False]
    except Exception:
        ctx.error()

    # السرعة
    ctx.progress(0.97, "🚀 فحص السرعة...", force=True)
    try:
        from .startup import list_launch_items
        items = list_launch_items()
        result.startup_running = sum(1 for i in items if i.enabled)
        result.startup_broken = sum(1 for i in items if not i.program_exists)
        from .monitor import quick_stats
        result.mem_percent = quick_stats()["mem_percent"]
    except Exception:
        ctx.error()
    ctx.progress(1.0, "", force=True)
    return result

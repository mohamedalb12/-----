"""smart.py — الفحص الذكي: مهملات النظام + الملفات الكبيرة + بقايا التطبيقات في خطوة واحدة."""

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
    result.junk = scan_junk(ctx.sub(0.0, 0.5))
    if ctx.cancelled:
        return result
    result.large = scan_large_old(ctx.sub(0.5, 0.9), os.path.expanduser("~"), large_min_bytes,
                                  extra_excludes=extra_excludes)
    if ctx.cancelled:
        return result
    result.orphans = find_orphans(ctx.sub(0.9, 1.0))
    return result

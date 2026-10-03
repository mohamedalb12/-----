"""
large.py — الملفات الكبيرة والقديمة.

يبحث عن الملفات التي يتجاوز حجمها حداً معيناً و/أو لم تُستخدم منذ مدة.
الحِزم (مثل مكتبة الصور أو ملفات .app) تُعامل كعنصر واحد ولا يتم الدخول إليها،
حتى لا يحذف المستخدم جزءاً من داخلها فيُفسدها.
"""

from __future__ import annotations

import os
import time
from typing import Iterable, List

from .jobs import NULL_CONTEXT, JobContext
from .models import Category, FileItem
from .walker import build_exclusions, count_files, walk_files

DAY = 86400


def scan_large_old(ctx: JobContext = NULL_CONTEXT, root: str = "~", min_size: int = 100_000_000,
                   min_age_days: int = 0, include_library: bool = False,
                   extra_excludes: Iterable[str] = ()) -> List[FileItem]:
    root = os.path.expanduser(root)
    excluded = build_exclusions(root, extra_excludes)
    opts = dict(excluded=excluded, packages_as_files=True, skip_home_library=not include_library)

    count_ctx = ctx.sub(0.0, 0.0)  # مرحلة العدّ: شريط تقدّم غير محدّد
    total = count_files(root, count_ctx, **opts)

    cutoff = time.time() - min_age_days * DAY if min_age_days else None
    results: List[FileItem] = []
    done = 0
    for entry in walk_files(root, ctx, **opts):
        done += 1
        if entry.size >= min_size:
            last_used = max(entry.mtime, entry.atime)
            if cutoff is None or last_used < cutoff:
                results.append(FileItem(entry.path, entry.size, Category.LARGE,
                                        entry.mtime, entry.atime, entry.is_dir))
        ctx.progress(done / max(total, done, 1),
                     f"جارٍ الفحص... {done:,} من {max(total, done):,} — وُجد {len(results):,}")
    results.sort(key=lambda i: i.size, reverse=True)
    return results

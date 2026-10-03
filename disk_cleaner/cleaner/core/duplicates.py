"""
duplicates.py — البحث عن الملفات المكررة.

الخوارزمية (سريعة ودقيقة):
1. تجميع الملفات حسب الحجم — الملفات مختلفة الحجم لا يمكن أن تكون متطابقة.
2. بصمة جزئية (أول وآخر 64KB) لاستبعاد معظم الملفات بسرعة.
3. بصمة كاملة (BLAKE2) للتأكد من التطابق التام بايت ببايت.
الروابط الصلبة (Hard links) لنفس الملف لا تُعد تكراراً.
"""

from __future__ import annotations

import hashlib
import os
from collections import defaultdict
from typing import Dict, Iterable, List, Tuple

from .jobs import NULL_CONTEXT, JobContext
from .models import Category, FileItem
from .walker import build_exclusions, walk_files

PARTIAL_BYTES = 64 * 1024
CHUNK = 1024 * 1024


def _partial_hash(path: str, size: int) -> bytes:
    h = hashlib.blake2b(digest_size=16)
    with open(path, "rb") as f:
        h.update(f.read(PARTIAL_BYTES))
        if size > 2 * PARTIAL_BYTES:
            f.seek(-PARTIAL_BYTES, os.SEEK_END)
            h.update(f.read(PARTIAL_BYTES))
    return h.digest()


def _full_hash(path: str, ctx: JobContext, on_bytes) -> bytes:
    h = hashlib.blake2b(digest_size=20)
    with open(path, "rb") as f:
        while True:
            if ctx.cancelled:
                raise InterruptedError
            chunk = f.read(CHUNK)
            if not chunk:
                break
            h.update(chunk)
            on_bytes(len(chunk))
    return h.digest()


def pick_original(group: List[FileItem]) -> FileItem:
    """النسخة التي نقترح الإبقاء عليها: الأقدم، ثم صاحبة المسار الأقصر."""
    return min(group, key=lambda i: (i.mtime, len(i.path), i.path))


def find_duplicates(ctx: JobContext = NULL_CONTEXT, root: str = "~", min_size: int = 1_000_000,
                    include_library: bool = False,
                    extra_excludes: Iterable[str] = ()) -> List[List[FileItem]]:
    root = os.path.expanduser(root)
    excluded = build_exclusions(root, extra_excludes)

    # ---- 1) التجميع حسب الحجم
    by_size: Dict[int, List[FileItem]] = defaultdict(list)
    seen_inodes = set()
    count = 0
    collect = ctx.sub(0.0, 0.25)
    for entry in walk_files(root, ctx, excluded, packages_as_files=False, skip_hidden_dirs=True,
                            skip_home_library=not include_library):
        count += 1
        if count % 300 == 0:
            collect.progress(None, f"جمع الملفات... {count:,} ملف")
        if entry.size < min_size or entry.name.startswith("."):
            continue
        try:
            st = os.stat(entry.path, follow_symlinks=False)
        except OSError:
            ctx.error()
            continue
        key = (st.st_dev, st.st_ino)
        if key in seen_inodes:      # رابط صلب لنفس الملف
            continue
        seen_inodes.add(key)
        by_size[entry.size].append(
            FileItem(entry.path, entry.size, Category.DUPLICATE, entry.mtime, entry.atime))
    if ctx.cancelled:
        return []

    candidates = [g for g in by_size.values() if len(g) > 1]

    # ---- 2) البصمة الجزئية
    partial_ctx = ctx.sub(0.25, 0.45)
    total = sum(len(g) for g in candidates)
    done = 0
    refined: List[List[FileItem]] = []
    for group in candidates:
        buckets: Dict[bytes, List[FileItem]] = defaultdict(list)
        for item in group:
            if ctx.cancelled:
                return []
            done += 1
            try:
                buckets[_partial_hash(item.path, item.size)].append(item)
            except OSError:
                ctx.error()
            partial_ctx.progress(done / max(total, 1), f"مقارنة سريعة... {done:,} من {total:,}")
        refined += [b for b in buckets.values() if len(b) > 1]

    # ---- 3) البصمة الكاملة
    full_ctx = ctx.sub(0.45, 1.0)
    total_bytes = sum(i.size for g in refined for i in g) or 1
    hashed = [0]

    def on_bytes(n: int):
        hashed[0] += n
        full_ctx.progress(hashed[0] / total_bytes, f"مقارنة دقيقة للمحتوى... {hashed[0] * 100 // total_bytes}%")

    groups: List[List[FileItem]] = []
    try:
        for group in refined:
            buckets: Dict[bytes, List[FileItem]] = defaultdict(list)
            for item in group:
                try:
                    buckets[_full_hash(item.path, ctx, on_bytes)].append(item)
                except OSError:
                    ctx.error()
            groups += [b for b in buckets.values() if len(b) > 1]
    except InterruptedError:
        return []

    # الأكثر هدراً للمساحة أولاً
    groups.sort(key=lambda g: g[0].size * (len(g) - 1), reverse=True)
    return groups


def wasted_bytes(groups: List[List[FileItem]]) -> int:
    return sum(g[0].size * (len(g) - 1) for g in groups)


def group_title(group: List[FileItem]) -> Tuple[str, int]:
    return group[0].name, group[0].size * (len(group) - 1)

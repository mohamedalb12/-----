"""
space.py — خريطة المساحة (Space Lens).

يبني شجرة أحجام لكل المجلدات تحت مسار معيّن مرة واحدة، فيصبح التنقّل
بين المجلدات فورياً بعد ذلك. يحسب أيضاً توزيع المساحة حسب نوع الملف.
"""

from __future__ import annotations

import heapq
import os
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from .jobs import NULL_CONTEXT, JobContext
from .models import human_size, kind_of
from .walker import build_exclusions

TOP_FILES = 40   # نحتفظ بأكبر N ملف في كل مجلد فقط لتوفير الذاكرة


class DirNode:
    __slots__ = ("path", "name", "size", "file_count", "dirs", "files", "parent", "depth", "error")

    def __init__(self, path: str, parent: Optional["DirNode"] = None):
        self.path = path
        self.name = os.path.basename(path.rstrip(os.sep)) or path
        self.size = 0
        self.file_count = 0
        self.dirs: List["DirNode"] = []
        self.files: List[Tuple[int, str]] = []    # (الحجم، الاسم) — كومة لأكبر الملفات
        self.parent = parent
        self.depth = 0 if parent is None else parent.depth + 1
        self.error = False

    def children(self) -> List[Tuple[str, str, int, bool]]:
        """(الاسم، المسار، الحجم، هل هو مجلد) مرتبة تنازلياً بالحجم."""
        rows = [(d.name, d.path, d.size, True) for d in self.dirs]
        rows += [(name, os.path.join(self.path, name), size, False) for size, name in self.files]
        rows.sort(key=lambda r: r[2], reverse=True)
        return rows

    def find_dir(self, path: str) -> Optional["DirNode"]:
        for d in self.dirs:
            if d.path == path:
                return d
        return None

    def remove_child(self, path: str, size: int) -> None:
        """تحديث الشجرة بعد حذف عنصر (بدون إعادة الفحص)."""
        self.dirs = [d for d in self.dirs if d.path != path]
        name = os.path.basename(path)
        self.files = [f for f in self.files if f[1] != name]
        heapq.heapify(self.files)
        node: Optional[DirNode] = self
        while node:
            node.size = max(0, node.size - size)
            node = node.parent


def _disk_usage(st: os.stat_result) -> int:
    # المساحة الفعلية على القرص (أدق للملفات المتفرقة Sparse مثل أقراص الأجهزة الافتراضية)
    blocks = getattr(st, "st_blocks", None)
    return min(st.st_size, blocks * 512) if blocks is not None else st.st_size


def build_space_tree(ctx: JobContext = NULL_CONTEXT, root: str = "~",
                     extra_excludes=()) -> Tuple[DirNode, Dict[str, int]]:
    root = os.path.abspath(os.path.expanduser(root))
    excluded = build_exclusions(root, extra_excludes)
    tree = DirNode(root)
    kinds: Dict[str, int] = defaultdict(int)
    top_total = None
    top_done = 0
    files_seen = 0

    stack: List[Tuple[DirNode, bool]] = [(tree, False)]
    while stack:
        if ctx.cancelled:
            break
        node, processed = stack.pop()
        if processed:  # كل المجلدات الفرعية انتهت — نحسب الحجم الكلي
            node.size += sum(d.size for d in node.dirs)
            node.file_count += sum(d.file_count for d in node.dirs)
            if node.depth == 1:
                top_done += 1
                ctx.progress(top_done / max(top_total or 1, 1),
                             f"تحليل {node.name}... ({files_seen:,} ملف، {human_size(tree_size_hint(tree))})")
            continue

        stack.append((node, True))
        try:
            with os.scandir(node.path) as it:
                entries = list(it)
        except OSError:
            node.error = True
            ctx.error()
            entries = []

        for entry in entries:
            try:
                if entry.is_dir(follow_symlinks=False):
                    if os.path.normcase(entry.path) in excluded:
                        continue
                    child = DirNode(entry.path, node)
                    node.dirs.append(child)
                    stack.append((child, False))
                elif entry.is_file(follow_symlinks=False):
                    size = _disk_usage(entry.stat(follow_symlinks=False))
                    node.size += size
                    node.file_count += 1
                    files_seen += 1
                    kinds[kind_of(entry.name)] += size
                    if len(node.files) < TOP_FILES:
                        heapq.heappush(node.files, (size, entry.name))
                    elif size > node.files[0][0]:
                        heapq.heapreplace(node.files, (size, entry.name))
            except OSError:
                ctx.error()

        if node is tree:
            top_total = len(node.dirs)
            if not top_total:
                ctx.progress(1.0, "", force=True)
    return tree, dict(kinds)


def tree_size_hint(tree: DirNode) -> int:
    """حجم تقريبي أثناء الفحص (للعرض فقط)."""
    return tree.size + sum(d.size for d in tree.dirs)

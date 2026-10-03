"""
junk.py — اكتشاف الملفات المهملة.

طريقتان:
1. scan_junk(): فحص ذكي وسريع لأماكن المهملات المعروفة في macOS
   (الكاش، السجلات، السلة، مخلفات Xcode، ...) مثل التطبيقات الاحترافية.
   الكاش يُجمَّع حسب التطبيق (مجلد لكل تطبيق) بدل آلاف الملفات الصغيرة.
2. scan_junk_folder(): فحص أي مجلد يختاره المستخدم ملفاً ملفاً
   والتعرّف على المهملات بقواعد عامة (الامتداد واسم المجلد).
"""

from __future__ import annotations

import glob
import os
import re
import sys
import tempfile
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from .jobs import NULL_CONTEXT, JobContext
from .models import Category, FileItem, JUNK_CATEGORIES, human_size, short_path
from .walker import HOME, build_exclusions, count_files, dir_size, walk_files

IS_MAC = sys.platform == "darwin"
DAY = 86400

INSTALLER_EXTS = frozenset(".dmg .pkg .mpkg .xip .exe .msi .deb .rpm .appimage".split())


def _installer(name: str, _mtime: float) -> bool:
    return os.path.splitext(name)[1].lower() in INSTALLER_EXTS


def _older_than(days: int) -> Callable[[str, float], bool]:
    def check(_name: str, mtime: float) -> bool:
        return time.time() - mtime > days * DAY
    return check


@dataclass
class JunkTarget:
    path: str
    category: Category
    # aggregate=True: كل عنصر مباشر داخل المجلد (مثل كاش تطبيق كامل) يظهر كعنصر واحد
    aggregate: bool = True
    # شرط اختياري على الملف (يُستخدم فقط مع aggregate=False)
    predicate: Optional[Callable[[str, float], bool]] = None
    # False = لا يُفحص في الفحص الذكي (مثلاً لأن macOS يطلب إذناً عند الوصول إليه)
    in_smart: bool = True


def junk_targets() -> List[JunkTarget]:
    """أماكن المهملات المعروفة حسب نظام التشغيل."""
    h = HOME
    j = os.path.join
    t: List[JunkTarget] = []
    if IS_MAC:
        t += [
            JunkTarget(j(h, "Library/Caches"), Category.CACHE),
            JunkTarget("/Library/Caches", Category.CACHE),
            JunkTarget(j(h, ".cache"), Category.CACHE),
            JunkTarget(j(h, "Library/Logs"), Category.LOGS),
            JunkTarget("/Library/Logs", Category.LOGS),
            JunkTarget("/private/var/log", Category.LOGS),
            JunkTarget(j(h, ".Trash"), Category.TRASH),
            JunkTarget(j(h, "Library/Developer/Xcode/DerivedData"), Category.DEV),
            JunkTarget(j(h, "Library/Developer/Xcode/iOS DeviceSupport"), Category.DEV),
            JunkTarget(j(h, "Library/Developer/Xcode/watchOS DeviceSupport"), Category.DEV),
            JunkTarget(j(h, "Library/Developer/CoreSimulator/Caches"), Category.DEV),
            JunkTarget(j(h, "Library/Application Support/MobileSync/Backup"), Category.IOS_BACKUP),
            JunkTarget(j(h, "Library/Containers/com.apple.mail/Data/Library/Mail Downloads"),
                       Category.MAIL, in_smart=False),
            JunkTarget(j(h, "Library/Mail Downloads"), Category.MAIL),
        ]
        # سلال المحذوفات في الأقراص الخارجية
        uid = str(os.getuid())
        for trashes in glob.glob("/Volumes/*/.Trashes"):
            t.append(JunkTarget(os.path.join(trashes, uid), Category.TRASH))
    else:
        t += [
            JunkTarget(j(h, ".cache"), Category.CACHE),
            JunkTarget(j(h, ".local/share/Trash/files"), Category.TRASH),
        ]
    t += [
        JunkTarget(tempfile.gettempdir(), Category.TEMP, aggregate=False, predicate=_older_than(2)),
        JunkTarget(j(h, ".npm/_cacache"), Category.DEV),
        JunkTarget(j(h, ".gradle/caches"), Category.DEV),
        JunkTarget(j(h, ".cargo/registry/cache"), Category.DEV),
        JunkTarget(j(h, "Downloads"), Category.INSTALLERS, aggregate=False, predicate=_installer),
    ]
    return t


def scan_junk(ctx: JobContext = NULL_CONTEXT, targets: Optional[List[JunkTarget]] = None,
              smart: bool = False) -> Dict[Category, List[FileItem]]:
    """الفحص الذكي لأماكن المهملات المعروفة."""
    targets = targets if targets is not None else junk_targets()
    targets = [tg for tg in targets if os.path.isdir(tg.path) and (tg.in_smart or not smart)]
    result: Dict[Category, List[FileItem]] = {c: [] for c in JUNK_CATEGORIES}
    seen = set()
    found_total = 0

    for index, target in enumerate(targets):
        if ctx.cancelled:
            break
        sub = ctx.sub(index / max(len(targets), 1), (index + 1) / max(len(targets), 1))
        label = f"فحص {short_path(target.path)}"
        sub.progress(0.0, label, force=True)

        if target.aggregate:
            try:
                with os.scandir(target.path) as it:
                    children = list(it)
            except OSError:
                ctx.error()
                continue
            for n, child in enumerate(children):
                if ctx.cancelled:
                    break
                if child.path in seen:
                    continue
                try:
                    st = child.stat(follow_symlinks=False)
                    is_dir = child.is_dir(follow_symlinks=False)
                except OSError:
                    ctx.error()
                    continue
                size = dir_size(child.path, ctx) if is_dir else st.st_size
                if size <= 0:
                    continue
                seen.add(child.path)
                result[target.category].append(
                    FileItem(child.path, size, target.category, st.st_mtime, st.st_atime, is_dir))
                found_total += size
                sub.progress((n + 1) / len(children), f"{label} — تم العثور على {human_size(found_total)}")
        else:
            excluded = build_exclusions(target.path)
            for entry in walk_files(target.path, ctx, excluded):
                if entry.path in seen:
                    continue
                if target.predicate and not target.predicate(entry.name, entry.mtime):
                    continue
                seen.add(entry.path)
                result[target.category].append(
                    FileItem(entry.path, entry.size, target.category, entry.mtime, entry.atime))
                found_total += entry.size
                sub.progress(None, f"{label} — تم العثور على {human_size(found_total)}")

    for items in result.values():
        items.sort(key=lambda i: i.size, reverse=True)
    return result


# --------------------------------------------------------------------------- #
#  قواعد عامة لفحص أي مجلد
# --------------------------------------------------------------------------- #

_TRASH_SEGMENTS = {".trash", ".trashes", "$recycle.bin", "recycler"}
_CACHE_SEGMENTS = {
    "caches", "cache", ".cache", "__pycache__", "cacheddata", "cachedextensions", "gpucache",
    "code cache", "shadercache", "grshadercache", "cachestorage", "dawncache", ".npm",
}
_LOG_SEGMENTS = {"logs", "log", "diagnosticreports"}
_DEV_SEGMENTS = {"deriveddata", "ios devicesupport", "watchos devicesupport", "crashreporter",
                 "crashpad", "shipit"}
_TEMP_PREFIXES = ("/tmp/", "/private/tmp/", "/private/var/tmp/", "/var/tmp/", "/private/var/folders/")
_TEMP_EXTS = {".tmp", ".temp", ".bak", ".old", ".swp", ".swo", ".dmp", ".crdownload", ".part",
              ".partial", ".chk", ".gid", ".~tmp", ".dump"}
_LOG_RE = re.compile(r"\.(log|log\.\d+|log\.gz|log\.bz2|trace|crash|ips|diag)$", re.I)
_SYSTEM_JUNK = {".ds_store", "thumbs.db", "desktop.ini", "ehthumbs.db"}


def classify_junk(path: str, name: str) -> Optional[Category]:
    lower_path = path.lower()
    lower_name = name.lower()
    segments = set(lower_path.replace("\\", "/").split("/")[:-1])
    ext = os.path.splitext(lower_name)[1]

    if segments & _TRASH_SEGMENTS or "/.local/share/trash/" in lower_path:
        return Category.TRASH
    if segments & _CACHE_SEGMENTS:
        return Category.CACHE
    if (ext in _TEMP_EXTS or lower_name.endswith("~") or lower_name.startswith("~$")
            or lower_path.startswith(_TEMP_PREFIXES)):
        return Category.TEMP
    if _LOG_RE.search(lower_name) or segments & _LOG_SEGMENTS:
        return Category.LOGS
    if segments & _DEV_SEGMENTS:
        return Category.DEV
    if ext in INSTALLER_EXTS and "downloads" in segments:
        return Category.INSTALLERS
    if lower_name in _SYSTEM_JUNK or lower_name.startswith("._"):
        return Category.SYSTEM_JUNK
    return None


def scan_junk_folder(ctx: JobContext, root: str,
                     extra_excludes=()) -> Dict[Category, List[FileItem]]:
    """فحص مجلد يختاره المستخدم ملفاً ملفاً."""
    excluded = build_exclusions(root, extra_excludes)
    total = count_files(root, ctx, excluded=excluded, packages_as_files=True)
    result: Dict[Category, List[FileItem]] = {c: [] for c in JUNK_CATEGORIES}
    done = 0
    for entry in walk_files(root, ctx, excluded, packages_as_files=True):
        done += 1
        cat = None if entry.is_dir else classify_junk(entry.path, entry.name)
        if cat:
            result[cat].append(FileItem(entry.path, entry.size, cat, entry.mtime, entry.atime))
        ctx.progress(done / max(total, done, 1), f"جارٍ الفحص... {done:,} من {max(total, done):,} ملف")
    for items in result.values():
        items.sort(key=lambda i: i.size, reverse=True)
    return result

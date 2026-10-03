"""
scanner.py
==========
منطق فحص القرص (Scan Logic) — مستقل تماماً عن الواجهة الرسومية.

يعمل الفاحص في خيط (Thread) منفصل ويُرسل نتائجه إلى الواجهة عبر طابور (Queue)،
وبذلك لا تتجمّد الواجهة أبداً أثناء الفحص.

مراحل الفحص:
    1. العدّ  : مرور سريع على شجرة المجلدات لعدّ الملفات (لحساب النسبة المئوية).
    2. الفحص  : قراءة حجم كل ملف وتصنيفه (كبير / مؤقت / كاش / سجلات / ...).

أي خطأ صلاحيات (PermissionError) أو ملف يختفي أثناء الفحص يتم تجاهله
وعدّه فقط، دون أن يتوقف البرنامج.
"""

from __future__ import annotations

import os
import queue
import re
import sys
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Iterator, List, Optional, Tuple

# --------------------------------------------------------------------------- #
#  التصنيفات
# --------------------------------------------------------------------------- #


class Category(str, Enum):
    """تصنيف الملف الذي عُثر عليه."""

    LARGE = "ملف كبير"
    TEMP = "ملف مؤقت"
    LOG = "ملف سجلات"
    CACHE = "كاش"
    TRASH = "سلة المحذوفات"
    LEFTOVER = "بقايا برامج"
    SYSTEM_JUNK = "ملفات نظام مهملة"

    @property
    def is_junk(self) -> bool:
        return self is not Category.LARGE


@dataclass
class FileItem:
    """ملف واحد ظهر في نتائج الفحص."""

    path: str
    name: str
    size: int
    category: Category
    file_type: str
    is_large: bool


@dataclass
class ScanOptions:
    root: str
    find_large: bool = True
    large_threshold_bytes: int = 100 * 1024 * 1024
    find_junk: bool = True


@dataclass
class ScanStats:
    files_scanned: int = 0
    dirs_scanned: int = 0
    errors: int = 0
    elapsed: float = 0.0
    cancelled: bool = False


# --------------------------------------------------------------------------- #
#  قواعد التعرّف على الملفات المهملة
# --------------------------------------------------------------------------- #

# مجلدات سلة المحذوفات (ماك / ويندوز / لينكس)
_TRASH_SEGMENTS = {".trash", ".trashes", "$recycle.bin", "recycler"}

# أسماء مجلدات الكاش الشائعة (مقارنة بأحرف صغيرة)
_CACHE_SEGMENTS = {
    "caches",          # ~/Library/Caches  و /Library/Caches
    "cache",
    ".cache",
    "__pycache__",
    "cacheddata",
    "cachedextensions",
    "gpucache",
    "code cache",
    "shadercache",
    "grshadercache",
    "cachestorage",
    "dawncache",
    ".npm",            # كاش npm
}

# مجلدات السجلات
_LOG_SEGMENTS = {"logs", "log", "diagnosticreports"}

# مجلدات تُعدّ "بقايا برامج" (مخلفات التطوير والتحديثات والأعطال)
_LEFTOVER_SEGMENTS = {
    "deriveddata",          # Xcode
    "ios devicesupport",    # Xcode
    "watchos devicesupport",
    "crashreporter",
    "crashpad",
    "shipit",               # بقايا تحديثات تطبيقات Electron
}

# مجلدات مؤقتة على مستوى النظام
_TEMP_PATH_PREFIXES = tuple(
    p.lower()
    for p in (
        "/tmp/",
        "/private/tmp/",
        "/private/var/tmp/",
        "/var/tmp/",
        "/private/var/folders/",   # مجلد المؤقتات الخاص بكل مستخدم في ماك
    )
)

_TEMP_EXTENSIONS = {
    ".tmp", ".temp", ".bak", ".old", ".swp", ".swo", ".dmp",
    ".crdownload", ".part", ".partial", ".chk", ".gid", ".~tmp", ".dump",
}

_LOG_RE = re.compile(r"\.(log|log\.\d+|log\.gz|log\.bz2|trace|crash|ips|diag)$", re.I)

_SYSTEM_JUNK_NAMES = {".ds_store", "thumbs.db", "desktop.ini", "ehthumbs.db"}

# ملفات التثبيت المنسية في مجلد التنزيلات
_INSTALLER_EXTENSIONS = {".dmg", ".pkg", ".mpkg", ".exe", ".msi", ".deb", ".rpm", ".appimage"}


def classify_junk(path: str, name: str) -> Optional[Category]:
    """
    يُرجع تصنيف الملف إن كان من الملفات المؤقتة/المهملة، وإلا None.
    """
    lower_path = path.lower()
    lower_name = name.lower()
    # أجزاء المسار (أسماء المجلدات الأب فقط)
    segments = set(lower_path.replace("\\", "/").split("/")[:-1])
    _, ext = os.path.splitext(lower_name)

    if segments & _TRASH_SEGMENTS or "/.local/share/trash/" in lower_path:
        return Category.TRASH

    if segments & _CACHE_SEGMENTS:
        return Category.CACHE

    if (
        ext in _TEMP_EXTENSIONS
        or lower_name.endswith("~")
        or lower_name.startswith("~$")          # ملفات أوفيس المؤقتة
        or lower_path.startswith(_TEMP_PATH_PREFIXES)
    ):
        return Category.TEMP

    if _LOG_RE.search(lower_name) or segments & _LOG_SEGMENTS:
        return Category.LOG

    if segments & _LEFTOVER_SEGMENTS:
        return Category.LEFTOVER
    if ext in _INSTALLER_EXTENSIONS and "downloads" in segments:
        return Category.LEFTOVER

    if lower_name in _SYSTEM_JUNK_NAMES or lower_name.startswith("._"):
        return Category.SYSTEM_JUNK

    return None


# --------------------------------------------------------------------------- #
#  وصف نوع الملف حسب الامتداد
# --------------------------------------------------------------------------- #

_TYPE_GROUPS = {
    "فيديو": {".mp4", ".mov", ".mkv", ".avi", ".wmv", ".m4v", ".webm", ".flv", ".mpg", ".mpeg"},
    "صوت": {".mp3", ".wav", ".aac", ".flac", ".m4a", ".ogg", ".aiff", ".wma"},
    "صورة": {".jpg", ".jpeg", ".png", ".gif", ".heic", ".tiff", ".bmp", ".webp", ".raw", ".cr2", ".nef", ".psd"},
    "أرشيف مضغوط": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".tgz"},
    "صورة قرص / مثبّت": {".dmg", ".iso", ".pkg", ".mpkg", ".img", ".exe", ".msi", ".deb", ".rpm", ".appimage", ".vmdk", ".vdi", ".qcow2"},
    "مستند": {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".pages", ".numbers", ".key", ".txt", ".rtf", ".epub"},
    "قاعدة بيانات": {".db", ".sqlite", ".sqlite3", ".sql"},
    "كود / بيانات": {".json", ".xml", ".csv", ".py", ".js", ".ts", ".html", ".css", ".java", ".c", ".cpp", ".swift"},
}

_EXT_TO_TYPE = {ext: group for group, exts in _TYPE_GROUPS.items() for ext in exts}


def describe_type(name: str) -> str:
    """وصف مقروء لنوع الملف، مثل: 'فيديو (.mp4)'."""
    _, ext = os.path.splitext(name)
    if not ext:
        return "ملف بدون امتداد"
    group = _EXT_TO_TYPE.get(ext.lower())
    return f"{group} ({ext.lower()})" if group else f"ملف {ext.lower()}"


# --------------------------------------------------------------------------- #
#  مجلدات يتم تخطّيها عند فحص القرص بالكامل
# --------------------------------------------------------------------------- #

if sys.platform == "darwin":
    _EXCLUDED_DIRS = (
        "/System",                    # نظام macOS محمي (SIP) ولا يمكن حذف شيء منه
        "/System/Volumes",            # روابط تؤدي لتكرار نفس الملفات
        "/Volumes",                   # الأقراص الخارجية الأخرى
        "/dev",
        "/private/var/vm",            # ملفات الذاكرة الافتراضية (swap)
        "/.vol",
        "/.Spotlight-V100",
        "/.fseventsd",
        "/.DocumentRevisions-V100",
        "/.MobileBackups",
        "/net",
        "/home",
        "/cores",
    )
elif sys.platform.startswith("win"):
    _EXCLUDED_DIRS = ("C:\\Windows\\WinSxS", "C:\\System Volume Information")
else:
    _EXCLUDED_DIRS = ("/proc", "/sys", "/dev", "/run", "/snap", "/mnt", "/media")


def _build_exclusions(root: str) -> set:
    """
    يُرجع المجلدات المستبعدة، مع إبقاء أي مجلد اختاره المستخدم صراحةً
    (مثلاً لو اختار /Volumes/USB فلن نستبعد /Volumes).
    """
    root_norm = os.path.normcase(os.path.abspath(root))
    excluded = set()
    for d in _EXCLUDED_DIRS:
        d_norm = os.path.normcase(d)
        if root_norm == d_norm or root_norm.startswith(d_norm.rstrip(os.sep) + os.sep):
            continue
        excluded.add(d_norm)
    return excluded


# --------------------------------------------------------------------------- #
#  الفاحص (يعمل في الخلفية)
# --------------------------------------------------------------------------- #

# أنواع الرسائل المرسلة إلى الواجهة عبر الطابور:
#   ("status",   نص)
#   ("counting", عدد_الملفات_حتى_الآن)
#   ("progress", نسبة 0..1, عدد_المفحوص, الإجمالي)
#   ("items",    [FileItem, ...])
#   ("finished", ScanStats)
Message = Tuple


class Scanner(threading.Thread):
    """خيط فحص يعمل في الخلفية ويمكن إيقافه في أي لحظة."""

    BATCH_SIZE = 200          # عدد النتائج المرسلة في كل دفعة
    UPDATE_INTERVAL = 0.1     # أقل فاصل زمني بين تحديثات شريط التقدم (ثانية)

    def __init__(self, options: ScanOptions, out_queue: "queue.Queue[Message]"):
        super().__init__(daemon=True)
        self.options = options
        self.queue = out_queue
        self._cancel = threading.Event()
        self.stats = ScanStats()
        self._excluded = _build_exclusions(options.root)

    # ---------------------------------------------------------------- API
    def cancel(self) -> None:
        """طلب إيقاف الفحص (يتوقف الخيط عند أقرب نقطة آمنة)."""
        self._cancel.set()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    # ---------------------------------------------------------- التنفيذ
    def run(self) -> None:
        start = time.monotonic()
        try:
            total = self._count_files()
            if not self.cancelled:
                self._scan(total)
        except Exception as exc:  # حماية أخيرة: لا نسمح لأي خطأ غير متوقع بإسقاط البرنامج
            self.queue.put(("status", f"حدث خطأ غير متوقع: {exc}"))
        finally:
            self.stats.elapsed = time.monotonic() - start
            self.stats.cancelled = self.cancelled
            self.queue.put(("finished", self.stats))

    def _walk_files(self, count_errors: bool) -> Iterator[os.DirEntry]:
        """
        مرور تكراري (بدون Recursion لتجنّب تجاوز حد العمق) على كل الملفات.
        - لا يتبع الروابط الرمزية (Symlinks) لتجنّب الحلقات اللانهائية.
        - يتجاهل أخطاء الصلاحيات ويعدّها.
        """
        stack: List[str] = [self.options.root]
        while stack:
            if self.cancelled:
                return
            current = stack.pop()
            try:
                with os.scandir(current) as it:
                    entries = list(it)
            except (PermissionError, FileNotFoundError, NotADirectoryError, OSError):
                if count_errors:
                    self.stats.errors += 1
                continue

            if count_errors:
                self.stats.dirs_scanned += 1

            for entry in entries:
                try:
                    if entry.is_dir(follow_symlinks=False):
                        if os.path.normcase(entry.path) not in self._excluded:
                            stack.append(entry.path)
                    elif entry.is_file(follow_symlinks=False):
                        yield entry
                except OSError:
                    if count_errors:
                        self.stats.errors += 1

    def _count_files(self) -> int:
        """المرحلة 1: عدّ الملفات لحساب النسبة المئوية لاحقاً."""
        self.queue.put(("status", "جارٍ حصر الملفات..."))
        count = 0
        last = 0.0
        for _ in self._walk_files(count_errors=False):
            count += 1
            now = time.monotonic()
            if now - last >= self.UPDATE_INTERVAL:
                self.queue.put(("counting", count))
                last = now
        self.queue.put(("counting", count))
        return count

    def _scan(self, total: int) -> None:
        """المرحلة 2: قراءة الأحجام وتصنيف الملفات."""
        opts = self.options
        self.queue.put(("status", "جارٍ فحص الملفات..."))
        batch: List[FileItem] = []
        last = 0.0

        for entry in self._walk_files(count_errors=True):
            self.stats.files_scanned += 1
            try:
                size = entry.stat(follow_symlinks=False).st_size
            except OSError:
                self.stats.errors += 1
                continue

            is_large = opts.find_large and size >= opts.large_threshold_bytes
            junk = classify_junk(entry.path, entry.name) if opts.find_junk else None

            if is_large or junk:
                batch.append(
                    FileItem(
                        path=entry.path,
                        name=entry.name,
                        size=size,
                        category=junk or Category.LARGE,
                        file_type=describe_type(entry.name),
                        is_large=is_large,
                    )
                )
                if len(batch) >= self.BATCH_SIZE:
                    self.queue.put(("items", batch))
                    batch = []

            now = time.monotonic()
            if now - last >= self.UPDATE_INTERVAL:
                done = self.stats.files_scanned
                # قد تُنشأ ملفات جديدة بين المرحلتين، لذلك نضمن ألا تتجاوز النسبة 100%
                fraction = min(done / total, 0.999) if total else 0.0
                self.queue.put(("progress", fraction, done, max(total, done)))
                last = now

        if batch:
            self.queue.put(("items", batch))
        if not self.cancelled:
            done = self.stats.files_scanned
            self.queue.put(("progress", 1.0, done, max(total, done)))


# --------------------------------------------------------------------------- #
#  أدوات مساعدة
# --------------------------------------------------------------------------- #


def human_size(num_bytes: float) -> str:
    """تحويل الحجم إلى صيغة مقروءة: KB / MB / GB / TB."""
    for unit in ("B", "KB", "MB", "GB"):
        if abs(num_bytes) < 1024:
            return f"{num_bytes:.0f} {unit}" if unit == "B" else f"{num_bytes:.2f} {unit}"
        num_bytes /= 1024
    return f"{num_bytes:.2f} TB"

"""
walker.py — المرور على شجرة الملفات بأمان.

- مرور تكراري (بدون Recursion) فلا يتجاوز حد العمق مهما تعمّقت المجلدات.
- لا يتبع الروابط الرمزية، فلا حلقات لا نهائية ولا تكرار في العدّ.
- أخطاء الصلاحيات تُعدّ وتُتجاهل ولا توقف الفحص.
- الحِزم (مثل .app و .photoslibrary) يمكن معاملتها كعنصر واحد بدل الدخول إليها.
"""

from __future__ import annotations

import os
import stat
import sys
from typing import Iterable, Iterator, NamedTuple, Optional, Set

from .jobs import NULL_CONTEXT, JobContext

HOME = os.path.expanduser("~")
IS_MAC = sys.platform == "darwin"

# مجلدات تظهر في Finder كملف واحد — حذف شيء بداخلها قد يُفسدها
PACKAGE_EXTS = frozenset(
    ".app .photoslibrary .musiclibrary .tvlibrary .fcpbundle .imovielibrary .logicx .band "
    ".xcarchive .bundle .framework .plugin .kext .appex .prefpane .qlgenerator .mdimporter "
    ".sparsebundle .rtfd .pages .numbers .key .docarch".split()
)

if IS_MAC:
    SYSTEM_EXCLUDES = (
        "/System", "/Volumes", "/dev", "/private/var/vm", "/.vol", "/.Spotlight-V100",
        "/.fseventsd", "/.DocumentRevisions-V100", "/.MobileBackups", "/net", "/home", "/cores",
        "/private/var/db",
    )
elif sys.platform.startswith("win"):
    SYSTEM_EXCLUDES = ("C:\\Windows", "C:\\System Volume Information", "C:\\$Recycle.Bin")
else:
    SYSTEM_EXCLUDES = ("/proc", "/sys", "/dev", "/run", "/snap", "/mnt", "/media", "/var/lib/docker")


class FileEntry(NamedTuple):
    path: str
    name: str
    size: int
    mtime: float
    atime: float
    is_dir: bool   # True للحِزم المعامَلة كعنصر واحد


def is_package(name: str) -> bool:
    return os.path.splitext(name)[1].lower() in PACKAGE_EXTS


def build_exclusions(root: str, extra: Iterable[str] = ()) -> Set[str]:
    """
    المجلدات المستبعدة من الفحص، مع إبقاء أي مسار اختاره المستخدم صراحةً
    (مثلاً لو اختار /Volumes/USB فلن نستبعد /Volumes).
    """
    root_n = os.path.normcase(os.path.abspath(root))
    result = set()
    for d in list(SYSTEM_EXCLUDES) + [os.path.expanduser(p) for p in extra]:
        d_n = os.path.normcase(os.path.abspath(d))
        if root_n == d_n or root_n.startswith(d_n.rstrip(os.sep) + os.sep):
            continue
        result.add(d_n)
    return result


def dir_size(path: str, ctx: JobContext = NULL_CONTEXT) -> int:
    """الحجم الكلي لمجلد (أو ملف)."""
    try:
        st = os.lstat(path)
    except OSError:
        ctx.error()
        return 0
    if not stat.S_ISDIR(st.st_mode):
        return st.st_size
    total = 0
    stack = [path]
    while stack:
        if ctx.cancelled:
            break
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                for entry in it:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
                        else:
                            total += entry.stat(follow_symlinks=False).st_size
                    except OSError:
                        ctx.error()
        except OSError:
            ctx.error()
    return total


def walk_files(
    root: str,
    ctx: JobContext = NULL_CONTEXT,
    excluded: Optional[Set[str]] = None,
    with_stat: bool = True,
    packages_as_files: bool = False,
    skip_hidden_dirs: bool = False,
    skip_home_library: bool = False,
) -> Iterator[FileEntry]:
    """يُرجع كل الملفات تحت root كـ FileEntry."""
    excluded = excluded if excluded is not None else build_exclusions(root)
    home_lib = os.path.normcase(os.path.join(HOME, "Library"))
    root_is_package = is_package(os.path.basename(root.rstrip(os.sep)))
    stack = [root]
    while stack:
        if ctx.cancelled:
            return
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                entries = list(it)
        except OSError:
            ctx.error()
            continue

        for entry in entries:
            try:
                if entry.is_dir(follow_symlinks=False):
                    norm = os.path.normcase(entry.path)
                    if norm in excluded:
                        continue
                    if skip_home_library and norm == home_lib:
                        continue
                    if skip_hidden_dirs and entry.name.startswith("."):
                        continue
                    if packages_as_files and not root_is_package and is_package(entry.name):
                        if with_stat:
                            st = entry.stat(follow_symlinks=False)
                            yield FileEntry(entry.path, entry.name, dir_size(entry.path, ctx),
                                            st.st_mtime, st.st_atime, True)
                        else:
                            yield FileEntry(entry.path, entry.name, 0, 0.0, 0.0, True)
                        continue
                    stack.append(entry.path)
                elif entry.is_file(follow_symlinks=False):
                    if with_stat:
                        st = entry.stat(follow_symlinks=False)
                        yield FileEntry(entry.path, entry.name, st.st_size,
                                        st.st_mtime, st.st_atime, False)
                    else:
                        yield FileEntry(entry.path, entry.name, 0, 0.0, 0.0, False)
            except OSError:
                ctx.error()


def count_files(root: str, ctx: JobContext, label: str = "جارٍ حصر الملفات", **kwargs) -> int:
    """مرور سريع لعدّ الملفات (لحساب نسبة التقدّم لاحقاً)."""
    errors_before = ctx.job.errors if ctx.job else 0
    count = 0
    for _ in walk_files(root, ctx, with_stat=False, **kwargs):
        count += 1
        if count % 500 == 0:
            ctx.progress(None, f"{label}... ({count:,} ملف)")
    if ctx.job:  # أخطاء مرحلة العدّ ستتكرر في مرحلة الفحص، فلا نعدّها مرتين
        ctx.job.errors = errors_before
    return count

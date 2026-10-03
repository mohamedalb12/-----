"""
privacy.py — مسح آثار التصفح والنشاط (مثل قسم Privacy في CleanMyMac).

لكل متصفح: الكاش، سجل التصفح، الكوكيز (تسجيلات الدخول)، الجلسات المحفوظة،
بيانات الملء التلقائي، وسجل التنزيلات. كلمات المرور المحفوظة لا تُلمس أبداً.

العناصر من نوع "sql" لا تُحذف كملفات، بل نمسح جداول السجل داخل قاعدة البيانات
(مثل Firefox الذي يحفظ السجل والإشارات المرجعية في نفس الملف).
"""

from __future__ import annotations

import glob
import os
import sqlite3
import sys
from dataclasses import dataclass
from typing import Dict, List, Tuple

from .jobs import JobContext, NULL_CONTEXT
from .models import Category, FileItem
from .walker import dir_size

IS_MAC = sys.platform == "darwin"
HOME = os.path.expanduser("~")
AS = os.path.join(HOME, "Library/Application Support")
CACHES = os.path.join(HOME, "Library/Caches")

KIND_LABELS = {
    "cache": "الكاش",
    "history": "سجل التصفح",
    "cookies": "الكوكيز (تسجيلات الدخول)",
    "session": "الجلسات والتبويبات المحفوظة",
    "autofill": "بيانات الملء التلقائي",
    "downloads": "سجل التنزيلات",
    "recent": "العناصر المستخدمة مؤخراً",
    "shell": "سجل أوامر Terminal",
}
# ما يُحدَّد تلقائياً (الكوكيز والملء التلقائي تسجّل خروجك من المواقع — لا نحددها افتراضياً)
DEFAULT_CHECKED = {"cache", "history", "downloads", "session", "recent"}


@dataclass
class Browser:
    name: str
    process: str        # اسم العملية لمعرفة إن كان مفتوحاً
    icon: str = "🌐"


# متصفحات مبنية على Chromium: (الاسم، العملية، مجلد البيانات، مجلد الكاش)
CHROMIUM = [
    ("Google Chrome", "Google Chrome", "Google/Chrome", "Google/Chrome"),
    ("Microsoft Edge", "Microsoft Edge", "Microsoft Edge", "Microsoft Edge"),
    ("Brave", "Brave Browser", "BraveSoftware/Brave-Browser", "BraveSoftware/Brave-Browser"),
    ("Opera", "Opera", "com.operasoftware.Opera", "com.operasoftware.Opera"),
    ("Vivaldi", "Vivaldi", "Vivaldi", "Vivaldi"),
    ("Arc", "Arc", "Arc/User Data", "Arc/User Data"),
    ("Chromium", "Chromium", "Chromium", "Chromium"),
]

# ملفات Chromium داخل كل ملف شخصي
CHROMIUM_FILES = {
    "history": ["History", "History-journal", "Visited Links", "Top Sites", "Top Sites-journal",
                "Network Action Predictor", "Shortcuts"],
    "cookies": ["Cookies", "Cookies-journal", "Network/Cookies", "Network/Cookies-journal"],
    "session": ["Sessions", "Current Session", "Current Tabs", "Last Session", "Last Tabs"],
    "autofill": ["Web Data", "Web Data-journal"],
    "cache": ["GPUCache", "Code Cache", "Service Worker/CacheStorage", "Service Worker/ScriptCache"],
}


def _item(path: str, browser: str, kind: str) -> FileItem:
    st = os.lstat(path)
    is_dir = os.path.isdir(path) and not os.path.islink(path)
    return FileItem(path, dir_size(path) if is_dir else st.st_size, Category.PRIVACY, st.st_mtime,
                    st.st_atime, is_dir, note=f"{browser}|{kind}")


def _chromium(name: str, data_dir: str, cache_dir: str) -> List[Tuple[str, str]]:
    root = os.path.join(AS, data_dir)
    found: List[Tuple[str, str]] = []
    if not os.path.isdir(root):
        return found
    profiles = [p for p in glob.glob(os.path.join(root, "*"))
                if os.path.basename(p) == "Default" or os.path.basename(p).startswith("Profile ")]
    for prof in profiles:
        for kind, names in CHROMIUM_FILES.items():
            for n in names:
                p = os.path.join(prof, n)
                if os.path.lexists(p):
                    found.append((p, kind))
    for prof_cache in glob.glob(os.path.join(CACHES, cache_dir, "*")):
        if os.path.isdir(prof_cache):
            found.append((prof_cache, "cache"))
    return found


def _safari() -> List[Tuple[str, str]]:
    lib = os.path.join(HOME, "Library")
    candidates = [
        (f"{lib}/Safari/History.db", "history"), (f"{lib}/Safari/History.db-wal", "history"),
        (f"{lib}/Safari/History.db-shm", "history"), (f"{lib}/Safari/History.db-lock", "history"),
        (f"{lib}/Safari/Downloads.plist", "downloads"),
        (f"{lib}/Safari/LastSession.plist", "session"), (f"{lib}/Safari/RecentlyClosedTabs.plist", "session"),
        (f"{lib}/Caches/com.apple.Safari", "cache"),
        (f"{lib}/Cookies/Cookies.binarycookies", "cookies"),
        (f"{lib}/Containers/com.apple.Safari/Data/Library/Cookies/Cookies.binarycookies", "cookies"),
        (f"{lib}/Safari/Form Values", "autofill"),
    ]
    return [(p, k) for p, k in candidates if os.path.lexists(p)]


def _firefox() -> List[Tuple[str, str]]:
    found: List[Tuple[str, str]] = []
    for prof in glob.glob(os.path.join(AS, "Firefox/Profiles/*")):
        for name, kind in (("cookies.sqlite", "cookies"), ("formhistory.sqlite", "autofill"),
                           ("sessionstore.jsonlz4", "session"), ("sessionstore-backups", "session")):
            p = os.path.join(prof, name)
            if os.path.lexists(p):
                found.append((p, kind))
        places = os.path.join(prof, "places.sqlite")
        if os.path.exists(places):
            found.append((places, "history"))   # يُمسح بـ SQL (يحتوي الإشارات المرجعية أيضاً)
    for cache in glob.glob(os.path.join(CACHES, "Firefox/Profiles/*")):
        found.append((cache, "cache"))
    return found


def _system() -> List[Tuple[str, str]]:
    found = []
    for p in glob.glob(os.path.join(AS, "com.apple.sharedfilelist/*RecentDocuments.sfl*")) + \
            glob.glob(os.path.join(AS, "com.apple.sharedfilelist/*RecentApplications.sfl*")) + \
            glob.glob(os.path.join(AS, "com.apple.sharedfilelist/*RecentServers.sfl*")) + \
            glob.glob(os.path.join(AS, "com.apple.sharedfilelist/com.apple.LSSharedFileList.ApplicationRecentDocuments/*")):
        found.append((p, "recent"))
    for name in (".zsh_history", ".bash_history"):
        p = os.path.join(HOME, name)
        if os.path.exists(p):
            found.append((p, "shell"))
    return found


BROWSER_ICONS = {"Safari": "🧭", "Google Chrome": "🟡", "Firefox": "🦊", "Microsoft Edge": "🌊",
                 "Brave": "🦁", "Opera": "⭕", "Vivaldi": "🎻", "Arc": "🌈", "Chromium": "🔵",
                 "النظام": "💻"}
PROCESS_NAMES = {name: proc for name, proc, _, _ in CHROMIUM}
PROCESS_NAMES.update({"Safari": "Safari", "Firefox": "firefox"})


def scan_privacy(ctx: JobContext = NULL_CONTEXT) -> Dict[str, List[FileItem]]:
    """يُرجع {اسم المتصفح: [عناصر]}. ‏item.note = "browser|kind"."""
    sources = [("Safari", _safari)] if IS_MAC else []
    sources += [(name, (lambda d=data, c=cache, n=name: _chromium(n, d, c)))
                for name, _proc, data, cache in CHROMIUM]
    sources += [("Firefox", _firefox), ("النظام", _system)]
    result: Dict[str, List[FileItem]] = {}
    for n, (name, fn) in enumerate(sources):
        if ctx.cancelled:
            break
        ctx.progress(n / len(sources), f"فحص {name}...")
        items = []
        for path, kind in fn():
            try:
                items.append(_item(path, name, kind))
            except OSError:
                ctx.error()
        if items:
            result[name] = items
    return result


def kind_of(item: FileItem) -> str:
    return item.note.split("|", 1)[1] if "|" in item.note else ""


def browser_of(item: FileItem) -> str:
    return item.note.split("|", 1)[0]


def _clear_firefox_history(db: str) -> None:
    con = sqlite3.connect(db, timeout=10)
    try:
        con.execute("DELETE FROM moz_historyvisits")
        con.execute("DELETE FROM moz_inputhistory")
        # حذف الصفحات التي ليست إشارات مرجعية
        con.execute("DELETE FROM moz_places WHERE id NOT IN (SELECT fk FROM moz_bookmarks WHERE fk NOT NULL)")
        con.commit()
        con.execute("VACUUM")
    finally:
        con.close()


def clean_privacy(ctx: JobContext, items: List[FileItem]):
    """حذف عناصر الخصوصية (نهائياً — فلا معنى لنقل الآثار إلى السلة)."""
    from .actions import FileActionError, delete_permanently
    deleted, failed = [], []
    for n, item in enumerate(items):
        ctx.progress(n / max(len(items), 1), f"مسح {KIND_LABELS.get(kind_of(item), '')} — {browser_of(item)}")
        try:
            if browser_of(item) == "Firefox" and kind_of(item) == "history":
                _clear_firefox_history(item.path)
            elif kind_of(item) == "shell":
                open(item.path, "w").close()      # إفراغ الملف بدل حذفه
            else:
                delete_permanently(item.path)
            deleted.append(item)
        except (FileActionError, OSError, sqlite3.Error) as exc:
            failed.append((item, str(exc)))
    ctx.progress(1.0, "", force=True)
    return deleted, failed

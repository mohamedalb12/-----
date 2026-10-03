"""
apps.py — إلغاء تثبيت التطبيقات بالكامل مع بقاياها.

عند حذف تطبيق بسحبه إلى السلة تبقى ملفاته المتناثرة في ~/Library
(الإعدادات، الكاش، بيانات الدعم، ...). هذه الوحدة:
- تسرد التطبيقات المثبتة مع أحجامها وأيقوناتها.
- تجد كل الملفات المرتبطة بتطبيق معيّن (بمعرّف الحزمة Bundle ID واسم التطبيق).
- تجد "بقايا" تطبيقات حُذفت سابقاً ولم تعد موجودة.
"""

from __future__ import annotations

import glob
import os
import plistlib
import re
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from .jobs import NULL_CONTEXT, JobContext
from .models import Category, FileItem
from .walker import HOME, dir_size

IS_MAC = sys.platform == "darwin"

APP_DIRS = ["/Applications", os.path.join(HOME, "Applications"), "/Applications/Utilities"]
SYSTEM_APP_DIRS = ["/System/Applications", "/System/Applications/Utilities"]


@dataclass
class AppInfo:
    name: str
    path: str
    bundle_id: str = ""
    version: str = ""
    executable: str = ""
    icon_file: str = ""
    size: int = -1                    # ‎-1 = لم يُحسب بعد
    is_system: bool = False
    alt_names: Set[str] = field(default_factory=set)   # الاسم الداخلي للتطبيق (CFBundleName)


def read_app(path: str) -> Optional[AppInfo]:
    plist_path = os.path.join(path, "Contents", "Info.plist")
    name = os.path.splitext(os.path.basename(path))[0]
    info: dict = {}
    try:
        with open(plist_path, "rb") as f:
            info = plistlib.load(f)
    except Exception:
        pass
    bundle_id = str(info.get("CFBundleIdentifier", ""))
    icon = str(info.get("CFBundleIconFile", "") or "")
    if icon and not icon.endswith(".icns"):
        icon += ".icns"
    icon_path = os.path.join(path, "Contents", "Resources", icon) if icon else ""
    if not icon_path or not os.path.exists(icon_path):
        candidates = glob.glob(os.path.join(path, "Contents", "Resources", "*.icns"))
        preferred = [c for c in candidates if "appicon" in c.lower() or name.lower() in c.lower()]
        icon_path = (preferred or candidates or [""])[0]
    alt_names = {str(info.get(k)) for k in ("CFBundleName", "CFBundleDisplayName") if info.get(k)}
    return AppInfo(
        name=name,
        path=path,
        bundle_id=bundle_id,
        version=str(info.get("CFBundleShortVersionString", "") or info.get("CFBundleVersion", "")),
        executable=str(info.get("CFBundleExecutable", "")),
        icon_file=icon_path,
        is_system=bundle_id.startswith("com.apple.") or path.startswith("/System/"),
        alt_names=alt_names,
    )


def list_apps() -> List[AppInfo]:
    """التطبيقات المثبتة في /Applications و ~/Applications (بدون تطبيقات النظام المحمية)."""
    apps, seen = [], set()
    for d in APP_DIRS:
        for path in sorted(glob.glob(os.path.join(d, "*.app"))):
            real = os.path.realpath(path)
            if real in seen:
                continue
            seen.add(real)
            app = read_app(path)
            if app:
                apps.append(app)
    apps.sort(key=lambda a: a.name.lower())
    return apps


def load_icon(icon_file: str, size: int = 64):
    """تحميل أيقونة التطبيق كصورة Pillow (أو None)."""
    if not icon_file:
        return None
    try:
        from PIL import Image
        img = Image.open(icon_file)
        img.load()
        img = img.convert("RGBA")
        img.thumbnail((size, size), Image.LANCZOS)
        return img
    except Exception:
        return None


def compute_app_details(ctx: JobContext, apps: List[AppInfo], icon_size: int = 64) -> None:
    """حساب أحجام التطبيقات وتحميل أيقوناتها في الخلفية (رسالة لكل تطبيق)."""
    for n, app in enumerate(apps):
        if ctx.cancelled:
            return
        icon = load_icon(app.icon_file, icon_size)
        app.size = dir_size(app.path, ctx)
        ctx.emit("app_details", app.path, app.size, icon)
        ctx.progress((n + 1) / max(len(apps), 1), f"حساب أحجام التطبيقات... {n + 1} من {len(apps)}")


# --------------------------------------------------------------------------- #
#  ملفات التطبيق المتناثرة
# --------------------------------------------------------------------------- #

LIB = os.path.join(HOME, "Library")

# (المجلد، نوع المطابقة، الوصف)
# نوع المطابقة: id = اسم = معرّف الحزمة،  name = اسم = اسم التطبيق،
#               idprefix = يبدأ بمعرّف الحزمة،  idsuffix = ينتهي بمعرّف الحزمة
_LEFTOVER_RULES: List[Tuple[str, str, str]] = [
    (f"{LIB}/Application Support", "id", "ملفات الدعم"),
    (f"{LIB}/Application Support", "name", "ملفات الدعم"),
    (f"{LIB}/Caches", "id", "الكاش"),
    (f"{LIB}/Caches", "name", "الكاش"),
    (f"{LIB}/Preferences", "idprefix", "التفضيلات"),
    (f"{LIB}/Preferences/ByHost", "idprefix", "التفضيلات"),
    (f"{LIB}/Containers", "id", "الحاويات"),
    (f"{LIB}/Group Containers", "idsuffix", "الحاويات"),
    (f"{LIB}/Logs", "id", "السجلات"),
    (f"{LIB}/Logs", "name", "السجلات"),
    (f"{LIB}/Saved Application State", "idprefix", "حالة النوافذ المحفوظة"),
    (f"{LIB}/HTTPStorages", "idprefix", "بيانات الإنترنت"),
    (f"{LIB}/WebKit", "id", "بيانات الإنترنت"),
    (f"{LIB}/Cookies", "idprefix", "بيانات الإنترنت"),
    (f"{LIB}/LaunchAgents", "idprefix", "عناصر بدء التشغيل"),
    (f"{LIB}/Application Scripts", "id", "سكربتات"),
    ("/Library/Application Support", "name", "ملفات الدعم (للنظام)"),
    ("/Library/Application Support", "id", "ملفات الدعم (للنظام)"),
    ("/Library/Caches", "id", "الكاش"),
    ("/Library/LaunchAgents", "idprefix", "عناصر بدء التشغيل"),
    ("/Library/LaunchDaemons", "idprefix", "عناصر بدء التشغيل"),
    ("/Library/Preferences", "idprefix", "التفضيلات"),
]

# أسماء عامة لا نطابقها بالاسم أبداً (قد تخص تطبيقات أخرى)
_GENERIC_NAMES = {"google", "microsoft", "adobe", "apple", "app", "data", "cache", "caches",
                  "logs", "support", "helper", "update", "updater", "java", "python", "node"}


def _matches(entry_name: str, rule: str, app: AppInfo) -> bool:
    lname = entry_name.lower()
    bid = app.bundle_id.lower()
    if rule == "id":
        return bool(bid) and lname == bid
    if rule == "idprefix":
        return bool(bid) and (lname == bid or lname.startswith(bid + "."))
    if rule == "idsuffix":
        return bool(bid) and (lname == bid or lname.endswith("." + bid))
    if rule == "name":
        names = {n.lower() for n in {app.name} | app.alt_names}
        return any(len(n) >= 3 and n not in _GENERIC_NAMES and lname == n for n in names)
    return False


def find_app_files(app: AppInfo, ctx: JobContext = NULL_CONTEXT) -> List[FileItem]:
    """كل الملفات المرتبطة بالتطبيق خارج حزمته."""
    found: Dict[str, FileItem] = {}
    for folder, rule, label in _LEFTOVER_RULES:
        try:
            with os.scandir(folder) as it:
                entries = list(it)
        except OSError:
            continue
        for entry in entries:
            if entry.path in found or not _matches(entry.name, rule, app):
                continue
            try:
                st = entry.stat(follow_symlinks=False)
                is_dir = entry.is_dir(follow_symlinks=False)
            except OSError:
                ctx.error()
                continue
            found[entry.path] = FileItem(entry.path, dir_size(entry.path, ctx), Category.LEFTOVER,
                                         st.st_mtime, st.st_atime, is_dir, note=label)
    return sorted(found.values(), key=lambda i: i.size, reverse=True)


def is_running(app: AppInfo) -> bool:
    try:
        out = subprocess.run(["pgrep", "-f", os.path.join(app.path, "Contents", "MacOS") + "/"],
                             capture_output=True, timeout=5)
        return out.returncode == 0
    except Exception:
        return False


def quit_app(app: AppInfo) -> None:
    if IS_MAC and app.bundle_id:
        subprocess.run(["osascript", "-e", f'tell application id "{app.bundle_id}" to quit'],
                       capture_output=True, timeout=15)


# --------------------------------------------------------------------------- #
#  بقايا تطبيقات محذوفة
# --------------------------------------------------------------------------- #

_BUNDLE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*\.[a-z0-9-]+\.[a-z0-9.\-_]+$", re.I)
_ORPHAN_DIRS = [
    (f"{LIB}/Application Support", "ملفات الدعم"),
    (f"{LIB}/Caches", "الكاش"),
    (f"{LIB}/Preferences", "التفضيلات"),
    (f"{LIB}/Saved Application State", "حالة النوافذ المحفوظة"),
    (f"{LIB}/HTTPStorages", "بيانات الإنترنت"),
    (f"{LIB}/WebKit", "بيانات الإنترنت"),
    (f"{LIB}/Logs", "السجلات"),
]
_SAFE_PREFIXES = ("com.apple.", "group.com.apple.", "systemgroup.", "org.python.", "com.microsoft.office")
_STRIP_SUFFIXES = (".plist", ".savedstate", ".binarycookies")


def installed_bundle_ids() -> Set[str]:
    ids: Set[str] = set()
    paths: List[str] = []
    for d in APP_DIRS + SYSTEM_APP_DIRS:
        paths += glob.glob(os.path.join(d, "*.app"))
    if IS_MAC:  # Spotlight يعرف التطبيقات المثبتة في أي مكان
        try:
            out = subprocess.run(["mdfind", "kMDItemContentType == 'com.apple.application-bundle'"],
                                 capture_output=True, text=True, timeout=30)
            paths += [p for p in out.stdout.splitlines() if p.endswith(".app")]
        except Exception:
            pass
    for p in set(paths):
        app = read_app(p)
        if app and app.bundle_id:
            ids.add(app.bundle_id.lower())
    return ids


def _vendor(bid: str) -> str:
    return ".".join(bid.split(".")[:2])


def find_orphans(ctx: JobContext = NULL_CONTEXT) -> List[FileItem]:
    """ملفات في ~/Library تخص تطبيقات لم تعد مثبتة على الجهاز."""
    ctx.progress(None, "جمع قائمة التطبيقات المثبتة...", force=True)
    installed = installed_bundle_ids()
    vendors = {_vendor(b) for b in installed}
    results: List[FileItem] = []
    for n, (folder, label) in enumerate(_ORPHAN_DIRS):
        if ctx.cancelled:
            break
        ctx.progress(n / len(_ORPHAN_DIRS), f"البحث عن بقايا التطبيقات في {label}...")
        try:
            with os.scandir(folder) as it:
                entries = list(it)
        except OSError:
            continue
        for entry in entries:
            lname = entry.name.lower()
            for suf in _STRIP_SUFFIXES:
                if lname.endswith(suf):
                    lname = lname[: -len(suf)]
            if not _BUNDLE_ID_RE.match(lname) or lname.startswith(_SAFE_PREFIXES):
                continue
            # نتحفّظ: أي تشابه مع تطبيق مثبت (أو نفس الشركة) يعني أنه ليس من البقايا
            if _vendor(lname) in vendors or any(
                    lname.startswith(b) or b.startswith(lname) for b in installed):
                continue
            try:
                st = entry.stat(follow_symlinks=False)
                is_dir = entry.is_dir(follow_symlinks=False)
            except OSError:
                continue
            size = dir_size(entry.path, ctx)
            if size > 0:
                results.append(FileItem(entry.path, size, Category.LEFTOVER, st.st_mtime,
                                        st.st_atime, is_dir, note=lname))
    results.sort(key=lambda i: i.size, reverse=True)
    return results

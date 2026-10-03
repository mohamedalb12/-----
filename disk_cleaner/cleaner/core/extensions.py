"""
extensions.py — مدير الإضافات (مثل Extensions في CleanMyMac).

- إضافات النظام: لوحات التفضيلات، إضافات Quick Look و Spotlight، إضافات الإنترنت،
  شاشات التوقف — يمكن حذفها مباشرة (إلى السلة).
- إضافات المتصفحات (Chrome وأخواته، Firefox): نعرضها ونفتح صفحة إدارة الإضافات في
  المتصفح لحذفها، لأن حذف ملفاتها مباشرة يجعل المتصفح يعيد تنزيلها عبر المزامنة.
"""

from __future__ import annotations

import glob
import json
import os
from dataclasses import dataclass
from typing import Dict, List

from .jobs import JobContext, NULL_CONTEXT
from .models import Category, FileItem
from .privacy import AS, CHROMIUM
from .walker import dir_size

HOME = os.path.expanduser("~")
LIB = os.path.join(HOME, "Library")

SYSTEM_EXTENSION_DIRS = [
    ("لوحات التفضيلات", "⚙️", [f"{LIB}/PreferencePanes", "/Library/PreferencePanes"]),
    ("إضافات المعاينة السريعة", "👁", [f"{LIB}/QuickLook", "/Library/QuickLook"]),
    ("إضافات Spotlight", "🔎", [f"{LIB}/Spotlight", "/Library/Spotlight"]),
    ("إضافات الإنترنت", "🌐", [f"{LIB}/Internet Plug-Ins", "/Library/Internet Plug-Ins"]),
    ("شاشات التوقف", "🖼", [f"{LIB}/Screen Savers", "/Library/Screen Savers"]),
    ("إضافات الصوت", "🔊", [f"{LIB}/Audio/Plug-Ins/Components", "/Library/Audio/Plug-Ins/Components"]),
]


@dataclass
class BrowserExtension:
    browser: str
    name: str
    version: str
    path: str
    ext_id: str


def system_extensions(ctx: JobContext = NULL_CONTEXT) -> Dict[str, List[FileItem]]:
    result: Dict[str, List[FileItem]] = {}
    for label, icon, dirs in SYSTEM_EXTENSION_DIRS:
        items = []
        for d in dirs:
            for p in glob.glob(os.path.join(d, "*")):
                if os.path.basename(p).startswith("."):
                    continue
                try:
                    st = os.lstat(p)
                except OSError:
                    ctx.error()
                    continue
                items.append(FileItem(p, dir_size(p), Category.EXTENSION, st.st_mtime, st.st_atime,
                                      os.path.isdir(p), note=label))
        if items:
            result[f"{icon}  {label}"] = items
    return result


def _chromium_name(manifest: dict, version_dir: str) -> str:
    name = str(manifest.get("name", ""))
    if name.startswith("__MSG_") and name.endswith("__"):
        key = name[6:-2]
        locale = manifest.get("default_locale", "en")
        for loc in (locale, "en", "en_US"):
            try:
                with open(os.path.join(version_dir, "_locales", loc, "messages.json"), encoding="utf-8") as f:
                    msgs = json.load(f)
                for k, v in msgs.items():
                    if k.lower() == key.lower():
                        return str(v.get("message", name))
            except Exception:
                continue
    return name


def browser_extensions() -> List[BrowserExtension]:
    exts: List[BrowserExtension] = []
    for browser, _proc, data_dir, _cache in CHROMIUM:
        root = os.path.join(AS, data_dir)
        for ext_dir in glob.glob(os.path.join(root, "*", "Extensions", "*")):
            versions = sorted(glob.glob(os.path.join(ext_dir, "*")))
            if not versions:
                continue
            try:
                with open(os.path.join(versions[-1], "manifest.json"), encoding="utf-8") as f:
                    manifest = json.load(f)
            except Exception:
                continue
            name = _chromium_name(manifest, versions[-1])
            # إضافات Chrome المدمجة (مثل متجر الويب) لا نعرضها
            if not name or name.startswith("__MSG_") or manifest.get("theme"):
                continue
            exts.append(BrowserExtension(browser, name, str(manifest.get("version", "")), ext_dir,
                                         os.path.basename(ext_dir)))
    for ext_json in glob.glob(os.path.join(AS, "Firefox/Profiles/*/extensions.json")):
        try:
            with open(ext_json, encoding="utf-8") as f:
                addons = json.load(f).get("addons", [])
        except Exception:
            continue
        for a in addons:
            if a.get("type") != "extension" or a.get("location") != "app-profile":
                continue
            name = (a.get("defaultLocale") or {}).get("name") or a.get("id", "")
            exts.append(BrowserExtension("Firefox", name, str(a.get("version", "")),
                                         a.get("path") or ext_json, a.get("id", "")))
    # إزالة التكرار (نفس الإضافة في عدة ملفات شخصية)
    unique = {}
    for e in exts:
        unique.setdefault((e.browser, e.ext_id), e)
    return sorted(unique.values(), key=lambda e: (e.browser, e.name.lower()))


EXTENSION_PAGES = {
    "Google Chrome": "chrome://extensions", "Microsoft Edge": "edge://extensions",
    "Brave": "brave://extensions", "Vivaldi": "vivaldi://extensions", "Opera": "opera://extensions",
    "Arc": "arc://extensions", "Chromium": "chrome://extensions", "Firefox": "about:addons",
}
BROWSER_APPS = {"Google Chrome": "Google Chrome", "Microsoft Edge": "Microsoft Edge",
                "Brave": "Brave Browser", "Vivaldi": "Vivaldi", "Opera": "Opera", "Arc": "Arc",
                "Chromium": "Chromium", "Firefox": "Firefox"}


def open_extensions_page(browser: str) -> None:
    from .shell import run
    app = BROWSER_APPS.get(browser)
    page = EXTENSION_PAGES.get(browser)
    if app and page:
        run(["open", "-a", app, page], timeout=10)

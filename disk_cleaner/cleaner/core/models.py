"""
models.py — نماذج البيانات المشتركة: التصنيفات، أنواع الملفات، وعنصر الملف.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Tuple


# --------------------------------------------------------------------------- #
#  تصنيفات النتائج
# --------------------------------------------------------------------------- #


class Category(str, Enum):
    CACHE = "cache"
    LOGS = "logs"
    TEMP = "temp"
    TRASH = "trash"
    DEV = "dev"
    INSTALLERS = "installers"
    IOS_BACKUP = "ios_backup"
    MAIL = "mail"
    SYSTEM_JUNK = "system_junk"
    LARGE = "large"
    DUPLICATE = "duplicate"
    APP = "app"
    LEFTOVER = "leftover"
    PRIVACY = "privacy"
    THREAT = "threat"
    EXTENSION = "extension"


@dataclass(frozen=True)
class CategoryInfo:
    label: str
    icon: str
    description: str
    safe: bool          # هل يُحدَّد تلقائياً للتنظيف؟
    color: str


CATEGORY_INFO: Dict[Category, CategoryInfo] = {
    Category.CACHE: CategoryInfo("كاش النظام والتطبيقات", "⚡",
                                 "ملفات مؤقتة تعيد التطبيقات إنشاءها تلقائياً.", True, "#7c6cff"),
    Category.LOGS: CategoryInfo("ملفات السجلات", "📜",
                                "سجلات الأحداث وتقارير الأعطال القديمة.", True, "#3b82f6"),
    Category.TEMP: CategoryInfo("ملفات مؤقتة", "⏳",
                                "ملفات مؤقتة قديمة لم تعد مستخدمة.", True, "#06b6d4"),
    Category.TRASH: CategoryInfo("سلة المحذوفات", "🗑",
                                 "ملفات في السلة ما زالت تشغل مساحة.", True, "#ef4444"),
    Category.DEV: CategoryInfo("مخلفات المطوّرين", "🛠",
                               "Xcode DerivedData، كاش npm و Gradle وغيرها.", True, "#f59e0b"),
    Category.INSTALLERS: CategoryInfo("ملفات تثبيت منسية", "💿",
                                      "ملفات ‎.dmg و ‎.pkg في مجلد التنزيلات.", False, "#ec4899"),
    Category.IOS_BACKUP: CategoryInfo("نسخ iPhone/iPad الاحتياطية", "📱",
                                      "نسخ احتياطية قديمة لأجهزة iOS — راجعها قبل الحذف.", False, "#8b5cf6"),
    Category.MAIL: CategoryInfo("مرفقات البريد", "✉️",
                                "مرفقات فتحتها من تطبيق Mail ونُسخت محلياً — تبقى في البريد نفسه.", False,
                                "#0ea5e9"),
    Category.SYSTEM_JUNK: CategoryInfo("ملفات نظام مهملة", "🧩",
                                       "ملفات ‎.DS_Store وملفات ‎._ المخفية.", True, "#64748b"),
    Category.LARGE: CategoryInfo("ملفات كبيرة", "📦", "", False, "#22c55e"),
    Category.DUPLICATE: CategoryInfo("ملفات مكررة", "👯", "", False, "#14b8a6"),
    Category.APP: CategoryInfo("تطبيق", "🧩", "", False, "#6366f1"),
    Category.LEFTOVER: CategoryInfo("بقايا تطبيقات", "🧹", "", False, "#f97316"),
    Category.PRIVACY: CategoryInfo("بيانات الخصوصية", "🕵️", "", False, "#0ea5e9"),
    Category.THREAT: CategoryInfo("تهديد محتمل", "🛡", "", False, "#ef4444"),
    Category.EXTENSION: CategoryInfo("إضافة", "🧩", "", False, "#8b5cf6"),
}

JUNK_CATEGORIES = [
    Category.CACHE, Category.LOGS, Category.TEMP, Category.TRASH, Category.DEV,
    Category.INSTALLERS, Category.MAIL, Category.IOS_BACKUP, Category.SYSTEM_JUNK,
]


# --------------------------------------------------------------------------- #
#  أنواع الملفات (حسب الامتداد)
# --------------------------------------------------------------------------- #

# key: (الاسم، الأيقونة، اللون، الامتدادات)
KINDS: Dict[str, Tuple[str, str, str, frozenset]] = {
    "video": ("فيديو", "🎬", "#ef4444", frozenset(
        ".mp4 .mov .mkv .avi .wmv .m4v .webm .flv .mpg .mpeg .3gp .mts .m2ts".split())),
    "audio": ("صوتيات", "🎵", "#f59e0b", frozenset(
        ".mp3 .wav .aac .flac .m4a .ogg .aiff .aif .wma .alac .caf".split())),
    "image": ("صور", "🖼", "#22c55e", frozenset(
        ".jpg .jpeg .png .gif .heic .heif .tiff .tif .bmp .webp .raw .cr2 .cr3 .nef .arw .dng .psd .svg".split())),
    "archive": ("أرشيفات مضغوطة", "🗜", "#a855f7", frozenset(
        ".zip .rar .7z .tar .gz .bz2 .xz .tgz .zst".split())),
    "disk": ("صور أقراص ومثبّتات", "💿", "#ec4899", frozenset(
        ".dmg .iso .pkg .mpkg .img .exe .msi .deb .rpm .appimage .vmdk .vdi .qcow2 .ipsw .xip .sparseimage .sparsebundle".split())),
    "doc": ("مستندات", "📄", "#3b82f6", frozenset(
        ".pdf .doc .docx .xls .xlsx .ppt .pptx .pages .numbers .key .txt .rtf .epub .md .csv".split())),
    "app": ("تطبيقات وحزم", "🧩", "#6366f1", frozenset(
        ".app .photoslibrary .musiclibrary .fcpbundle .imovielibrary .logicx .band .xcarchive .bundle .framework".split())),
    "code": ("كود وبيانات", "💻", "#06b6d4", frozenset(
        ".json .xml .py .js .ts .html .css .java .c .cpp .h .swift .go .rs .db .sqlite .sqlite3 .sql .log".split())),
    "other": ("أخرى", "❔", "#64748b", frozenset()),
}

_EXT_TO_KIND = {ext: key for key, (_, _, _, exts) in KINDS.items() for ext in exts}


def kind_of(name: str) -> str:
    _, ext = os.path.splitext(name)
    return _EXT_TO_KIND.get(ext.lower(), "other")


def kind_label(key: str) -> str:
    label, icon, _, _ = KINDS[key]
    return f"{icon}  {label}"


# --------------------------------------------------------------------------- #
#  عنصر ملف
# --------------------------------------------------------------------------- #


@dataclass
class FileItem:
    path: str
    size: int
    category: Category = Category.LARGE
    mtime: float = 0.0
    atime: float = 0.0
    is_dir: bool = False
    note: str = ""

    @property
    def name(self) -> str:
        return os.path.basename(self.path.rstrip(os.sep)) or self.path

    @property
    def last_used(self) -> float:
        return max(self.mtime, self.atime)

    @property
    def kind(self) -> str:
        return kind_of(self.name)


# --------------------------------------------------------------------------- #
#  تنسيق القيم للعرض
# --------------------------------------------------------------------------- #


def human_size(num_bytes: float) -> str:
    """تحويل الحجم إلى صيغة مقروءة (يستخدم 1000 مثل Finder في ماك)."""
    step = 1000.0
    for unit in ("B", "KB", "MB", "GB"):
        if abs(num_bytes) < step:
            return f"{num_bytes:.0f} {unit}" if unit in ("B", "KB") else f"{num_bytes:.1f} {unit}"
        num_bytes /= step
    return f"{num_bytes:.2f} TB"


def _ar_count(n: int, one: str, two: str, few: str, many: str) -> str:
    """صياغة العدد بالعربية: يوم، يومين، 3 أيام، 11 يوماً."""
    if n == 1:
        return one
    if n == 2:
        return two
    if 3 <= n % 100 <= 10:
        return f"{n} {few}"
    return f"{n} {many}"


def relative_age(ts: float) -> str:
    if not ts:
        return "—"
    days = int((time.time() - ts) // 86400)
    if days < 1:
        return "اليوم"
    if days < 30:
        return "منذ " + _ar_count(days, "يوم", "يومين", "أيام", "يوماً")
    if days < 365:
        return "منذ " + _ar_count(days // 30, "شهر", "شهرين", "أشهر", "شهراً")
    return "منذ " + _ar_count(days // 365, "سنة", "سنتين", "سنوات", "سنة")


def format_date(ts: float) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(ts)) if ts else "—"


def short_path(path: str) -> str:
    home = os.path.expanduser("~")
    if path == home or path.startswith(home + os.sep):
        return "~" + path[len(home):]
    return path

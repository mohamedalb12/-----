"""
security.py — الحماية (مثل قسم Protection في CleanMyMac).

1. فحص إعدادات الأمان في macOS: ‏Gatekeeper، حماية النظام SIP، تشفير FileVault،
   الجدار الناري، التحديثات التلقائية، وإصدار XProtect.
2. فحص التهديدات: يبحث عن برامج الإعلانات المزعجة (Adware) المعروفة، والوكلاء
   الخلفيين المشبوهين (غير موقّعين، أو يعملون من مجلدات مؤقتة، أو برنامجهم محذوف)،
   وإضافات المتصفح المعروفة بأنها ضارة.

ملاحظة صريحة: هذا فحص استدلالي (Heuristic) وليس برنامج مكافحة فيروسات بقاعدة بيانات
توقيعات. macOS نفسه يحتوي على XProtect الذي يحذف البرمجيات الخبيثة المعروفة تلقائياً.
"""

from __future__ import annotations

import glob
import os
import plistlib
import re
import sys
from dataclasses import dataclass
from typing import List, Optional

from .jobs import JobContext, NULL_CONTEXT
from .models import Category, FileItem
from .shell import run
from .walker import dir_size

IS_MAC = sys.platform == "darwin"
HOME = os.path.expanduser("~")


# --------------------------------------------------------------------------- #
#  إعدادات الحماية
# --------------------------------------------------------------------------- #


@dataclass
class ProtectionCheck:
    key: str
    title: str
    ok: Optional[bool]          # None = تعذّر التحقق
    detail: str
    settings_url: str = ""


def _check(cmd, ok_pattern: str, timeout: float = 10) -> Optional[bool]:
    code, out = run(cmd, timeout=timeout)
    if code == 127 or (code != 0 and not out):
        return None
    return bool(re.search(ok_pattern, out, re.I))


def protection_checks() -> List[ProtectionCheck]:
    if not IS_MAC:
        return []
    checks = []
    gk = _check(["spctl", "--status"], r"assessments enabled")
    checks.append(ProtectionCheck("gatekeeper", "Gatekeeper", gk,
                                  "يمنع تشغيل التطبيقات غير الموثوقة." if gk else
                                  "مُعطّل! أي تطبيق يمكنه العمل دون تحقق.",
                                  "x-apple.systempreferences:com.apple.preference.security?General"))
    sip = _check(["csrutil", "status"], r"enabled")
    checks.append(ProtectionCheck("sip", "حماية سلامة النظام (SIP)", sip,
                                  "ملفات النظام محمية من التعديل." if sip else
                                  "مُعطّلة — يُنصح بتفعيلها من وضع الاسترداد (Recovery)."))
    fv = _check(["fdesetup", "status"], r"FileVault is On")
    checks.append(ProtectionCheck("filevault", "تشفير FileVault", fv,
                                  "قرصك مشفّر — بياناتك آمنة لو سُرق الجهاز." if fv else
                                  "القرص غير مشفّر. يُنصح بتفعيله لحماية بياناتك.",
                                  "x-apple.systempreferences:com.apple.preference.security?FDE"))
    fw = _check(["/usr/libexec/ApplicationFirewall/socketfilterfw", "--getglobalstate"],
                r"enabled|State = [12]")
    checks.append(ProtectionCheck("firewall", "الجدار الناري", fw,
                                  "يمنع الاتصالات الواردة غير المرغوبة." if fw else
                                  "مُعطّل. يُنصح بتفعيله خاصة على الشبكات العامة.",
                                  "x-apple.systempreferences:com.apple.Network-Settings.extension?Firewall"))
    au = _check(["defaults", "read", "/Library/Preferences/com.apple.SoftwareUpdate",
                 "AutomaticallyInstallMacOSUpdates"], r"^\s*1")
    checks.append(ProtectionCheck("updates", "تحديثات macOS التلقائية", au,
                                  "يتم تثبيت تحديثات الأمان تلقائياً." if au else
                                  "التثبيت التلقائي غير مفعّل — فعّله لتصلك إصلاحات الأمان.",
                                  "x-apple.systempreferences:com.apple.Software-Update-Settings.extension"))
    xp = _xprotect_version()
    checks.append(ProtectionCheck("xprotect", "XProtect (مكافح البرمجيات الخبيثة من Apple)",
                                  True if xp else None,
                                  f"الإصدار {xp} — يعمل تلقائياً في الخلفية." if xp else "تعذّر قراءة الإصدار."))
    return checks


def _xprotect_version() -> str:
    for p in ("/Library/Apple/System/Library/CoreServices/XProtect.bundle/Contents/Info.plist",
              "/System/Library/CoreServices/XProtect.bundle/Contents/Info.plist"):
        try:
            with open(p, "rb") as f:
                return str(plistlib.load(f).get("CFBundleShortVersionString", ""))
        except Exception:
            continue
    return ""


# --------------------------------------------------------------------------- #
#  فحص التهديدات
# --------------------------------------------------------------------------- #

# أسماء عائلات Adware المعروفة على macOS (أجزاء من الأسماء، بأحرف صغيرة)
ADWARE_PATTERNS = [
    "mackeeper", "genieo", "vsearch", "pirrit", "shlayer", "bundlore", "adload", "searchbaron",
    "searchmine", "searchpulse", "searchmarquis", "conduit", "installmac", "spigot", "crossrider",
    "advancedmaccleaner", "advanced mac cleaner", "maccleanup pro", "mac auto fixer", "macbooster",
    "smart mac booster", "chummy", "mughthesec", "operatorsearch", "safefinder", "weknow",
    "trovi", "yesearches", "mybrowserhelper", "vidx", "zipcloud", "tapufind",
    "searchtool", "loudmouth", "geneio", "downlite", "bitcoin miner", "xmrig",
]
_ADWARE_RE = re.compile("|".join(re.escape(p) for p in ADWARE_PATTERNS), re.I)
_SUSPICIOUS_DIRS = ("/tmp/", "/private/tmp/", "/var/tmp/", "/private/var/tmp/", "/Users/Shared/")


@dataclass
class Threat:
    path: str
    title: str
    reason: str
    severity: str        # high / medium / low


def _signed(path: str) -> Optional[bool]:
    if not IS_MAC or not os.path.exists(path):
        return None
    code, _ = run(["codesign", "--verify", "--strict", path], timeout=20)
    return code == 0


def scan_threats(ctx: JobContext = NULL_CONTEXT) -> List[FileItem]:
    threats: List[Threat] = []

    # 1) الوكلاء والخدمات الخلفية
    from .startup import list_launch_items
    items = list_launch_items(ctx)
    for n, item in enumerate(items):
        if ctx.cancelled:
            break
        ctx.progress(0.6 * n / max(len(items), 1), f"فحص العناصر الخلفية: {item.label}")
        text = f"{item.label} {item.program}"
        if _ADWARE_RE.search(text):
            threats.append(Threat(item.path, item.label, "يطابق اسم برنامج إعلانات مزعجة معروف", "high"))
        elif item.program and item.program.startswith(_SUSPICIOUS_DIRS):
            threats.append(Threat(item.path, item.label, "يعمل من مجلد مؤقت أو مشترك — سلوك مشبوه", "high"))
        elif any(part.startswith(".") for part in item.program.split("/")[1:-1]):
            threats.append(Threat(item.path, item.label, "يعمل من مجلد مخفي", "medium"))
        elif item.program and not item.program_exists:
            threats.append(Threat(item.path, item.label, "بقايا: البرنامج الذي يشغّله لم يعد موجوداً", "low"))
        elif item.program and not item.label.startswith("com.apple.") and _signed(item.program) is False:
            threats.append(Threat(item.path, item.label, "البرنامج غير موقّع رقمياً", "medium"))

    # 2) التطبيقات وملفات الدعم
    ctx.progress(0.65, "فحص التطبيقات وملفات الدعم...")
    for pattern in ("/Applications/*", os.path.join(HOME, "Applications/*"),
                    os.path.join(HOME, "Library/Application Support/*"),
                    "/Library/Application Support/*"):
        for p in glob.glob(pattern):
            if _ADWARE_RE.search(os.path.basename(p)):
                threats.append(Threat(p, os.path.basename(p), "يطابق اسم برنامج إعلانات مزعجة معروف", "high"))

    # 3) إضافات المتصفحات
    ctx.progress(0.8, "فحص إضافات المتصفحات...")
    from .extensions import browser_extensions
    for ext in browser_extensions():
        if _ADWARE_RE.search(ext.name):
            threats.append(Threat(ext.path, f"{ext.name} ({ext.browser})",
                                  "إضافة متصفح معروفة بالإعلانات المزعجة أو تغيير محرك البحث", "high"))

    ctx.progress(1.0, "", force=True)
    severity_order = {"high": 0, "medium": 1, "low": 2}
    threats.sort(key=lambda t: severity_order[t.severity])
    result = []
    seen = set()
    for t in threats:
        if t.path in seen:
            continue
        seen.add(t.path)
        try:
            st = os.lstat(t.path)
        except OSError:
            continue
        result.append(FileItem(t.path, dir_size(t.path), Category.THREAT, st.st_mtime, st.st_atime,
                               os.path.isdir(t.path), note=f"{t.severity}|{t.reason}|{t.title}"))
    return result


def threat_parts(item: FileItem):
    severity, reason, title = (item.note.split("|", 2) + ["", "", ""])[:3]
    return severity, reason, title


SEVERITY_LABEL = {"high": "🔴 خطورة عالية", "medium": "🟠 مشبوه", "low": "🟡 بقايا غير ضارة"}

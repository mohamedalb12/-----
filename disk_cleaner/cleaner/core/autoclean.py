"""
autoclean.py — التنظيف التلقائي (مثل Autopilot في CleanMyMac).

يعمل حتى والبرنامج مغلق: نُثبّت «وكيل macOS» (LaunchAgent) يشغّل البرنامج في الخلفية
بدون نافذة كل عدة ساعات:

    "Disk Cleaner Pro" --autoclean

في كل مرة:
1. يقيس حجم الفئات المختارة (الكاش، السجلات، المؤقتات، مخلفات المطورين).
2. إذا تجاوز المجموع الحد الذي اختاره المستخدم → يحذف الملفات القديمة فقط
   (التي لم تُعدَّل منذ عدة أيام)، فلا يتأثر أي تطبيق يعمل الآن.
3. يفرّغ من سلة المحذوفات ما مضى عليه أكثر من N يوماً (اختياري).
4. ينبّه إذا قلّت المساحة الحرة عن حد معيّن (اختياري).
5. يرسل إشعار macOS بالنتيجة ويسجّلها في السجل.

ملاحظات أمان:
- كاش Apple الداخلي (com.apple.*) لا يُلمس — النظام يديره بنفسه.
- الحذف هنا نهائي: نقل الكاش إلى السلة لا يحرر أي مساحة.
"""

from __future__ import annotations

import json
import os
import plistlib
import stat
import sys
import time
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional

from .. import BUNDLE_ID
from .actions import disk_usage, is_protected
from .jobs import NULL_CONTEXT, JobContext
from .junk import junk_targets, scan_junk
from .models import CATEGORY_INFO, Category, FileItem, human_size
from .settings import Settings, settings_dir
from .shell import applescript_quote, osascript, run

IS_MAC = sys.platform == "darwin"
DAY = 86400
AGENT_LABEL = f"{BUNDLE_ID}.autoclean"
AGENT_PATH = os.path.expanduser(f"~/Library/LaunchAgents/{AGENT_LABEL}.plist")
STATE_PATH = os.path.join(settings_dir(), "autoclean.json")

# الفئات المسموح بتنظيفها تلقائياً (القرار للمستخدم من بينها)
AUTO_CATEGORIES = [Category.CACHE, Category.LOGS, Category.TEMP, Category.DEV]
_SKIP_NAMES = ("com.apple.", "cloudkit", "com.mohamedalb12.")


# --------------------------------------------------------------------------- #
#  الحالة والسجل (ملف منفصل حتى لا يتعارض مع إعدادات الواجهة)
# --------------------------------------------------------------------------- #


@dataclass
class RunRecord:
    time: float
    measured: int           # الحجم المقاس للفئات المختارة
    freed: int              # ما تم تحريره من الكاش ونحوه
    trash_freed: int
    files: int
    triggered: bool
    free_space: int
    note: str = ""


@dataclass
class AutoState:
    total_freed: int = 0
    runs: List[dict] = field(default_factory=list)
    last_low_disk_alert: float = 0.0

    @classmethod
    def load(cls) -> "AutoState":
        try:
            with open(STATE_PATH, encoding="utf-8") as f:
                data = json.load(f)
            return cls(total_freed=int(data.get("total_freed", 0)), runs=list(data.get("runs", [])),
                       last_low_disk_alert=float(data.get("last_low_disk_alert", 0)))
        except Exception:
            return cls()

    def save(self) -> None:
        try:
            os.makedirs(settings_dir(), exist_ok=True)
            tmp = STATE_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(asdict(self), f, ensure_ascii=False, indent=1)
            os.replace(tmp, STATE_PATH)
        except OSError:
            pass

    def add(self, record: RunRecord) -> None:
        self.runs = ([asdict(record)] + self.runs)[:40]
        self.total_freed += record.freed + record.trash_freed

    @property
    def last_run(self) -> Optional[dict]:
        return self.runs[0] if self.runs else None


# --------------------------------------------------------------------------- #
#  القياس والتنظيف
# --------------------------------------------------------------------------- #


def _skipped(path: str) -> bool:
    name = os.path.basename(path.rstrip("/")).lower()
    return name.startswith(_SKIP_NAMES) or is_protected(path)


def measure(ctx: JobContext = NULL_CONTEXT, categories: Optional[List[str]] = None
            ) -> Dict[Category, List[FileItem]]:
    """فحص الفئات المختارة + سلة المحذوفات."""
    cats = {Category(c) for c in (categories or [c.value for c in AUTO_CATEGORIES])} | {Category.TRASH}
    targets = [t for t in junk_targets() if t.category in cats]
    result = scan_junk(ctx, targets)
    for cat in list(result):
        result[cat] = [i for i in result[cat] if not _skipped(i.path)]
    return result


def _delete_old_files(path: str, cutoff: float, dry_run: bool) -> tuple:
    """يحذف الملفات الأقدم من cutoff داخل path. يُرجع (المحرَّر، عدد الملفات)."""
    freed = files = 0

    def handle(file_path: str, st) -> None:
        nonlocal freed, files
        if max(st.st_mtime, st.st_atime) >= cutoff:   # استُخدم أو عُدّل مؤخراً → نتركه
            return
        if not dry_run:
            try:
                os.remove(file_path)
            except OSError:
                return
        freed += st.st_size
        files += 1

    try:
        st = os.lstat(path)
    except OSError:
        return 0, 0
    if not stat.S_ISDIR(st.st_mode):
        handle(path, st)
        return freed, files
    for root, dirs, names in os.walk(path, topdown=False):
        for name in names:
            fp = os.path.join(root, name)
            try:
                handle(fp, os.lstat(fp))
            except OSError:
                continue
        if not dry_run and root != path:
            try:
                os.rmdir(root)       # يحذف المجلد فقط إن أصبح فارغاً
            except OSError:
                pass
    return freed, files


def _empty_old_trash(items: List[FileItem], days: int, dry_run: bool) -> int:
    """حذف ما في السلة منذ أكثر من days يوماً (ctime = وقت النقل إلى السلة تقريباً)."""
    from .actions import delete_permanently
    cutoff = time.time() - days * DAY
    freed = 0
    for item in items:
        try:
            if os.lstat(item.path).st_ctime >= cutoff:
                continue
            if not dry_run:
                delete_permanently(item.path)
            freed += item.size
        except Exception:
            continue
    return freed


def run_autoclean(ctx: JobContext = NULL_CONTEXT, settings: Optional[Settings] = None,
                  force: bool = False, dry_run: bool = False) -> RunRecord:
    s = settings or Settings.load()
    ctx.progress(None, "قياس حجم الكاش والمهملات...", force=True)
    found = measure(ctx.sub(0.0, 0.6), s.auto_categories)
    selected = [Category(c) for c in s.auto_categories]
    measured = sum(i.size for c in selected for i in found.get(c, []))
    threshold = s.auto_threshold_mb * 1_000_000
    triggered = force or measured >= threshold

    freed = files = 0
    if triggered:
        cutoff = time.time() - s.auto_min_age_days * DAY
        items = [i for c in selected for i in found.get(c, [])]
        for n, item in enumerate(items):
            if ctx.cancelled:
                break
            ctx.progress(0.6 + 0.35 * n / max(len(items), 1), f"تنظيف {item.name}...")
            f, k = _delete_old_files(item.path, cutoff, dry_run)
            freed += f
            files += k

    trash_freed = 0
    if s.auto_trash_days:
        trash_freed = _empty_old_trash(found.get(Category.TRASH, []), s.auto_trash_days, dry_run)

    _total, _used, free = disk_usage("/")
    note = "تجربة بدون حذف" if dry_run else ""
    record = RunRecord(time.time(), measured, freed, trash_freed, files, triggered, free, note)

    if not dry_run:
        state = AutoState.load()
        state.add(record)
        # تنبيه المساحة المنخفضة (مرة كل 12 ساعة كحد أقصى)
        if s.low_disk_alert_gb and free < s.low_disk_alert_gb * 1_000_000_000 and \
                time.time() - state.last_low_disk_alert > 12 * 3600:
            state.last_low_disk_alert = time.time()
            notify("⚠️ المساحة على وشك النفاد",
                   f"المتبقي {human_size(free)} فقط. افتح Disk Cleaner Pro لتحرير مساحة.")
        state.save()
        if s.auto_notify and (freed + trash_freed) > 0:
            parts = []
            if freed:
                parts.append(f"الكاش والمهملات: {human_size(freed)}")
            if trash_freed:
                parts.append(f"السلة: {human_size(trash_freed)}")
            notify("🧹 تنظيف تلقائي", f"تم تحرير {human_size(freed + trash_freed)} — " + "، ".join(parts))
    ctx.progress(1.0, "", force=True)
    return record


def category_labels(keys: List[str]) -> str:
    return "، ".join(CATEGORY_INFO[Category(k)].label for k in keys)


# --------------------------------------------------------------------------- #
#  الإشعارات
# --------------------------------------------------------------------------- #


def notify(title: str, text: str) -> None:
    if IS_MAC:
        osascript(f"display notification {applescript_quote(text)} with title "
                  f"{applescript_quote('Disk Cleaner Pro')} subtitle {applescript_quote(title)}", timeout=10)


# --------------------------------------------------------------------------- #
#  وكيل macOS (LaunchAgent) لتشغيل التنظيف والبرنامج مغلق
# --------------------------------------------------------------------------- #


def program_arguments() -> List[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--autoclean"]
    main = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                        "main.py")
    return [sys.executable, main, "--autoclean"]


def agent_installed() -> bool:
    return os.path.exists(AGENT_PATH)


def install_agent(interval_hours: int) -> tuple:
    """تثبيت/تحديث الوكيل. يُرجع (نجح؟، رسالة)."""
    if not IS_MAC:
        return False, "التنظيف التلقائي في الخلفية متاح على macOS فقط."
    plist = {
        "Label": AGENT_LABEL,
        "ProgramArguments": program_arguments(),
        "StartInterval": max(1, int(interval_hours)) * 3600,
        "RunAtLoad": False,
        "ProcessType": "Background",
        "LowPriorityIO": True,
        "Nice": 10,
        "StandardOutPath": os.path.join(settings_dir(), "autoclean.log"),
        "StandardErrorPath": os.path.join(settings_dir(), "autoclean.log"),
    }
    try:
        os.makedirs(os.path.dirname(AGENT_PATH), exist_ok=True)
        os.makedirs(settings_dir(), exist_ok=True)
        domain = f"gui/{os.getuid()}"
        run(["launchctl", "bootout", f"{domain}/{AGENT_LABEL}"], timeout=10)
        with open(AGENT_PATH, "wb") as f:
            plistlib.dump(plist, f)
        code, out = run(["launchctl", "bootstrap", domain, AGENT_PATH], timeout=10)
        if code != 0:
            return False, out.strip() or "تعذّر تفعيل الوكيل."
        return True, ""
    except OSError as exc:
        return False, str(exc)


def uninstall_agent() -> None:
    if IS_MAC:
        run(["launchctl", "bootout", f"gui/{os.getuid()}/{AGENT_LABEL}"], timeout=10)
    try:
        os.remove(AGENT_PATH)
    except OSError:
        pass


def ensure_agent(settings: Settings) -> None:
    """يُستدعى عند فتح البرنامج: يحدّث الوكيل لو تغيّر مكان التطبيق أو الإعدادات."""
    if not IS_MAC:
        return
    if not settings.auto_enabled:
        if agent_installed():
            uninstall_agent()
        return
    try:
        with open(AGENT_PATH, "rb") as f:
            current = plistlib.load(f)
        if (current.get("ProgramArguments") == program_arguments()
                and current.get("StartInterval") == settings.auto_interval_hours * 3600):
            return
    except Exception:
        pass
    install_agent(settings.auto_interval_hours)


def cli_main() -> int:
    """نقطة الدخول عند التشغيل بـ --autoclean (بدون واجهة)."""
    s = Settings.load()
    if not s.auto_enabled:
        return 0
    record = run_autoclean(NULL_CONTEXT, s)
    print(time.strftime("%Y-%m-%d %H:%M"), f"measured={human_size(record.measured)}",
          f"freed={human_size(record.freed)}", f"trash={human_size(record.trash_freed)}",
          f"triggered={record.triggered}", flush=True)
    return 0

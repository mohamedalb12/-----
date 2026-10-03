"""
maintenance.py — مهام صيانة النظام (مثل قسم Maintenance في CleanMyMac).

المهام التي تحتاج صلاحيات المدير تُجمَّع وتُنفَّذ بطلب كلمة سر واحد فقط.
"""

from __future__ import annotations

import glob
import os
import sqlite3
import sys
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from .jobs import JobContext
from .shell import is_process_running, join_cmd, run, run_admin_script

IS_MAC = sys.platform == "darwin"
HOME = os.path.expanduser("~")
LSREGISTER = ("/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework"
              "/Support/lsregister")


@dataclass
class MaintenanceTask:
    key: str
    icon: str
    title: str
    description: str
    commands: List[List[str]] = field(default_factory=list)
    admin: bool = False
    recommended: bool = False
    python: Optional[Callable[[], str]] = None     # مهمة تُنفَّذ بكود Python
    available: bool = True


def _speed_up_mail() -> str:
    """ضغط قاعدة بيانات Mail (Envelope Index) لتسريع البحث وفتح الرسائل."""
    if is_process_running("Mail"):
        raise RuntimeError("أغلق تطبيق Mail أولاً.")
    dbs = glob.glob(os.path.join(HOME, "Library/Mail/V*/MailData/Envelope Index"))
    if not dbs:
        raise RuntimeError("لم يتم العثور على قاعدة بيانات Mail (قد تحتاج «الوصول الكامل للقرص»).")
    saved = 0
    for db in dbs:
        before = os.path.getsize(db)
        con = sqlite3.connect(db, timeout=10)
        try:
            con.execute("VACUUM")
        finally:
            con.close()
        saved += max(0, before - os.path.getsize(db))
    from .models import human_size
    return f"تم ضغط قاعدة البيانات وتوفير {human_size(saved)}"


def all_tasks() -> List[MaintenanceTask]:
    tasks = [
        MaintenanceTask("ram", "🧠", "تحرير الذاكرة (RAM)",
                        "يفرّغ الذاكرة غير النشطة لتستفيد منها التطبيقات المفتوحة.",
                        [["purge"]], admin=True, recommended=True,
                        available=os.path.exists("/usr/sbin/purge")),
        MaintenanceTask("dns", "🌐", "مسح ذاكرة DNS المؤقتة",
                        "يحل مشاكل فتح بعض المواقع بعد تغيير الشبكة.",
                        [["dscacheutil", "-flushcache"], ["killall", "-HUP", "mDNSResponder"]],
                        admin=True, recommended=True),
        MaintenanceTask("periodic", "🗓", "تشغيل سكربتات الصيانة",
                        "ينظّف سجلات النظام والملفات المؤقتة القديمة (daily / weekly / monthly).",
                        [["periodic", "daily", "weekly", "monthly"]], admin=True, recommended=True,
                        available=os.path.exists("/usr/sbin/periodic")),
        MaintenanceTask("snapshots", "⏱", "حذف لقطات Time Machine المحلية",
                        "يحرّر المساحة التي تشغلها النسخ الاحتياطية المؤقتة على القرص.",
                        [["tmutil", "thinlocalsnapshots", "/", "999999999999", "4"]], admin=True),
        MaintenanceTask("spotlight", "🔎", "إعادة فهرسة Spotlight",
                        "يصلح البحث عندما لا يجد Spotlight ملفاتك. قد يستغرق بعض الوقت في الخلفية.",
                        [["mdutil", "-E", "/"]], admin=True),
        MaintenanceTask("launchservices", "🗂", "إعادة بناء قاعدة Launch Services",
                        "يصلح قائمة «فتح باستخدام» المكررة والأيقونات الخاطئة للملفات.",
                        [[LSREGISTER, "-r", "-domain", "local", "-domain", "system", "-domain", "user"]],
                        available=os.path.exists(LSREGISTER)),
        MaintenanceTask("quicklook", "👁", "تحديث ذاكرة المعاينة السريعة",
                        "يصلح الصور المصغّرة ومعاينات Quick Look التي لا تظهر.",
                        [["qlmanage", "-r", "cache"], ["qlmanage", "-r"]]),
        MaintenanceTask("mail", "✉️", "تسريع تطبيق Mail",
                        "يضغط قاعدة بيانات Mail لتسريع البحث وتحميل الرسائل (أغلق Mail أولاً).",
                        python=_speed_up_mail),
        MaintenanceTask("fonts", "🔤", "إعادة بناء ذاكرة الخطوط",
                        "يصلح الخطوط المشوّهة أو التي لا تظهر. أعد تشغيل الجهاز بعدها.",
                        [["atsutil", "databases", "-remove"]], admin=True),
    ]
    if not IS_MAC:
        for t in tasks:
            t.available = t.python is not None
    return [t for t in tasks if t.available]


def run_tasks(ctx: JobContext, keys: List[str]) -> Dict[str, Tuple[bool, str]]:
    """تنفيذ المهام المحددة. يُرجع {key: (نجحت؟, رسالة)}."""
    tasks = [t for t in all_tasks() if t.key in keys]
    results: Dict[str, Tuple[bool, str]] = {}
    total = len(tasks) or 1
    done = 0

    # 1) مهام المدير: سكربت واحد = كلمة سر واحدة
    admin = [t for t in tasks if t.admin]
    if admin:
        ctx.progress(0.05, "في انتظار كلمة سر المدير...", force=True)
        parts = []
        for t in admin:
            inner = " && ".join(join_cmd(c) for c in t.commands)
            parts.append(f"( ( {inner} ) >/dev/null 2>&1 && echo OK:{t.key} || echo FAIL:{t.key} )")
        code, out = run_admin_script(" ; ".join(parts), "Disk Cleaner Pro يحتاج كلمة السر لتنفيذ الصيانة.")
        for t in admin:
            if code == 128:
                results[t.key] = (False, out)
            elif f"OK:{t.key}" in out:
                results[t.key] = (True, "تم بنجاح")
            else:
                results[t.key] = (False, "تعذّر التنفيذ" + (f": {out.strip()[:200]}" if code else ""))
        done += len(admin)

    # 2) المهام العادية
    for t in tasks:
        if t.admin or ctx.cancelled:
            continue
        ctx.progress(done / total, f"{t.title}...", force=True)
        try:
            if t.python:
                results[t.key] = (True, t.python())
            else:
                ok, msg = True, "تم بنجاح"
                for cmd in t.commands:
                    code, out = run(cmd, timeout=300)
                    if code != 0:
                        ok, msg = False, out.strip()[:200] or f"رمز الخروج {code}"
                results[t.key] = (ok, msg)
        except Exception as exc:
            results[t.key] = (False, str(exc))
        done += 1
    ctx.progress(1.0, "", force=True)
    return results

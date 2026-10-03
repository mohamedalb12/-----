"""
file_actions.py
===============
العمليات على الملفات: الفتح، الإظهار في Finder، النقل إلى سلة المحذوفات، والحذف النهائي.

مكتوبة بحيث تعمل على macOS بشكل أساسي، مع دعم ويندوز ولينكس أيضاً.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

IS_MAC = sys.platform == "darwin"
IS_WINDOWS = sys.platform.startswith("win")

# مسارات نظام لا يُسمح بحذف أي شيء بداخلها (حماية إضافية من الحذف الخاطئ)
if IS_MAC:
    _PROTECTED_PREFIXES = ("/System/", "/bin/", "/sbin/", "/usr/bin/", "/usr/sbin/",
                           "/usr/lib/", "/usr/libexec/", "/private/var/db/")
elif IS_WINDOWS:
    _PROTECTED_PREFIXES = ("c:\\windows\\", "c:\\program files\\windowsapps\\")
else:
    _PROTECTED_PREFIXES = ("/bin/", "/sbin/", "/usr/bin/", "/usr/sbin/", "/usr/lib/",
                           "/lib/", "/lib64/", "/boot/", "/etc/")


class FileActionError(Exception):
    """خطأ مفهوم للمستخدم يُعرض في نافذة رسالة."""


def is_protected(path: str) -> bool:
    """هل الملف داخل مجلد نظام محمي؟"""
    p = os.path.abspath(path)
    if IS_WINDOWS:
        p = p.lower()
    return p.startswith(_PROTECTED_PREFIXES)


def _run(cmd: list) -> None:
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=30)
    except FileNotFoundError as exc:
        raise FileActionError(f"الأمر غير موجود: {cmd[0]}") from exc
    except subprocess.CalledProcessError as exc:
        msg = (exc.stderr or b"").decode(errors="ignore").strip()
        raise FileActionError(msg or f"فشل تنفيذ الأمر: {' '.join(cmd)}") from exc
    except subprocess.TimeoutExpired as exc:
        raise FileActionError("انتهت مهلة تنفيذ الأمر.") from exc


def _ensure_exists(path: str) -> None:
    if not os.path.lexists(path):
        raise FileActionError(f"الملف لم يعد موجوداً:\n{path}")


def open_file(path: str) -> None:
    """فتح الملف بالبرنامج الافتراضي في النظام."""
    _ensure_exists(path)
    if IS_MAC:
        _run(["open", path])
    elif IS_WINDOWS:
        os.startfile(path)  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["xdg-open", path])


def reveal_in_folder(path: str) -> None:
    """فتح المجلد الذي يحتوي الملف مع تحديده (Finder / Explorer)."""
    _ensure_exists(path)
    if IS_MAC:
        _run(["open", "-R", path])           # -R = Reveal في Finder
    elif IS_WINDOWS:
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
    else:
        subprocess.Popen(["xdg-open", os.path.dirname(path)])


def move_to_trash(path: str) -> None:
    """
    نقل الملف إلى سلة المحذوفات (يمكن استرجاعه لاحقاً).
    نستخدم مكتبة Send2Trash، وعلى ماك نلجأ إلى Finder عبر AppleScript إذا فشلت.
    """
    _ensure_exists(path)
    if is_protected(path):
        raise FileActionError("هذا الملف داخل مجلد نظام محمي ولا يمكن حذفه.")

    error = None
    try:
        from send2trash import send2trash
        send2trash(path)
        return
    except ImportError:
        error = FileActionError("مكتبة Send2Trash غير مثبتة. نفّذ: pip install Send2Trash")
    except Exception as exc:  # مثل OSError أو خطأ صلاحيات
        error = exc

    if IS_MAC:
        # الطريقة البديلة: نطلب من Finder نقل الملف (يدعم "إرجاع" من السلة)
        escaped = path.replace("\\", "\\\\").replace('"', '\\"')
        script = f'tell application "Finder" to delete (POSIX file "{escaped}" as alias)'
        _run(["osascript", "-e", script])
        return

    raise FileActionError(f"تعذّر النقل إلى سلة المحذوفات:\n{error}")


def delete_permanently(path: str) -> None:
    """حذف نهائي لا يمكن التراجع عنه."""
    _ensure_exists(path)
    if is_protected(path):
        raise FileActionError("هذا الملف داخل مجلد نظام محمي ولا يمكن حذفه.")
    try:
        if os.path.isdir(path) and not os.path.islink(path):
            shutil.rmtree(path)
        else:
            os.remove(path)
    except PermissionError as exc:
        raise FileActionError(f"لا توجد صلاحية لحذف الملف:\n{path}") from exc
    except OSError as exc:
        raise FileActionError(f"تعذّر حذف الملف:\n{exc}") from exc

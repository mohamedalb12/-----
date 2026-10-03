"""
actions.py — العمليات على الملفات والنظام.

فتح الملف، إظهاره في Finder، المعاينة السريعة (Quick Look)، النقل إلى السلة،
الحذف النهائي، إفراغ السلة، ومعلومات الجهاز والقرص.
"""

from __future__ import annotations

import os
import platform
import shutil
import socket
import subprocess
import sys
from typing import List, Tuple

from .jobs import JobContext
from .models import FileItem

IS_MAC = sys.platform == "darwin"
IS_WINDOWS = sys.platform.startswith("win")
HOME = os.path.expanduser("~")

if IS_MAC:
    _PROTECTED_PREFIXES = ("/System/", "/bin/", "/sbin/", "/usr/bin/", "/usr/sbin/", "/usr/lib/",
                           "/usr/libexec/", "/private/var/db/", "/Library/Apple/")
elif IS_WINDOWS:
    _PROTECTED_PREFIXES = ("c:\\windows\\", "c:\\program files\\windowsapps\\")
else:
    _PROTECTED_PREFIXES = ("/bin/", "/sbin/", "/usr/bin/", "/usr/sbin/", "/usr/lib/", "/lib/",
                           "/lib64/", "/boot/", "/etc/")

# مجلدات لا يُسمح بحذفها هي نفسها أبداً
_PROTECTED_EXACT = {
    "/", HOME, os.path.join(HOME, "Library"), os.path.join(HOME, "Documents"),
    os.path.join(HOME, "Desktop"), os.path.join(HOME, "Downloads"), os.path.join(HOME, "Pictures"),
    os.path.join(HOME, "Movies"), os.path.join(HOME, "Music"), "/Applications", "/Library",
    "/Users", "/System", "/private", "/usr", "/opt", os.path.join(HOME, ".Trash"),
}


class FileActionError(Exception):
    """خطأ مفهوم للمستخدم."""


def is_protected(path: str) -> bool:
    p = os.path.abspath(path).rstrip(os.sep) or os.sep
    if p in _PROTECTED_EXACT:
        return True
    check = p.lower() if IS_WINDOWS else p
    return (check + os.sep).startswith(_PROTECTED_PREFIXES)


def is_in_trash(path: str) -> bool:
    p = path.replace("\\", "/")
    return "/.Trash/" in p or "/.Trashes/" in p or "/.local/share/Trash/" in p


def _run(cmd: List[str], timeout: int = 60) -> None:
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=timeout)
    except FileNotFoundError as exc:
        raise FileActionError(f"الأمر غير موجود: {cmd[0]}") from exc
    except subprocess.CalledProcessError as exc:
        msg = (exc.stderr or b"").decode(errors="ignore").strip()
        raise FileActionError(msg or "فشل تنفيذ العملية.") from exc
    except subprocess.TimeoutExpired as exc:
        raise FileActionError("انتهت مهلة تنفيذ العملية.") from exc


def _ensure_exists(path: str) -> None:
    if not os.path.lexists(path):
        raise FileActionError(f"الملف لم يعد موجوداً:\n{path}")


def open_file(path: str) -> None:
    _ensure_exists(path)
    if IS_MAC:
        _run(["open", path])
    elif IS_WINDOWS:
        os.startfile(path)  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["xdg-open", path])


def reveal_in_folder(path: str) -> None:
    _ensure_exists(path)
    if IS_MAC:
        _run(["open", "-R", path])
    elif IS_WINDOWS:
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
    else:
        subprocess.Popen(["xdg-open", os.path.dirname(path)])


def quick_look(path: str) -> None:
    """معاينة سريعة مثل زر المسافة في Finder."""
    _ensure_exists(path)
    if IS_MAC:
        subprocess.Popen(["qlmanage", "-p", path], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
    else:
        open_file(path)


def move_to_trash(path: str) -> None:
    _ensure_exists(path)
    if is_protected(path):
        raise FileActionError("هذا العنصر محمي ولا يمكن حذفه.")
    if is_in_trash(path):  # موجود في السلة بالفعل: الحذف منها نهائي
        delete_permanently(path)
        return
    error = None
    try:
        from send2trash import send2trash
        send2trash(path)
        return
    except ImportError:
        error = FileActionError("مكتبة Send2Trash غير مثبتة.")
    except Exception as exc:
        error = exc
    if IS_MAC:
        # بديل: Finder (يطلب كلمة سر المدير تلقائياً للملفات المملوكة للنظام)
        escaped = path.replace("\\", "\\\\").replace('"', '\\"')
        _run(["osascript", "-e",
              f'tell application "Finder" to delete (POSIX file "{escaped}" as alias)'], timeout=300)
        return
    raise FileActionError(f"تعذّر النقل إلى سلة المحذوفات:\n{error}")


def delete_permanently(path: str) -> None:
    _ensure_exists(path)
    if is_protected(path):
        raise FileActionError("هذا العنصر محمي ولا يمكن حذفه.")
    try:
        if os.path.isdir(path) and not os.path.islink(path):
            shutil.rmtree(path)
        else:
            os.remove(path)
    except PermissionError as exc:
        raise FileActionError(f"لا توجد صلاحية لحذف:\n{path}") from exc
    except OSError as exc:
        raise FileActionError(f"تعذّر الحذف:\n{exc}") from exc


def delete_items(ctx: JobContext, items: List[FileItem], mode: str
                 ) -> Tuple[List[FileItem], List[Tuple[FileItem, str]]]:
    """حذف مجموعة عناصر في الخلفية. يُرجع (ما حُذف، [(ما فشل، السبب)])."""
    action = move_to_trash if mode == "trash" else delete_permanently
    deleted, failed = [], []
    for n, item in enumerate(items):
        if ctx.cancelled:
            break
        ctx.progress(n / max(len(items), 1), f"جارٍ حذف {item.name}...")
        try:
            action(item.path)
            deleted.append(item)
        except FileActionError as exc:
            failed.append((item, str(exc)))
        except Exception as exc:
            failed.append((item, f"{exc}"))
    ctx.progress(1.0, "", force=True)
    return deleted, failed


def empty_trash() -> None:
    if IS_MAC:
        _run(["osascript", "-e", 'tell application "Finder" to empty trash'], timeout=600)
    else:
        trash = os.path.join(HOME, ".local/share/Trash/files")
        for name in os.listdir(trash):
            delete_permanently(os.path.join(trash, name))


# --------------------------------------------------------------------------- #
#  معلومات النظام
# --------------------------------------------------------------------------- #


def disk_usage(path: str = "/") -> Tuple[int, int, int]:
    """(الإجمالي، المستخدم، الحر)."""
    if IS_MAC and path == "/" and os.path.exists("/System/Volumes/Data"):
        path = "/System/Volumes/Data"
    u = shutil.disk_usage(path)
    return u.total, u.total - u.free, u.free


def computer_name() -> str:
    if IS_MAC:
        try:
            out = subprocess.run(["scutil", "--get", "ComputerName"], capture_output=True,
                                 text=True, timeout=3)
            if out.stdout.strip():
                return out.stdout.strip()
        except Exception:
            pass
    return socket.gethostname().split(".")[0]


def os_description() -> str:
    if IS_MAC:
        ver = platform.mac_ver()[0]
        return f"macOS {ver}" if ver else "macOS"
    return f"{platform.system()} {platform.release()}"


def has_full_disk_access() -> bool:
    """هل لدى البرنامج صلاحية «الوصول الكامل للقرص» في macOS؟"""
    if not IS_MAC:
        return True
    for probe in ("Library/Safari", "Library/Mail", "Library/Application Support/com.apple.TCC"):
        path = os.path.join(HOME, probe)
        if os.path.exists(path):
            try:
                os.listdir(path)
                return True
            except PermissionError:
                return False
            except OSError:
                continue
    return True


def open_full_disk_access_settings() -> None:
    if IS_MAC:
        subprocess.Popen(["open",
                          "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles"])

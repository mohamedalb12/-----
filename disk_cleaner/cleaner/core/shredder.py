"""
shredder.py — آلة التمزيق (مثل Shredder في CleanMyMac).

يحذف الملفات نهائياً بعد الكتابة فوق محتواها ببيانات عشوائية وتغيير اسمها،
ويتعامل مع الملفات «العالقة» المقفلة (chflags uchg) التي يرفض Finder حذفها.

ملاحظة صريحة: على أقراص SSD (كل أجهزة ماك الحديثة) لا يضمن أي برنامج أن الكتابة
فوق الملف تصل لنفس الخلايا الفعلية. الحماية الحقيقية هي تفعيل FileVault، فعندها
تكون أي بيانات محذوفة غير قابلة للاسترجاع أصلاً.
"""

from __future__ import annotations

import os
import secrets
import stat
from typing import List, Tuple

from .actions import is_protected
from .jobs import JobContext
from .shell import run

CHUNK = 1024 * 1024


def _unlock(path: str) -> None:
    run(["chflags", "-R", "nouchg,noschg", path], timeout=30)
    try:
        os.chmod(path, os.stat(path, follow_symlinks=False).st_mode | stat.S_IWUSR)
    except OSError:
        pass


def _shred_file(path: str, ctx: JobContext) -> None:
    size = os.path.getsize(path)
    if size and not os.path.islink(path):
        with open(path, "r+b", buffering=0) as f:
            written = 0
            while written < size:
                if ctx.cancelled:
                    raise InterruptedError
                n = min(CHUNK, size - written)
                f.write(os.urandom(n))
                written += n
            f.flush()
            os.fsync(f.fileno())
    # اسم عشوائي حتى لا يبقى الاسم الأصلي في سجلات نظام الملفات
    new = os.path.join(os.path.dirname(path), secrets.token_hex(8))
    os.rename(path, new)
    os.remove(new)


def shred_paths(ctx: JobContext, paths: List[str]) -> Tuple[List[str], List[Tuple[str, str]]]:
    done, failed = [], []
    for n, path in enumerate(paths):
        ctx.progress(n / max(len(paths), 1), f"تمزيق {os.path.basename(path)}...", force=True)
        try:
            if is_protected(path):
                raise PermissionError("عنصر محمي لا يمكن تمزيقه.")
            _unlock(path)
            if os.path.isdir(path) and not os.path.islink(path):
                for root, dirs, files in os.walk(path, topdown=False):
                    for name in files:
                        _shred_file(os.path.join(root, name), ctx)
                    for name in dirs:
                        full = os.path.join(root, name)
                        if os.path.islink(full):
                            os.remove(full)
                        else:
                            os.rmdir(full)
                os.rmdir(path)
            else:
                _shred_file(path, ctx)
            done.append(path)
        except InterruptedError:
            failed.append((path, "تم الإيقاف"))
            break
        except Exception as exc:
            failed.append((path, str(exc)))
    ctx.progress(1.0, "", force=True)
    return done, failed

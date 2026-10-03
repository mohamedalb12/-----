"""
shell.py — تشغيل أوامر النظام بأمان.

run()        أمر عادي مع مهلة زمنية، لا يرمي استثناءات (يُرجع رمز الخروج والمخرجات).
run_admin()  أوامر تحتاج صلاحيات المدير: macOS يعرض نافذة كلمة السر الرسمية مرة واحدة
             لكل مجموعة أوامر (عبر AppleScript «with administrator privileges»).
"""

from __future__ import annotations

import shlex
import subprocess
import sys
from typing import List, Tuple

IS_MAC = sys.platform == "darwin"


def run(cmd: List[str], timeout: float = 30, input_text: str = None) -> Tuple[int, str]:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, input=input_text)
        return out.returncode, (out.stdout or "") + (out.stderr or "")
    except FileNotFoundError:
        return 127, f"الأمر غير موجود: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, "انتهت المهلة"
    except OSError as exc:
        return 1, str(exc)


def applescript_quote(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def osascript(script: str, timeout: float = 60) -> Tuple[int, str]:
    return run(["osascript", "-e", script], timeout=timeout)


def run_admin(commands: List[List[str]], prompt: str = "", timeout: float = 900) -> Tuple[int, str]:
    """
    تنفيذ عدة أوامر بصلاحيات المدير بطلب كلمة سر واحد.
    رمز 128 = ألغى المستخدم نافذة كلمة السر.
    """
    if not commands:
        return 0, ""
    return run_admin_script(" ; ".join(join_cmd(cmd) for cmd in commands), prompt, timeout)


def join_cmd(cmd: List[str]) -> str:
    return " ".join(shlex.quote(part) for part in cmd)


def run_admin_script(shell_line: str, prompt: str = "", timeout: float = 900) -> Tuple[int, str]:
    """تنفيذ سطر shell كامل بصلاحيات المدير."""
    if not IS_MAC:
        return run(["sudo", "-n", "sh", "-c", shell_line], timeout=timeout)
    script = f"do shell script {applescript_quote(shell_line)} with administrator privileges"
    if prompt:
        script += f" with prompt {applescript_quote(prompt)}"
    code, out = osascript(script, timeout=timeout)
    if code != 0 and "-128" in out:
        return 128, "تم إلغاء طلب كلمة السر."
    return code, out


def is_process_running(name: str) -> bool:
    code, _ = run(["pgrep", "-x", name], timeout=5)
    return code == 0


def quit_app_named(name: str) -> None:
    if IS_MAC:
        osascript(f"tell application {applescript_quote(name)} to quit", timeout=20)

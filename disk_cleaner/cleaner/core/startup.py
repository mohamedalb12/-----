"""
startup.py — عناصر بدء التشغيل والوكلاء الخلفيون (مثل قسم Optimization في CleanMyMac).

- عناصر تسجيل الدخول: التطبيقات التي تفتح تلقائياً (عبر System Events).
- الوكلاء الخلفيون (Launch Agents/Daemons): برامج صغيرة تعمل في الخلفية دائماً،
  غالباً للتحديث التلقائي. يمكن إيقافها أو تشغيلها أو حذفها.
"""

from __future__ import annotations

import os
import plistlib
import re
import sys
from dataclasses import dataclass
from typing import List, Optional, Set, Tuple

from .jobs import JobContext, NULL_CONTEXT
from .shell import applescript_quote, join_cmd, osascript, run, run_admin_script

IS_MAC = sys.platform == "darwin"
HOME = os.path.expanduser("~")

LAUNCH_DIRS = [
    (os.path.join(HOME, "Library/LaunchAgents"), "user"),
    ("/Library/LaunchAgents", "agent"),
    ("/Library/LaunchDaemons", "daemon"),
]
SCOPE_LABEL = {"user": "وكيل للمستخدم", "agent": "وكيل لكل المستخدمين", "daemon": "خدمة نظام"}


@dataclass
class LaunchItem:
    path: str
    label: str
    program: str
    scope: str
    enabled: bool = True
    run_at_load: bool = False
    keep_alive: bool = False
    program_exists: bool = True

    @property
    def needs_admin(self) -> bool:
        return self.scope != "user"

    @property
    def vendor(self) -> str:
        parts = self.label.split(".")
        return ".".join(parts[:2]) if len(parts) >= 2 else self.label


def _disabled_labels(domain: str) -> Set[str]:
    """العناصر المعطّلة في نطاق launchd معيّن."""
    code, out = run(["launchctl", "print-disabled", domain], timeout=10)
    if code != 0:
        return set()
    return {m.group(1) for m in re.finditer(r'"([^"]+)"\s*=>\s*(?:true|disabled)', out)}


def _user_domain() -> str:
    return f"gui/{os.getuid()}"


def list_launch_items(ctx: JobContext = NULL_CONTEXT) -> List[LaunchItem]:
    disabled_user = _disabled_labels(_user_domain()) if IS_MAC else set()
    disabled_system = _disabled_labels("system") if IS_MAC else set()
    items: List[LaunchItem] = []
    for folder, scope in LAUNCH_DIRS:
        try:
            names = sorted(os.listdir(folder))
        except OSError:
            continue
        for name in names:
            if not name.endswith(".plist"):
                continue
            path = os.path.join(folder, name)
            try:
                with open(path, "rb") as f:
                    data = plistlib.load(f)
            except Exception:
                ctx.error()
                data = {}
            label = str(data.get("Label") or name[:-6])
            program = str(data.get("Program") or (data.get("ProgramArguments") or [""])[0] or "")
            disabled = data.get("Disabled") is True or label in (
                disabled_user if scope == "user" else disabled_system)
            items.append(LaunchItem(
                path=path, label=label, program=program, scope=scope, enabled=not disabled,
                run_at_load=bool(data.get("RunAtLoad")), keep_alive=bool(data.get("KeepAlive")),
                program_exists=not program or os.path.exists(program)))
    return items


def _domain_cmds(item: LaunchItem, enable: bool) -> List[List[str]]:
    domain = _user_domain() if item.scope == "user" else "system" if item.scope == "daemon" else None
    if domain is None:
        # وكلاء /Library/LaunchAgents تعمل في جلسة كل مستخدم
        domain_user = _user_domain()
        return ([["launchctl", "enable", f"{domain_user}/{item.label}"],
                 ["launchctl", "bootstrap", domain_user, item.path]] if enable else
                [["launchctl", "disable", f"{domain_user}/{item.label}"],
                 ["launchctl", "bootout", f"{domain_user}/{item.label}"]])
    if enable:
        return [["launchctl", "enable", f"{domain}/{item.label}"],
                ["launchctl", "bootstrap", domain, item.path]]
    return [["launchctl", "disable", f"{domain}/{item.label}"],
            ["launchctl", "bootout", f"{domain}/{item.label}"]]


def set_enabled(item: LaunchItem, enable: bool) -> Tuple[bool, str]:
    """إيقاف/تشغيل عنصر. bootout/bootstrap قد يفشلان إن كان العنصر متوقفاً أصلاً، وهذا طبيعي."""
    cmds = _domain_cmds(item, enable)
    if item.scope == "daemon":
        line = " ; ".join(join_cmd(c) + " 2>/dev/null" for c in cmds[1:])
        code, out = run_admin_script(f"{join_cmd(cmds[0])} && ( {line} ; true )")
        return code == 0, out
    code, out = run(cmds[0])
    for c in cmds[1:]:
        run(c)
    return code == 0, out


def remove_item(item: LaunchItem) -> Tuple[bool, str]:
    """إيقاف العنصر ونقل ملفه إلى سلة المحذوفات."""
    stop = _domain_cmds(item, False)[1]
    if item.needs_admin:
        trash = os.path.join(HOME, ".Trash") + "/"
        code, out = run_admin_script(
            f"{join_cmd(stop)} 2>/dev/null ; {join_cmd(['mv', item.path, trash])} 2>/dev/null"
            f" || {join_cmd(['rm', '-f', item.path])}")
        return code == 0, out
    run(stop)
    from .actions import move_to_trash
    try:
        move_to_trash(item.path)
        return True, ""
    except Exception as exc:
        return False, str(exc)


# --------------------------------------------------------------------------- #
#  عناصر تسجيل الدخول
# --------------------------------------------------------------------------- #


@dataclass
class LoginItem:
    name: str
    path: str
    hidden: bool = False


def list_login_items() -> Tuple[List[LoginItem], Optional[str]]:
    """يُرجع (العناصر، رسالة خطأ إن وُجدت — مثلاً لم يُمنح إذن التحكم في System Events)."""
    if not IS_MAC:
        return [], None
    code, out = osascript(
        'tell application "System Events"\n'
        '  set out to ""\n'
        '  repeat with li in login items\n'
        '    set out to out & (name of li) & "\t" & (path of li) & "\t" & (hidden of li) & linefeed\n'
        '  end repeat\n'
        '  return out\n'
        'end tell', timeout=20)
    if code != 0:
        return [], "اسمح للبرنامج بالتحكم في «System Events» من إعدادات الخصوصية لعرض عناصر تسجيل الدخول."
    items = []
    for line in out.strip().splitlines():
        parts = line.split("\t")
        if len(parts) >= 2 and parts[0]:
            items.append(LoginItem(parts[0], parts[1], parts[2:3] == ["true"]))
    return items, None


def remove_login_item(name: str) -> Tuple[bool, str]:
    code, out = osascript(f'tell application "System Events" to delete login item {applescript_quote(name)}')
    return code == 0, out


def open_login_items_settings() -> None:
    if IS_MAC:
        run(["open", "x-apple.systempreferences:com.apple.LoginItems-Settings.extension"])

"""
selftest.py — اختبار ذاتي سريع يُشغَّل على أجهزة ماك الحقيقية في GitHub Actions:

    "Disk Cleaner Pro.app/Contents/MacOS/Disk Cleaner Pro" --selftest

يشغّل دوال الفحص الأساسية على النظام الحقيقي، ثم يفتح الواجهة ويتنقّل بين كل
الصفحات ويغلقها. يُرجع 0 عند النجاح و 1 عند أي خطأ.
"""

from __future__ import annotations

import os
import sys
import time
import traceback


def _step(name, fn, failures):
    start = time.monotonic()
    try:
        info = fn()
        print(f"  ✔ {name} ({time.monotonic() - start:.1f}s) {info or ''}", flush=True)
    except Exception:
        failures.append(name)
        print(f"  ✘ {name}\n{traceback.format_exc()}", flush=True)


def run_selftest() -> int:
    from .core import actions, apps, junk, space
    from .core.jobs import NULL_CONTEXT
    from .core.models import human_size

    failures = []
    print(f"Python {sys.version.split()[0]} on {sys.platform}", flush=True)

    _step("disk usage", lambda: [human_size(x) for x in actions.disk_usage("/")], failures)
    _step("system info", lambda: (actions.computer_name(), actions.os_description(),
                                  "FDA" if actions.has_full_disk_access() else "no FDA"), failures)
    _step("junk scan", lambda: {c.value: len(v) for c, v in junk.scan_junk(NULL_CONTEXT).items() if v},
          failures)

    def apps_test():
        found = apps.list_apps()
        if found:
            files = apps.find_app_files(found[0])
            icon = apps.load_icon(found[0].icon_file)
            return f"{len(found)} apps, first={found[0].name} files={len(files)} icon={icon is not None}"
        return "no apps"

    _step("apps", apps_test, failures)
    _step("orphans", lambda: f"{len(apps.find_orphans(NULL_CONTEXT))} items", failures)
    _step("space map", lambda: human_size(space.build_space_tree(
        NULL_CONTEXT, os.path.expanduser("~/Library/Caches"))[0].size), failures)

    def ui_test():
        from .ui.app import App
        from .ui.pages import PAGES

        app = App()
        errors = []
        app.report_callback_exception = lambda *exc: errors.append("".join(traceback.format_exception(*exc)))
        keys = [k for k, *_ in PAGES]

        def visit(i=0):
            if i < len(keys):
                app.show_page(keys[i])
                app.after(400, lambda: visit(i + 1))
            else:
                app.after(800, app.destroy)

        app.after(500, visit)
        app.after(30000, app.destroy)  # حماية من التعليق
        app.mainloop()
        if errors:
            raise RuntimeError("\n".join(errors))
        return f"{len(keys)} pages"

    _step("user interface", ui_test, failures)

    print("SELFTEST " + ("FAILED: " + ", ".join(failures) if failures else "PASSED"), flush=True)
    return 1 if failures else 0

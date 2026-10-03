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
    def protection():
        from .core import security
        checks = security.protection_checks()
        return ", ".join(f"{c.key}={c.ok}" for c in checks)

    def startup_items():
        from .core import startup
        items = startup.list_launch_items()
        return f"{len(items)} launch items, {sum(i.enabled for i in items)} enabled"

    def privacy_scan():
        from .core import privacy
        return {k: len(v) for k, v in privacy.scan_privacy(NULL_CONTEXT).items()}

    def threats():
        from .core import security
        return f"{len(security.scan_threats(NULL_CONTEXT))} findings"

    def extensions():
        from .core import extensions as ext
        return f"{sum(len(v) for v in ext.system_extensions().values())} system, " \
               f"{len(ext.browser_extensions())} browser"

    def monitor_sample():
        from .core import monitor
        from .core.jobs import Job
        import queue
        q = queue.Queue()
        job = Job(q, None, monitor.run_monitor, 0.5)
        job.start()
        sample = None
        deadline = time.time() + 10
        while time.time() < deadline and sample is None:
            try:
                _j, kind, payload = q.get(timeout=1)
                if kind == "sample":
                    sample = payload[0]
            except queue.Empty:
                pass
        job.cancel()
        assert sample is not None, "no sample"
        bh = monitor.battery_health()
        return f"cpu={sample.cpu:.0f}% mem={sample.mem_percent:.0f}% battery={bh}"

    def maintenance_list():
        from .core import maintenance
        return [t.key for t in maintenance.all_tasks()]

    def updates():
        from .core import updater
        ups, checked, total = updater.check_updates(NULL_CONTEXT)
        return f"{len(ups)} updates, checked {checked}/{total}"

    def shredder():
        import tempfile
        from .core.shredder import shred_paths
        d = tempfile.mkdtemp(dir=os.path.expanduser("~"))
        with open(os.path.join(d, "secret.txt"), "w") as f:
            f.write("x" * 5000)
        done, failed = shred_paths(NULL_CONTEXT, [d])
        assert done and not os.path.exists(d), failed
        return "ok"

    for name, fn in (("protection checks", protection), ("startup items", startup_items),
                     ("privacy scan", privacy_scan), ("threat scan", threats),
                     ("extensions", extensions), ("monitor", monitor_sample),
                     ("maintenance tasks", maintenance_list), ("updater", updates),
                     ("shredder", shredder)):
        _step(name, fn, failures)

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
                app.after(700, lambda: visit(i + 1))
            else:
                app.after(800, app.destroy)

        app.after(500, visit)
        app.after(60000, app.destroy)  # حماية من التعليق
        app.mainloop()
        if errors:
            raise RuntimeError("\n".join(errors))
        return f"{len(keys)} pages"

    _step("user interface", ui_test, failures)

    print("SELFTEST " + ("FAILED: " + ", ".join(failures) if failures else "PASSED"), flush=True)
    return 1 if failures else 0

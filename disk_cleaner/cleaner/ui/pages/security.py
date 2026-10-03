"""security.py — صفحة الحماية: إعدادات أمان macOS + فحص البرامج المزعجة والعناصر المشبوهة."""

from __future__ import annotations

from collections import defaultdict

import customtkinter as ctk

from ...core import security
from ...core.shell import run
from .. import theme as T
from ..checktree import CheckTree, Group
from ..widgets import Card, EmptyState, GradientButton, PageHeader, ProgressPanel
from .base import CallbackListener, Page

COLUMNS = (("info", "السبب", 330, "w"), ("size", "الحجم", 90, "e"), ("path", "المكان", 380, "w"))


class SecurityPage(Page):
    def __init__(self, master, app):
        super().__init__(master, app)
        self.loaded = False
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        header = PageHeader(self, "🛡", "الحماية",
                            "تحقّق من إعدادات أمان جهازك وابحث عن البرامج المزعجة والعناصر المشبوهة")
        header.grid(row=0, column=0, sticky="ew")
        self.scan_btn = GradientButton(header.actions, "🛡  فحص التهديدات", self.scan, width=180, height=40,
                                       font_size=14)
        self.scan_btn.pack()

        self.checks_frame = ctk.CTkFrame(self, fg_color="transparent", height=1)
        self.checks_frame.grid(row=1, column=0, sticky="ew", pady=(14, 0))
        for i in range(3):
            self.checks_frame.grid_columnconfigure(i, weight=1, uniform="c")

        self.progress = ProgressPanel(self, on_cancel=self.cancel_job)
        self.progress.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        self.progress.grid_remove()

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=3, column=0, sticky="nsew", pady=(10, 0))
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(0, weight=1)
        self.tree = CheckTree(body, COLUMNS, on_change=self._update_footer, actions=app.files,
                              info=lambda i: security.threat_parts(i)[1])
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.empty = EmptyState(body, "🛡", "افحص جهازك",
                                "نبحث عن برامج الإعلانات المزعجة المعروفة، والعناصر الخلفية غير الموقّعة "
                                "أو التي تعمل من مجلدات مؤقتة، وإضافات المتصفح الضارة.\n"
                                "ملاحظة: هذا فحص ذكي وليس مضاد فيروسات — ‏macOS يحتوي على XProtect الذي "
                                "يحذف البرمجيات الخبيثة المعروفة تلقائياً.")
        self.empty.grid(row=0, column=0, sticky="nsew")

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        self.summary = ctk.CTkLabel(footer, text="", font=T.font(13), text_color=T.MUTED)
        self.summary.pack(side="left")
        self.remove_btn = GradientButton(footer, "🗑  إزالة المحدد", self.remove, width=200, height=46,
                                         colors=T.GRADIENT_DANGER)
        self.remove_btn.pack(side="right")
        self._update_footer()

    def on_show(self):
        if not self.loaded:
            self.loaded = True
            self.app.run_job(CallbackListener(on_finished=self._show_checks, parent=self.app),
                             lambda ctx: security.protection_checks())

    def _show_checks(self, checks, _job):
        for w in self.checks_frame.winfo_children():
            w.destroy()
        for n, c in enumerate(checks or []):
            card = Card(self.checks_frame)
            card.grid(row=n // 3, column=n % 3, sticky="nsew", padx=5, pady=5)
            card.grid_columnconfigure(1, weight=1)
            icon = "✅" if c.ok else "⚠️" if c.ok is False else "❔"
            ctk.CTkLabel(card, text=icon, font=T.font(22)).grid(row=0, column=0, rowspan=2, padx=(14, 8), pady=10)
            ctk.CTkLabel(card, text=c.title, font=T.font(13, "bold"), anchor="w").grid(
                row=0, column=1, sticky="sw", pady=(10, 0))
            ctk.CTkLabel(card, text=c.detail, font=T.font(11), anchor="w", justify="left", wraplength=230,
                         text_color=T.MUTED if c.ok else T.WARNING).grid(row=1, column=1, sticky="nw",
                                                                         pady=(0, 10))
            if c.ok is False and c.settings_url:
                ctk.CTkButton(card, text="إصلاح", width=56, height=28,
                              command=lambda u=c.settings_url: run(["open", u])).grid(
                    row=0, column=2, rowspan=2, padx=10)

    def scan(self):
        self.scan_btn.configure_button(enabled=False)
        self.progress.grid()
        self.progress.start("جارٍ الفحص...")
        self.start_job(security.scan_threats)

    def on_progress(self, fraction, text):
        self.progress.update_progress(fraction, text)

    def on_finished(self, result, job):
        self.scan_btn.configure_button(enabled=True)
        self.progress.finish(self.summary_text(job, f"وُجد {len(result or [])} عنصر"))
        if result is None:
            return
        by_sev = defaultdict(list)
        for item in result:
            by_sev[security.threat_parts(item)[0]].append(item)
        groups = [Group(sev, security.SEVERITY_LABEL[sev], by_sev[sev], checked=sev == "high")
                  for sev in ("high", "medium", "low") if by_sev.get(sev)]
        self.tree.set_groups(groups, expand=True)
        if groups:
            self.empty.lower()
        else:
            self.empty.set("جهازك نظيف ✅", "لم نجد أي برامج مزعجة أو عناصر مشبوهة.")
            self.empty.lift()

    def _update_footer(self):
        items = self.tree.checked_items()
        self.summary.configure(text=f"المحدد: {len(items)} عنصر — أعد تشغيل الجهاز بعد الإزالة لإيقافها تماماً"
                               if items else "")
        self.remove_btn.configure_button(enabled=bool(items))

    def remove(self):
        self.app.delete_items(self.tree.checked_items(),
                              lambda d, f: self.tree.remove_paths({i.path for i in d}),
                              title="إزالة التهديدات", action_text="إزالة")

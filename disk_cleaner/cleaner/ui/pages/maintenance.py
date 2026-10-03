"""maintenance.py — صفحة الصيانة: مهام تحافظ على سرعة الجهاز واستقراره."""

from __future__ import annotations

import customtkinter as ctk

from ...core.maintenance import all_tasks, run_tasks
from .. import theme as T
from ..widgets import Card, GradientButton, PageHeader, ProgressPanel, show_toast
from .base import Page


class MaintenancePage(Page):
    def __init__(self, master, app):
        super().__init__(master, app)
        self.tasks = all_tasks()
        self.vars = {}
        self.status = {}
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        header = PageHeader(self, "🔧", "الصيانة",
                            "مهام تُصلح المشاكل الشائعة وتحافظ على سرعة جهازك — المهام المحددة موصى بها")
        header.grid(row=0, column=0, sticky="ew")

        self.progress = ProgressPanel(self)
        self.progress.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        self.progress.grid_remove()

        listing = ctk.CTkScrollableFrame(self, fg_color="transparent")
        listing.grid(row=2, column=0, sticky="nsew", pady=(12, 0))
        listing.grid_columnconfigure((0, 1), weight=1, uniform="t")
        for n, task in enumerate(self.tasks):
            card = Card(listing)
            card.grid(row=n // 2, column=n % 2, sticky="nsew", padx=6, pady=6)
            card.grid_columnconfigure(1, weight=1)
            var = ctk.BooleanVar(value=task.recommended)
            self.vars[task.key] = var
            ctk.CTkCheckBox(card, text="", variable=var, width=24).grid(row=0, column=0, rowspan=3,
                                                                       padx=(16, 4), pady=16)
            ctk.CTkLabel(card, text=f"{task.icon}  {task.title}", font=T.font(15, "bold"), anchor="w").grid(
                row=0, column=1, sticky="w", pady=(14, 0))
            ctk.CTkLabel(card, text=task.description, font=T.font(12), text_color=T.MUTED, anchor="w",
                         justify="left", wraplength=380).grid(row=1, column=1, sticky="w", padx=(0, 14))
            tag = "🔐 يحتاج كلمة السر" if task.admin else ""
            self.status[task.key] = ctk.CTkLabel(card, text=tag, font=T.font(12), text_color=T.FAINT,
                                                 anchor="w")
            self.status[task.key].grid(row=2, column=1, sticky="w", pady=(2, 12))

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        ctk.CTkLabel(footer, text="💡 المهام التي تحتاج كلمة السر تُنفَّذ معاً بطلب واحد فقط.",
                     font=T.font(12), text_color=T.MUTED).pack(side="left")
        self.run_btn = GradientButton(footer, "▶  تشغيل المهام المحددة", self.run, width=260, height=48)
        self.run_btn.pack(side="right")

    def run(self):
        keys = [k for k, v in self.vars.items() if v.get()]
        if not keys:
            return
        for k in keys:
            self.status[k].configure(text="⏳ في الانتظار...", text_color=T.MUTED)
        self.run_btn.configure_button(enabled=False)
        self.progress.grid()
        self.progress.start("جارٍ تنفيذ مهام الصيانة...")
        self.start_job(run_tasks, keys)

    def on_progress(self, fraction, text):
        self.progress.update_progress(fraction, text)

    def on_finished(self, result, job):
        self.run_btn.configure_button(enabled=True)
        self.progress.finish(self.summary_text(job))
        if not result:
            return
        ok_count = 0
        for key, (ok, msg) in result.items():
            ok_count += ok
            self.status[key].configure(text=("✅ " if ok else "⚠️ ") + (msg or ""),
                                       text_color=T.SUCCESS if ok else T.WARNING)
        if ok_count:
            show_toast(self.app, f"اكتملت {ok_count} من {len(result)} مهام صيانة", "🔧",
                       color=("#16a34a", "#15803d"))

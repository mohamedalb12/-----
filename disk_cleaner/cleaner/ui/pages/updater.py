"""updater.py — صفحة تحديث التطبيقات."""

from __future__ import annotations

from tkinter import ttk
from typing import Dict

import customtkinter as ctk

from ...core import updater
from ...core.shell import run
from .. import theme as T
from ..widgets import Card, EmptyState, GradientButton, PageHeader, ProgressPanel
from .base import Page


class UpdaterPage(Page):
    def __init__(self, master, app):
        super().__init__(master, app)
        self.updates: Dict[str, updater.UpdateInfo] = {}
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        header = PageHeader(self, "⬆️", "التحديثات",
                            "ابحث عن إصدارات أحدث من تطبيقاتك (App Store والتطبيقات التي تدعم Sparkle)")
        header.grid(row=0, column=0, sticky="ew")
        self.scan_btn = GradientButton(header.actions, "🔍  بحث عن تحديثات", self.scan, width=190, height=40,
                                       font_size=14)
        self.scan_btn.pack()

        self.progress = ProgressPanel(self, on_cancel=self.cancel_job)
        self.progress.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        self.progress.grid_remove()

        card = Card(self)
        card.grid(row=2, column=0, sticky="nsew", pady=(12, 0))
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(card, columns=("current", "latest", "source"), style="Pro.Treeview",
                                 selectmode="browse")
        self.tree.heading("#0", text="التطبيق", anchor="w")
        self.tree.column("#0", width=280, stretch=True)
        for col, title, w in (("current", "الإصدار الحالي", 140), ("latest", "الإصدار الجديد", 140),
                              ("source", "المصدر", 120)):
            self.tree.heading(col, text=title, anchor="w")
            self.tree.column(col, width=w, anchor="w", stretch=False)
        self.tree.grid(row=0, column=0, sticky="nsew", padx=(10, 0), pady=10)
        sb = ctk.CTkScrollbar(card, command=self.tree.yview)
        sb.grid(row=0, column=1, sticky="ns", pady=10)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Double-1>", lambda _e: self.update_selected())
        self.empty = EmptyState(card, "⬆️", "هل تطبيقاتك محدّثة؟",
                                "التحديثات تُصلح الثغرات الأمنية وتحسّن الأداء. اضغط «بحث عن تحديثات».")
        self.empty.grid(row=0, column=0, columnspan=2, sticky="nsew")

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        self.notes = ctk.CTkLabel(footer, text="", font=T.font(12), text_color=T.MUTED, justify="left",
                                  anchor="w", wraplength=700)
        self.notes.pack(side="left", fill="x", expand=True)
        self.update_btn = GradientButton(footer, "⬇️  تحديث", self.update_selected, width=170, height=46)
        self.update_btn.pack(side="right")
        self.update_btn.configure_button(enabled=False)

    def scan(self):
        self.updates.clear()
        self.tree.delete(*self.tree.get_children())
        self.scan_btn.configure_button(enabled=False)
        self.progress.grid()
        self.progress.start("جمع قائمة التطبيقات...")
        self.start_job(updater.check_updates)

    def on_progress(self, fraction, text):
        self.progress.update_progress(fraction, text)

    def on_custom(self, kind, payload):
        if kind == "update_found":
            self._add(payload[0])

    def _add(self, u: "updater.UpdateInfo"):
        if u.app.path in self.updates:
            return
        self.updates[u.app.path] = u
        self.tree.insert("", "end", iid=u.app.path, text=f"  {u.app.name}",
                         values=(u.current, f"✨ {u.latest}", u.source))
        self.empty.lower()

    def on_finished(self, result, job):
        self.scan_btn.configure_button(enabled=True)
        if result is None:
            self.progress.finish(self.summary_text(job), complete=False)
            return
        updates, checked, total = result
        for u in updates:
            self._add(u)
        self.progress.finish(self.summary_text(
            job, f"{len(updates)} تحديث متاح — تم فحص {checked} من {total} تطبيق "
                 "(الباقي لا يدعم الفحص التلقائي)"))
        if not updates:
            self.empty.set("كل تطبيقاتك محدّثة 🎉", f"تم فحص {checked} تطبيق.")
            self.empty.lift()

    def _on_select(self, _e):
        sel = self.tree.selection()
        u = self.updates.get(sel[0]) if sel else None
        self.update_btn.configure_button(enabled=u is not None)
        self.notes.configure(text=(f"📝 {u.notes}" if u and u.notes else ""))

    def update_selected(self):
        sel = self.tree.selection()
        u = self.updates.get(sel[0]) if sel else None
        if not u:
            return
        if u.source == "App Store":
            run(["open", u.url])
        else:
            # تطبيقات Sparkle تُحدَّث من داخلها بأمان (تتحقق من التوقيع) — نفتح التطبيق
            run(["open", u.app.path])
            self.notes.configure(text=f"📝 فتحنا {u.app.name} — اختر «Check for Updates» من قائمة "
                                      "التطبيق لتثبيت التحديث بأمان.")

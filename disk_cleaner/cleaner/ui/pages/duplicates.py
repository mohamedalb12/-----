"""duplicates.py — صفحة الملفات المكررة."""

from __future__ import annotations

import os
from tkinter import filedialog, messagebox

import customtkinter as ctk

from ...core.duplicates import find_duplicates, pick_original, wasted_bytes
from ...core.models import human_size
from .. import theme as T
from ..checktree import CheckTree, Group
from ..widgets import Card, EmptyState, GradientButton, PageHeader, ProgressPanel
from .base import Page

MIN_SIZES = {"100 KB": 100_000, "1 MB": 1_000_000, "10 MB": 10_000_000, "100 MB": 100_000_000}
COLUMNS = (("size", "الحجم", 110, "e"), ("used", "آخر تعديل", 130, "w"), ("path", "المكان", 440, "w"))


class DuplicatesPage(Page):
    def __init__(self, master, app):
        super().__init__(master, app)
        self.groups = []
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        PageHeader(self, "👯", "الملفات المكررة",
                   "نسخ متطابقة تماماً (مقارنة المحتوى بايت ببايت) تهدر مساحتك").grid(
            row=0, column=0, sticky="ew")

        opts = Card(self)
        opts.grid(row=1, column=0, sticky="ew", pady=(14, 0))
        opts.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(opts, text="المكان", font=T.font(13, "bold")).grid(row=0, column=0, padx=(18, 10),
                                                                     pady=16)
        self.path_var = ctk.StringVar(value=os.path.expanduser("~"))
        ctk.CTkEntry(opts, textvariable=self.path_var, height=36).grid(row=0, column=1, sticky="ew")
        ctk.CTkButton(opts, text="📁", width=40, height=36, fg_color=T.CARD_ALT, hover_color=T.HOVER,
                      text_color=T.TEXT, command=self._choose).grid(row=0, column=2, padx=6)
        ctk.CTkLabel(opts, text="أصغر حجم", font=T.font(13, "bold")).grid(row=0, column=3, padx=(14, 8))
        self.min_size = ctk.CTkSegmentedButton(opts, values=list(MIN_SIZES), font=T.font(12))
        self.min_size.set("1 MB")
        self.min_size.grid(row=0, column=4)
        self.scan_btn = GradientButton(opts, "🔍  فحص", self.scan, width=130, height=40, font_size=14)
        self.scan_btn.grid(row=0, column=5, padx=18)

        self.progress = ProgressPanel(self, on_cancel=self.cancel_job)
        self.progress.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        self.progress.grid_remove()

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=3, column=0, sticky="nsew", pady=(12, 0))
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(0, weight=1)
        self.tree = CheckTree(body, COLUMNS, on_change=self._update_footer, actions=app.files)
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.empty = EmptyState(body, "👯", "ابحث عن النسخ المكررة",
                                "سيحدد البرنامج تلقائياً كل النسخ عدا الأقدم (الأصلية) في كل مجموعة. "
                                "مجلد Library والمجلدات المخفية مستثناة للأمان.")
        self.empty.grid(row=0, column=0, sticky="nsew")

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=4, column=0, sticky="ew", pady=(12, 0))
        ctk.CTkButton(footer, text="✨ تحديد ذكي", width=110, fg_color=T.TRACK, hover_color=T.HOVER,
                      text_color=T.TEXT, command=self.smart_select).pack(side="left")
        ctk.CTkButton(footer, text="إلغاء التحديد", width=100, fg_color=T.TRACK, hover_color=T.HOVER,
                      text_color=T.TEXT, command=lambda: self.tree.set_all(False)).pack(side="left", padx=8)
        self.summary = ctk.CTkLabel(footer, text="", font=T.font(13), text_color=T.MUTED)
        self.summary.pack(side="left", padx=10)
        self.delete_btn = GradientButton(footer, "🗑  حذف النسخ المحددة", self.delete, width=240,
                                         height=48, colors=T.GRADIENT_DANGER)
        self.delete_btn.pack(side="right")
        self._update_footer()

    def _choose(self):
        folder = filedialog.askdirectory(parent=self.app, initialdir=self.path_var.get())
        if folder:
            self.path_var.set(folder)

    def show_groups(self, groups):
        self.groups = groups
        tree_groups = []
        for n, g in enumerate(groups):
            original = pick_original(g)
            tree_groups.append(Group(
                f"g{n}", f"{g[0].name}   ×{len(g)}", g, checked=True, keep={original.path},
                subtitle=f"هدر {human_size(g[0].size * (len(g) - 1))}"))
        self.tree.set_groups(tree_groups, expand=True)
        if groups:
            self.empty.lower()
        else:
            self.empty.set("لا توجد ملفات مكررة 🎉", "كل ملفاتك فريدة في هذا المكان.")
            self.empty.lift()

    def smart_select(self):
        self.tree.set_all(False)
        self.tree.set_all(True)  # set_all(True) يحترم النسخة الأصلية (keep) في كل مجموعة

    def _update_footer(self):
        size = self.tree.checked_size()
        self.summary.configure(
            text=f"{len(self.groups):,} مجموعة — هدر إجمالي {human_size(wasted_bytes(self.groups))}"
                 + (f"  •  المحدد: {human_size(size)}" if size else ""))
        self.delete_btn.configure_button(enabled=size > 0)

    def scan(self):
        root = os.path.expanduser(self.path_var.get().strip())
        if not os.path.isdir(root):
            messagebox.showerror("مسار غير صالح", f"المجلد غير موجود:\n{root}", parent=self.app)
            return
        self.scan_btn.configure_button(enabled=False)
        self.progress.grid()
        self.progress.start("جمع الملفات...")
        self.start_job(find_duplicates, root, MIN_SIZES[self.min_size.get()], False,
                       self.app.settings.excluded)

    def on_progress(self, fraction, text):
        self.progress.update_progress(fraction, text)

    def on_finished(self, result, job):
        self.scan_btn.configure_button(enabled=True)
        extra = f"{len(result or []):,} مجموعة مكررة" if result is not None else ""
        self.progress.finish(self.summary_text(job, extra), complete=not job.cancelled)
        if result is not None and not job.cancelled:
            self.show_groups(result)

    def delete(self):
        checked = {i.path for i in self.tree.checked_items()}
        all_gone = sum(1 for g in self.groups if all(i.path in checked for i in g))
        warning = ""
        if all_gone:
            if not messagebox.askyesno(
                    "انتبه", f"حددت كل النسخ في {all_gone} مجموعة، أي لن تبقى أي نسخة من هذه الملفات.\n"
                             "هل تريد المتابعة؟", icon="warning", parent=self.app):
                return
            warning = f"• سيتم حذف كل النسخ في {all_gone} مجموعة."
        self.app.delete_items(self.tree.checked_items(), self._after_delete, warning=warning)

    def _after_delete(self, deleted, _failed):
        gone = {i.path for i in deleted}
        self.groups = [g2 for g2 in ([i for i in g if i.path not in gone] for g in self.groups)
                       if len(g2) > 1]
        self.tree.remove_paths(gone)
        # مجموعات بقي فيها ملف واحد لم تعد مكررة
        self.show_groups(self.groups)

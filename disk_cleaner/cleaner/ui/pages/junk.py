"""junk.py — صفحة مهملات النظام."""

from __future__ import annotations

import os
from tkinter import filedialog

import customtkinter as ctk

from ...core.junk import scan_junk, scan_junk_folder
from ...core.models import CATEGORY_INFO, JUNK_CATEGORIES, human_size, short_path
from .. import theme as T
from ..checktree import CheckTree, Group
from ..widgets import EmptyState, GradientButton, PageHeader, ProgressPanel
from .base import Page


class JunkPage(Page):
    def __init__(self, master, app):
        super().__init__(master, app)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        header = PageHeader(self, "🧹", "مهملات النظام",
                            "الكاش، السجلات، الملفات المؤقتة، سلة المحذوفات ومخلفات المطوّرين")
        header.grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(header.actions, text="📁  فحص مجلد محدد", height=40, width=160,
                      fg_color=T.CARD, hover_color=T.HOVER, text_color=T.TEXT, border_width=1,
                      border_color=T.BORDER, command=self.scan_folder).pack(side="left", padx=8)
        self.scan_btn = GradientButton(header.actions, "🔍  فحص", self.scan, width=140, height=40,
                                       font_size=14)
        self.scan_btn.pack(side="left")

        self.progress = ProgressPanel(self, on_cancel=self.cancel_job)
        self.progress.grid(row=1, column=0, sticky="ew", pady=(14, 0))
        self.progress.grid_remove()

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=2, column=0, sticky="nsew", pady=(14, 0))
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(0, weight=1)
        self.tree = CheckTree(body, on_change=self._update_footer, actions=app.files)
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.empty = EmptyState(body, "🧹", "لنكتشف المهملات المختبئة",
                                "اضغط «فحص» للبحث في الكاش والسجلات والملفات المؤقتة وسلة "
                                "المحذوفات ومخلفات Xcode وغيرها.")
        self.empty.grid(row=0, column=0, sticky="nsew")

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=3, column=0, sticky="ew", pady=(14, 0))
        ctk.CTkButton(footer, text="تحديد الكل", width=96, fg_color=T.TRACK, hover_color=T.HOVER,
                      text_color=T.TEXT, command=lambda: self.tree.set_all(True)).pack(side="left")
        ctk.CTkButton(footer, text="إلغاء التحديد", width=96, fg_color=T.TRACK, hover_color=T.HOVER,
                      text_color=T.TEXT, command=lambda: self.tree.set_all(False)).pack(side="left", padx=8)
        self.summary = ctk.CTkLabel(footer, text="", font=T.font(13), text_color=T.MUTED)
        self.summary.pack(side="left", padx=12)
        self.clean_btn = GradientButton(footer, "🧹  تنظيف", self.clean, width=220, height=48,
                                        colors=T.GRADIENT_SUCCESS)
        self.clean_btn.pack(side="right")
        self._update_footer()

    # ------------------------------------------------------------ النتائج
    def show_result(self, result):
        groups = []
        for cat in JUNK_CATEGORIES:
            items = result.get(cat, [])
            info = CATEGORY_INFO[cat]
            badge = "   ✓ موصى به" if info.safe else "   ⚠︎ راجعه أولاً"
            groups.append(Group(cat.value, f"{info.icon}  {info.label}{badge}", items,
                                checked=info.safe))
        self.tree.set_groups(groups)
        if self.tree.group_order:
            self.empty.lower()
            self.tree.lift()
        else:
            self.empty.set("جهازك نظيف! ✨", "لم يتم العثور على مهملات.")
            self.empty.lift()

    def on_smart_result(self, result):
        if not self.busy:
            self.show_result(result.junk)

    def _update_footer(self):
        checked = self.tree.checked_size()
        self.summary.configure(text=f"المحدد: {human_size(checked)} من {human_size(self.tree.total_size())}")
        self.clean_btn.configure_button(text=f"🧹  تنظيف {human_size(checked)}" if checked else "🧹  تنظيف",
                                        enabled=checked > 0 and not self.busy)

    # ------------------------------------------------------------ الفحص
    def _begin(self, text: str):
        self.scan_btn.configure_button(enabled=False)
        self.progress.grid()
        self.progress.start(text)
        self._update_footer()

    def scan(self):
        self._begin("جارٍ فحص أماكن المهملات المعروفة...")
        self.start_job(scan_junk)

    def scan_folder(self):
        folder = filedialog.askdirectory(parent=self.app, initialdir=os.path.expanduser("~"),
                                         title="اختر مجلداً للبحث فيه عن المهملات")
        if folder:
            self._begin(f"جارٍ فحص {short_path(folder)}...")
            self.start_job(scan_junk_folder, folder, self.app.settings.excluded)

    def on_progress(self, fraction, text):
        self.progress.update_progress(fraction, text)

    def on_finished(self, result, job):
        self.scan_btn.configure_button(enabled=True)
        total = sum(i.size for items in (result or {}).values() for i in items)
        self.progress.finish(self.summary_text(job, f"وُجد {human_size(total)}"),
                             complete=not job.cancelled)
        if result is not None:
            self.show_result(result)
        self._update_footer()

    # ------------------------------------------------------------ التنظيف
    def clean(self):
        items = self.tree.checked_items()
        self.app.delete_items(items, self._after_delete, action_text="تنظيف", title="تنظيف المهملات",
                              warning="يُفضّل إغلاق التطبيقات المفتوحة قبل حذف الكاش الخاص بها.")

    def _after_delete(self, deleted, _failed):
        self.tree.remove_paths({i.path for i in deleted})
        if self.app.smart_result:
            gone = {i.path for i in deleted}
            for cat, items in self.app.smart_result.junk.items():
                self.app.smart_result.junk[cat] = [i for i in items if i.path not in gone]
            dash = self.app.pages.get("dashboard")
            if dash:
                dash.on_smart_result(self.app.smart_result)

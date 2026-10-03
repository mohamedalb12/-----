"""privacy.py — صفحة الخصوصية: مسح آثار التصفح والنشاط."""

from __future__ import annotations

from tkinter import messagebox

import customtkinter as ctk

from ...core import privacy
from ...core.models import human_size
from ...core.shell import is_process_running, quit_app_named
from .. import theme as T
from ..checktree import CheckTree, Group
from ..widgets import EmptyState, GradientButton, PageHeader, ProgressPanel, show_toast
from .base import CallbackListener, Page

COLUMNS = (("size", "الحجم", 100, "e"), ("info", "النوع", 220, "w"), ("path", "المكان", 420, "w"))


class PrivacyPage(Page):
    def __init__(self, master, app):
        super().__init__(master, app)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        header = PageHeader(self, "🕵️", "الخصوصية",
                            "امسح سجل التصفح والكوكيز والكاش من كل متصفحاتك — كلمات المرور لا تُلمس أبداً")
        header.grid(row=0, column=0, sticky="ew")
        self.scan_btn = GradientButton(header.actions, "🔍  فحص", self.scan, width=130, height=40,
                                       font_size=14)
        self.scan_btn.pack()

        self.progress = ProgressPanel(self, on_cancel=self.cancel_job)
        self.progress.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        self.progress.grid_remove()

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=2, column=0, sticky="nsew", pady=(12, 0))
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(0, weight=1)
        self.tree = CheckTree(body, COLUMNS, on_change=self._update_footer, actions=app.files,
                              info=lambda i: privacy.KIND_LABELS.get(privacy.kind_of(i), ""))
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.empty = EmptyState(body, "🕵️", "احمِ خصوصيتك",
                                "سنبحث في Safari و Chrome و Firefox و Edge و Brave وغيرها عن سجل التصفح "
                                "والكوكيز والكاش، وعن قوائم الملفات المستخدمة مؤخراً في النظام.\n"
                                "يُفضّل منح «الوصول الكامل للقرص» لفحص Safari.")
        self.empty.grid(row=0, column=0, sticky="nsew")

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        self.summary = ctk.CTkLabel(footer, text="", font=T.font(13), text_color=T.MUTED, justify="left")
        self.summary.pack(side="left")
        self.clean_btn = GradientButton(footer, "🧽  مسح المحدد", self.clean, width=220, height=48,
                                        colors=T.GRADIENT_SUCCESS)
        self.clean_btn.pack(side="right")
        self._update_footer()

    def scan(self):
        self.scan_btn.configure_button(enabled=False)
        self.progress.grid()
        self.progress.start("جارٍ الفحص...")
        self.start_job(privacy.scan_privacy)

    def on_progress(self, fraction, text):
        self.progress.update_progress(fraction, text)

    def on_finished(self, result, job):
        self.scan_btn.configure_button(enabled=True)
        self.progress.finish(self.summary_text(job))
        if result is None:
            return
        groups = [Group(name, f"{privacy.BROWSER_ICONS.get(name, '🌐')}  {name}", items)
                  for name, items in result.items()]
        self.tree.set_groups(groups, expand=True)
        self.tree.set_checked_paths({i.path for items in result.values() for i in items
                                     if privacy.kind_of(i) in privacy.DEFAULT_CHECKED})
        if groups:
            self.empty.lower()
        else:
            self.empty.set("لا توجد آثار", "لم نجد بيانات تصفح.")
            self.empty.lift()

    def _update_footer(self):
        items = self.tree.checked_items()
        self.summary.configure(
            text=f"المحدد: {len(items):,} عنصر ({human_size(sum(i.size for i in items))})\n"
                 "💡 الكوكيز غير محددة افتراضياً لأن مسحها يسجّل خروجك من المواقع.")
        self.clean_btn.configure_button(enabled=bool(items))

    def clean(self):
        items = self.tree.checked_items()
        browsers = sorted({privacy.browser_of(i) for i in items} - {"النظام"})
        running = [b for b in browsers if is_process_running(privacy.PROCESS_NAMES.get(b, b))]
        if running:
            answer = messagebox.askyesnocancel(
                "المتصفحات مفتوحة", f"يجب إغلاق: {', '.join(running)}\nهل تريد إغلاقها الآن تلقائياً؟",
                parent=self.app)
            if not answer:
                return
            for b in running:
                quit_app_named(privacy.PROCESS_NAMES.get(b, b))
        if not messagebox.askyesno("مسح بيانات الخصوصية",
                                   f"سيتم مسح {len(items):,} عنصر نهائياً. متابعة؟", parent=self.app):
            return
        self.clean_btn.configure_button(enabled=False)
        self.app.run_job(CallbackListener(on_finished=self._cleaned, parent=self.app),
                         privacy.clean_privacy, items)

    def _cleaned(self, result, _job):
        deleted, failed = result if result else ([], [])
        self.tree.remove_paths({i.path for i in deleted})
        if deleted:
            show_toast(self.app, f"تم مسح {len(deleted):,} عنصر من آثار التصفح", "🕵️",
                       color=("#16a34a", "#15803d"))
        if failed:
            messagebox.showwarning("بعض العناصر لم تُمسح",
                                   "\n".join(f"• {i.name}: {e}" for i, e in failed[:6]), parent=self.app)
        self._update_footer()

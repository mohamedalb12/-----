"""large.py — صفحة الملفات الكبيرة والقديمة."""

from __future__ import annotations

import csv
import os
from collections import defaultdict
from tkinter import filedialog, messagebox

import customtkinter as ctk

from ...core.large import scan_large_old
from ...core.models import KINDS, format_date, human_size, kind_label
from .. import theme as T
from ..checktree import CheckTree, Group
from ..widgets import Card, EmptyState, GradientButton, PageHeader, ProgressPanel, show_toast
from .base import Page

SIZE_STEPS_MB = [10, 25, 50, 100, 250, 500, 1000, 2000, 5000, 10000]
AGE_OPTIONS = {"أي وقت": 0, "أقدم من شهر": 30, "أقدم من 3 أشهر": 90, "أقدم من 6 أشهر": 180,
               "أقدم من سنة": 365, "أقدم من سنتين": 730}


def _mb_label(mb: int) -> str:
    return f"{mb / 1000:g} GB" if mb >= 1000 else f"{mb} MB"


class LargePage(Page):
    def __init__(self, master, app):
        super().__init__(master, app)
        self.items = []
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        PageHeader(self, "📦", "الملفات الكبيرة والقديمة",
                   "اعثر على الملفات الضخمة أو المنسية التي تستهلك مساحتك").grid(row=0, column=0, sticky="ew")

        # ---------------- لوحة الخيارات
        opts = Card(self)
        opts.grid(row=1, column=0, sticky="ew", pady=(14, 0))
        opts.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(opts, text="المكان", font=T.font(13, "bold")).grid(row=0, column=0, padx=(18, 10),
                                                                     pady=(16, 6), sticky="w")
        self.path_var = ctk.StringVar(value=os.path.expanduser("~"))
        ctk.CTkEntry(opts, textvariable=self.path_var, height=36).grid(row=0, column=1, sticky="ew",
                                                                      pady=(16, 6))
        quick = ctk.CTkFrame(opts, fg_color="transparent")
        quick.grid(row=0, column=2, padx=(10, 18), pady=(16, 6))
        for text, cmd in (("🏠", lambda: self.path_var.set(os.path.expanduser("~"))),
                          ("💽", lambda: self.path_var.set(os.path.abspath(os.sep))),
                          ("📁", self._choose)):
            ctk.CTkButton(quick, text=text, width=40, height=36, fg_color=T.CARD_ALT,
                          hover_color=T.HOVER, text_color=T.TEXT, command=cmd).pack(side="left", padx=2)

        ctk.CTkLabel(opts, text="الحجم", font=T.font(13, "bold")).grid(row=1, column=0, padx=(18, 10),
                                                                    pady=6, sticky="w")
        size_row = ctk.CTkFrame(opts, fg_color="transparent")
        size_row.grid(row=1, column=1, columnspan=2, sticky="ew", padx=(0, 18), pady=6)
        size_row.grid_columnconfigure(0, weight=1)
        self.slider = ctk.CTkSlider(size_row, from_=0, to=len(SIZE_STEPS_MB) - 1,
                                    number_of_steps=len(SIZE_STEPS_MB) - 1, command=self._on_slider)
        self.slider.set(SIZE_STEPS_MB.index(100))
        self.slider.grid(row=0, column=0, sticky="ew")
        self.size_label = ctk.CTkLabel(size_row, text="", width=120, font=T.font(13, "bold"),
                                       text_color=T.ACCENT)
        self.size_label.grid(row=0, column=1, padx=(12, 0))
        self._on_slider(self.slider.get())

        ctk.CTkLabel(opts, text="العمر", font=T.font(13, "bold")).grid(row=2, column=0, padx=(18, 10),
                                                                    pady=(6, 16), sticky="w")
        row3 = ctk.CTkFrame(opts, fg_color="transparent")
        row3.grid(row=2, column=1, columnspan=2, sticky="ew", padx=(0, 18), pady=(6, 16))
        self.age = ctk.CTkSegmentedButton(row3, values=list(AGE_OPTIONS), font=T.font(12))
        self.age.set("أي وقت")
        self.age.pack(side="left")
        self.include_lib = ctk.CTkSwitch(row3, text="تضمين ملفات Library", font=T.font(12))
        self.include_lib.pack(side="left", padx=16)
        self.scan_btn = GradientButton(row3, "🔍  فحص", self.scan, width=140, height=40, font_size=14)
        self.scan_btn.pack(side="right")

        self.progress = ProgressPanel(self, on_cancel=self.cancel_job)
        self.progress.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        self.progress.grid_remove()

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=3, column=0, sticky="nsew", pady=(12, 0))
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(0, weight=1)
        self.tree = CheckTree(body, on_change=self._update_footer, actions=app.files)
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.empty = EmptyState(body, "📦", "ما الذي يشغل مساحتك؟",
                                "حدد الحجم والعمر ثم اضغط «فحص». الملفات مُجمّعة حسب النوع: فيديو، "
                                "صور، أرشيفات، صور أقراص...")
        self.empty.grid(row=0, column=0, sticky="nsew")

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=4, column=0, sticky="ew", pady=(12, 0))
        self.summary = ctk.CTkLabel(footer, text="", font=T.font(13), text_color=T.MUTED)
        self.summary.pack(side="left")
        self.delete_btn = GradientButton(footer, "🗑  حذف المحدد", self.delete, width=210, height=48,
                                         colors=T.GRADIENT_DANGER)
        self.delete_btn.pack(side="right")
        ctk.CTkButton(footer, text="⬇︎  تصدير CSV", width=120, height=40, fg_color=T.TRACK,
                      hover_color=T.HOVER, text_color=T.TEXT, command=self.export).pack(side="right", padx=10)
        self._update_footer()

    # ------------------------------------------------------------ الخيارات
    def _on_slider(self, value):
        self.size_label.configure(text=f"≥ {_mb_label(SIZE_STEPS_MB[int(round(float(value)))])}")

    def _choose(self):
        folder = filedialog.askdirectory(parent=self.app, initialdir=self.path_var.get())
        if folder:
            self.path_var.set(folder)

    # ------------------------------------------------------------ النتائج
    def show_items(self, items):
        self.items = items
        by_kind = defaultdict(list)
        for item in items:
            by_kind["app" if item.is_dir else item.kind].append(item)
        groups = [Group(k, kind_label(k), by_kind[k]) for k in KINDS if by_kind.get(k)]
        groups.sort(key=lambda g: sum(i.size for i in g.items), reverse=True)
        self.tree.set_groups(groups)
        if items:
            self.empty.lower()
        else:
            self.empty.set("لم يتم العثور على ملفات", "جرّب حداً أصغر للحجم أو مكاناً آخر.")
            self.empty.lift()

    def on_smart_result(self, result):
        if not self.busy and not self.items:
            self.show_items(result.large)

    def _update_footer(self):
        n = len(self.tree.checked_items())
        size = self.tree.checked_size()
        self.summary.configure(text=f"{len(self.items):,} ملف بإجمالي {human_size(self.tree.total_size())}"
                                    + (f"  •  المحدد: {n:,} ({human_size(size)})" if n else ""))
        self.delete_btn.configure_button(enabled=n > 0)

    # ------------------------------------------------------------ الفحص
    def scan(self):
        root = os.path.expanduser(self.path_var.get().strip())
        if not os.path.isdir(root):
            messagebox.showerror("مسار غير صالح", f"المجلد غير موجود:\n{root}", parent=self.app)
            return
        self.scan_btn.configure_button(enabled=False)
        self.progress.grid()
        self.progress.start("جارٍ حصر الملفات...")
        min_size = SIZE_STEPS_MB[int(round(self.slider.get()))] * 1_000_000
        self.start_job(scan_large_old, root, min_size, AGE_OPTIONS[self.age.get()],
                       bool(self.include_lib.get()), self.app.settings.excluded)

    def on_progress(self, fraction, text):
        self.progress.update_progress(fraction, text)

    def on_finished(self, result, job):
        self.scan_btn.configure_button(enabled=True)
        found = f"وُجد {len(result or []):,} ملف ({human_size(sum(i.size for i in result or []))})"
        self.progress.finish(self.summary_text(job, found), complete=not job.cancelled)
        if result is not None:
            self.show_items(result)

    # ------------------------------------------------------------ الإجراءات
    def delete(self):
        self.app.delete_items(self.tree.checked_items(), self._after_delete)

    def _after_delete(self, deleted, _failed):
        gone = {i.path for i in deleted}
        self.items = [i for i in self.items if i.path not in gone]
        self.tree.remove_paths(gone)

    def export(self):
        if not self.items:
            return
        path = filedialog.asksaveasfilename(parent=self.app, defaultextension=".csv",
                                            initialfile="large-files.csv",
                                            filetypes=[("CSV", "*.csv")])
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["name", "size_bytes", "size", "modified", "path"])
            for i in self.items:
                w.writerow([i.name, i.size, human_size(i.size), format_date(i.mtime), i.path])
        show_toast(self.app, "تم تصدير القائمة", "📄")

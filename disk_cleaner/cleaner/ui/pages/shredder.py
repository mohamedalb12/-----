"""shredder.py — آلة التمزيق: حذف آمن ونهائي للملفات الحساسة والعالقة."""

from __future__ import annotations

import os
from tkinter import filedialog, messagebox
from typing import List

import customtkinter as ctk

from ...core.models import human_size, short_path
from ...core.shredder import shred_paths
from ...core.walker import dir_size
from .. import theme as T
from ..widgets import Card, EmptyState, GradientButton, PageHeader, ProgressPanel, show_toast
from .base import Page


class ShredderPage(Page):
    def __init__(self, master, app):
        super().__init__(master, app)
        self.paths: List[str] = []
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        header = PageHeader(self, "✂️", "آلة التمزيق",
                            "احذف الملفات الحساسة نهائياً، وتخلّص من الملفات العالقة التي يرفض Finder حذفها")
        header.grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(header.actions, text="📄 إضافة ملفات", width=130, height=38, fg_color=T.CARD,
                      hover_color=T.HOVER, text_color=T.TEXT, border_width=1, border_color=T.BORDER,
                      command=self.add_files).pack(side="left", padx=4)
        ctk.CTkButton(header.actions, text="📁 إضافة مجلد", width=130, height=38, fg_color=T.CARD,
                      hover_color=T.HOVER, text_color=T.TEXT, border_width=1, border_color=T.BORDER,
                      command=self.add_folder).pack(side="left", padx=4)

        self.progress = ProgressPanel(self, on_cancel=self.cancel_job)
        self.progress.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        self.progress.grid_remove()

        self.card = Card(self)
        self.card.grid(row=2, column=0, sticky="nsew", pady=(12, 0))
        self.card.grid_columnconfigure(0, weight=1)
        self.card.grid_rowconfigure(0, weight=1)
        self.listing = ctk.CTkScrollableFrame(self.card, fg_color="transparent")
        self.listing.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        self.listing.grid_columnconfigure(0, weight=1)
        self.empty = EmptyState(self.card, "✂️", "أضف ملفات لتمزيقها",
                                "سيتم الكتابة فوق محتوى الملفات ببيانات عشوائية ثم حذفها نهائياً بلا سلة.\n"
                                "ملاحظة صريحة: على أقراص SSD لا يمكن لأي برنامج ضمان المسح الفعلي للخلايا — "
                                "الحماية الحقيقية هي تفعيل FileVault.")
        self.empty.grid(row=0, column=0, sticky="nsew")

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        self.summary = ctk.CTkLabel(footer, text="", font=T.font(13), text_color=T.MUTED)
        self.summary.pack(side="left")
        ctk.CTkButton(footer, text="مسح القائمة", width=100, fg_color=T.TRACK, hover_color=T.HOVER,
                      text_color=T.TEXT, command=self.clear).pack(side="left", padx=12)
        self.shred_btn = GradientButton(footer, "✂️  تمزيق نهائي", self.shred, width=210, height=48,
                                        colors=T.GRADIENT_DANGER)
        self.shred_btn.pack(side="right")
        self._render()

    def add_files(self):
        files = filedialog.askopenfilenames(parent=self.app, title="اختر الملفات المراد تمزيقها")
        self._add(files)

    def add_folder(self):
        folder = filedialog.askdirectory(parent=self.app, title="اختر المجلد المراد تمزيقه")
        if folder:
            self._add([folder])

    def _add(self, paths):
        for p in paths:
            if p and p not in self.paths:
                self.paths.append(p)
        self._render()

    def clear(self):
        self.paths = []
        self._render()

    def _render(self):
        for w in self.listing.winfo_children():
            w.destroy()
        total = 0
        for p in self.paths:
            size = dir_size(p) if os.path.exists(p) else 0
            total += size
            row = ctk.CTkFrame(self.listing, fg_color=T.CARD_ALT, corner_radius=10)
            row.pack(fill="x", pady=3)
            icon = "📁" if os.path.isdir(p) else "📄"
            ctk.CTkLabel(row, text=f"{icon}  {short_path(p)}", font=T.font(13), anchor="w").pack(
                side="left", padx=12, pady=8)
            ctk.CTkButton(row, text="✕", width=30, height=26, fg_color="transparent", hover_color=T.HOVER,
                          text_color=T.MUTED, command=lambda x=p: self._remove(x)).pack(side="right", padx=6)
            ctk.CTkLabel(row, text=human_size(size), font=T.font(12), text_color=T.MUTED).pack(side="right")
        if self.paths:
            self.empty.lower()
        else:
            self.empty.lift()
        self.summary.configure(text=f"{len(self.paths)} عنصر — {human_size(total)}" if self.paths else "")
        self.shred_btn.configure_button(enabled=bool(self.paths) and not self.busy)

    def _remove(self, path):
        self.paths.remove(path)
        self._render()

    def shred(self):
        if not self.paths or not messagebox.askyesno(
                "تمزيق نهائي", f"سيتم حذف {len(self.paths)} عنصر نهائياً دون المرور بسلة المحذوفات.\n"
                               "لا يمكن التراجع عن هذا أبداً. متابعة؟", icon="warning", parent=self.app):
            return
        self.shred_btn.configure_button(enabled=False)
        self.progress.grid()
        self.progress.start("جارٍ التمزيق...")
        self.start_job(shred_paths, list(self.paths))

    def on_progress(self, fraction, text):
        self.progress.update_progress(fraction, text)

    def on_finished(self, result, job):
        done, failed = result if result else ([], [])
        self.progress.finish(self.summary_text(job, f"تم تمزيق {len(done)} عنصر"))
        self.paths = [p for p in self.paths if p not in done]
        self._render()
        if done:
            show_toast(self.app, f"تم تمزيق {len(done)} عنصر نهائياً", "✂️")
        if failed:
            messagebox.showwarning("تعذّر تمزيق بعض العناصر",
                                   "\n".join(f"• {os.path.basename(p)}: {e}" for p, e in failed[:6]),
                                   parent=self.app)

"""settings.py — صفحة الإعدادات."""

from __future__ import annotations

import os
from tkinter import filedialog, messagebox

import customtkinter as ctk

from ... import APP_NAME, __version__
from ...core import actions
from ...core.models import human_size, short_path
from .. import theme as T
from ..widgets import Card, PageHeader
from .base import Page

APPEARANCE = {"تلقائي (حسب النظام)": "System", "داكن": "Dark", "فاتح": "Light"}
DELETE_MODES = {"سلة المحذوفات (آمن)": "trash", "حذف نهائي": "permanent"}
SMART_LARGE = {"100 MB": 100, "250 MB": 250, "500 MB": 500, "1 GB": 1000, "5 GB": 5000}


class SettingsPage(Page):
    def __init__(self, master, app):
        super().__init__(master, app)
        s = app.settings
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        PageHeader(self, "⚙️", "الإعدادات", "خصّص البرنامج كما تحب").grid(row=0, column=0, sticky="ew")

        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.grid(row=1, column=0, sticky="nsew", pady=(14, 0))
        scroll.grid_columnconfigure(0, weight=1)

        def section(row, icon, title, subtitle=""):
            card = Card(scroll)
            card.grid(row=row, column=0, sticky="ew", pady=(0, 14))
            card.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(card, text=f"{icon}  {title}", font=T.font(16, "bold"), anchor="w").grid(
                row=0, column=0, sticky="w", padx=20, pady=(16, 0))
            if subtitle:
                ctk.CTkLabel(card, text=subtitle, font=T.font(12), text_color=T.MUTED, anchor="w",
                             justify="left").grid(row=1, column=0, sticky="w", padx=20)
            return card

        # ---------------- المظهر
        c = section(0, "🎨", "المظهر", "اختر الوضع الداكن أو الفاتح أو اتبع إعدادات النظام.")
        self.appearance = ctk.CTkSegmentedButton(c, values=list(APPEARANCE), command=self._appearance)
        self.appearance.set(next(k for k, v in APPEARANCE.items() if v == s.appearance))
        self.appearance.grid(row=0, column=1, rowspan=2, padx=20, pady=16)

        # ---------------- الحذف
        c = section(1, "🗑", "طريقة الحذف الافتراضية",
                    "النقل إلى السلة يتيح استرجاع الملفات. يمكنك تغيير الاختيار في كل مرة من نافذة التأكيد.")
        self.delete_mode = ctk.CTkSegmentedButton(c, values=list(DELETE_MODES), command=self._delete_mode)
        self.delete_mode.set(next(k for k, v in DELETE_MODES.items() if v == s.delete_mode))
        self.delete_mode.grid(row=0, column=1, rowspan=2, padx=20, pady=16)

        # ---------------- الفحص الذكي
        c = section(2, "⚡", "الفحص الذكي", "أصغر حجم للملفات الكبيرة التي يعرضها الفحص الذكي.")
        self.smart_large = ctk.CTkSegmentedButton(c, values=list(SMART_LARGE), command=self._smart_large)
        self.smart_large.set(next((k for k, v in SMART_LARGE.items() if v == s.smart_large_mb), "500 MB"))
        self.smart_large.grid(row=0, column=1, rowspan=2, padx=20, pady=16)

        # ---------------- الاستثناءات
        c = section(3, "🚫", "مجلدات مستثناة من الفحص",
                    "لن يقترب البرنامج من هذه المجلدات أبداً (مثل مجلدات مشاريعك أو نسخك الاحتياطية).")
        ctk.CTkButton(c, text="＋ إضافة مجلد", width=130, command=self._add_exclusion).grid(
            row=0, column=1, rowspan=2, padx=20, pady=16)
        self.excl_frame = ctk.CTkFrame(c, fg_color="transparent")
        self.excl_frame.grid(row=2, column=0, columnspan=2, sticky="ew", padx=20, pady=(4, 16))
        self._render_exclusions()

        # ---------------- الصلاحيات
        c = section(4, "🔐", "الوصول الكامل للقرص",
                    "يسمح بفحص المجلدات المحمية في macOS. من: إعدادات النظام ← الخصوصية والأمان ← "
                    "الوصول الكامل للقرص.")
        ok = actions.has_full_disk_access()
        ctk.CTkLabel(c, text="✅ مفعّل" if ok else "⚠️ غير مفعّل", font=T.font(13, "bold"),
                     text_color=T.SUCCESS if ok else T.WARNING).grid(row=0, column=1, padx=10, pady=(16, 0))
        ctk.CTkButton(c, text="فتح الإعدادات", width=130,
                      command=actions.open_full_disk_access_settings).grid(row=1, column=1, padx=20,
                                                                          pady=(4, 16))

        # ---------------- الإحصاءات
        c = section(5, "🏆", "إحصاءاتك")
        self.stats = ctk.CTkLabel(c, text="", font=T.font(13), anchor="w", justify="left")
        self.stats.grid(row=1, column=0, sticky="w", padx=20, pady=(6, 16))
        ctk.CTkButton(c, text="تصفير", width=90, fg_color=T.TRACK, hover_color=T.HOVER,
                      text_color=T.TEXT, command=self._reset_stats).grid(row=0, column=1, rowspan=2,
                                                                         padx=20)

        # ---------------- حول
        c = section(6, "ℹ️", f"{APP_NAME} v{__version__}",
                    "برنامج مفتوح المصدر مكتوب بلغة Python. ملف الإعدادات:\n"
                    + short_path(s.path()))
        ctk.CTkLabel(c, text="").grid(row=2, column=0, pady=4)

    def on_show(self):
        s = self.app.settings
        self.stats.configure(text=f"المساحة المحرَّرة: {human_size(s.total_cleaned)}\n"
                                  f"عمليات التنظيف: {s.clean_count:,}")

    def _save(self):
        self.app.settings.save()

    def _appearance(self, value):
        self.app.settings.appearance = APPEARANCE[value]
        ctk.set_appearance_mode(APPEARANCE[value])
        self._save()

    def _delete_mode(self, value):
        self.app.settings.delete_mode = DELETE_MODES[value]
        self._save()

    def _smart_large(self, value):
        self.app.settings.smart_large_mb = SMART_LARGE[value]
        self._save()

    def _render_exclusions(self):
        for w in self.excl_frame.winfo_children():
            w.destroy()
        excluded = self.app.settings.excluded
        if not excluded:
            ctk.CTkLabel(self.excl_frame, text="لا توجد مجلدات مستثناة.", font=T.font(12),
                         text_color=T.FAINT).pack(anchor="w")
        for path in excluded:
            row = ctk.CTkFrame(self.excl_frame, fg_color=T.CARD_ALT, corner_radius=10)
            row.pack(fill="x", pady=3)
            ctk.CTkLabel(row, text=f"📁  {short_path(path)}", font=T.font(13), anchor="w").pack(
                side="left", padx=12, pady=6)
            ctk.CTkButton(row, text="✕", width=30, height=26, fg_color="transparent",
                          hover_color=T.HOVER, text_color=T.MUTED,
                          command=lambda p=path: self._remove_exclusion(p)).pack(side="right", padx=6)

    def _add_exclusion(self):
        folder = filedialog.askdirectory(parent=self.app, initialdir=os.path.expanduser("~"))
        if folder and folder not in self.app.settings.excluded:
            self.app.settings.excluded.append(folder)
            self._save()
            self._render_exclusions()

    def _remove_exclusion(self, path):
        self.app.settings.excluded.remove(path)
        self._save()
        self._render_exclusions()

    def _reset_stats(self):
        if messagebox.askyesno("تصفير الإحصاءات", "هل تريد تصفير إحصاءات التنظيف؟", parent=self.app):
            self.app.settings.total_cleaned = 0
            self.app.settings.clean_count = 0
            self._save()
            self.on_show()

"""dashboard.py — الصفحة الرئيسية: حالة القرص + الفحص الذكي + التنظيف بضغطة واحدة."""

from __future__ import annotations

import time
from tkinter import messagebox

import customtkinter as ctk

from ...core import actions
from ...core.models import CATEGORY_INFO, Category, JUNK_CATEGORIES, human_size
from ...core.smart import SmartResult, smart_scan
from .. import theme as T
from ..widgets import Card, Donut, GradientButton, ProgressPanel, StatCard, show_toast
from .base import Page


def _greeting() -> str:
    hour = time.localtime().tm_hour
    if 5 <= hour < 12:
        return "صباح الخير ☀️"
    if 12 <= hour < 18:
        return "مساء الخير 🌤"
    return "مساء الخير 🌙"


class DashboardPage(Page):
    def __init__(self, master, app):
        super().__init__(master, app)
        self.result: SmartResult = None
        self.grid_columnconfigure(0, weight=1)

        # ---------------- الترحيب
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(head, text=_greeting(), font=T.font(28, "bold"), anchor="w").pack(anchor="w")
        ctk.CTkLabel(head, text=f"💻 {actions.computer_name()}  •  {actions.os_description()}",
                     font=T.font(13), text_color=T.MUTED, anchor="w").pack(anchor="w", pady=(2, 0))

        # ---------------- تنبيه صلاحية الوصول الكامل للقرص
        self.banner = Card(self, fg_color=T.ACCENT_SOFT, border_color=T.ACCENT)
        ctk.CTkLabel(self.banner, text="🔐", font=T.font(26)).pack(side="left", padx=(16, 8), pady=12)
        txt = ctk.CTkFrame(self.banner, fg_color="transparent")
        txt.pack(side="left", fill="x", expand=True, pady=10)
        ctk.CTkLabel(txt, text="امنح البرنامج «الوصول الكامل للقرص» لفحص أعمق",
                     font=T.font(14, "bold"), anchor="w").pack(anchor="w")
        ctk.CTkLabel(txt, text="بدونها سيتخطّى البرنامج بعض المجلدات المحمية مثل السلة وبريد Mail.",
                     font=T.font(12), text_color=T.MUTED, anchor="w").pack(anchor="w")
        ctk.CTkButton(self.banner, text="فتح الإعدادات", width=120,
                      command=actions.open_full_disk_access_settings).pack(side="right", padx=16)
        if not actions.has_full_disk_access():
            self.banner.grid(row=1, column=0, sticky="ew", pady=(16, 0))

        # ---------------- البطاقة الرئيسية
        hero = Card(self)
        hero.grid(row=2, column=0, sticky="ew", pady=(18, 0))
        hero.grid_columnconfigure(1, weight=1)
        self.donut = Donut(hero, size=210, thickness=22)
        self.donut.grid(row=0, column=0, rowspan=3, padx=26, pady=24)

        info = ctk.CTkFrame(hero, fg_color="transparent")
        info.grid(row=0, column=1, sticky="w", pady=(30, 0))
        ctk.CTkLabel(info, text="مساحة قرص التشغيل", font=T.font(14), text_color=T.MUTED,
                     anchor="w").pack(anchor="w")
        self.free_label = ctk.CTkLabel(info, text="—", font=T.font(34, "bold"), anchor="w")
        self.free_label.pack(anchor="w")
        legend = ctk.CTkFrame(info, fg_color="transparent")
        legend.pack(anchor="w", pady=(6, 0))
        self.used_legend = self._legend(legend, T.ACCENT, "مستخدم")
        self.junk_legend = self._legend(legend, T.PINK, "مهملات يمكن حذفها")
        self.free_legend = self._legend(legend, T.TRACK, "متاح")

        action = ctk.CTkFrame(hero, fg_color="transparent")
        action.grid(row=0, column=2, rowspan=3, padx=30, pady=24, sticky="e")
        self.scan_btn = GradientButton(action, "⚡  فحص ذكي", self.start_scan, width=250, height=64,
                                       font_size=19)
        self.scan_btn.pack()
        self.caption = ctk.CTkLabel(action, text="مهملات النظام + الملفات الكبيرة + بقايا التطبيقات",
                                    font=T.font(12), text_color=T.MUTED)
        self.caption.pack(pady=(8, 0))
        self.progress = ProgressPanel(hero, on_cancel=self.cancel_job)
        self.progress.grid(row=2, column=1, sticky="ew", pady=(0, 26))
        self.progress.grid_remove()

        # ---------------- بطاقات النتائج
        cards = ctk.CTkFrame(self, fg_color="transparent")
        cards.grid(row=3, column=0, sticky="ew", pady=(18, 0))
        for i in range(4):
            cards.grid_columnconfigure(i, weight=1, uniform="cards")
        self.card_junk = StatCard(cards, "🧹", "مهملات النظام", "#7c6cff", "مراجعة التفاصيل",
                                  lambda: app.show_page("junk"))
        self.card_trash = StatCard(cards, "🗑", "سلة المحذوفات", "#ef4444", "إفراغ السلة",
                                   self.empty_trash)
        self.card_large = StatCard(cards, "📦", "ملفات كبيرة", "#22c55e", "مراجعة الملفات",
                                   lambda: app.show_page("large"))
        self.card_apps = StatCard(cards, "🧩", "بقايا التطبيقات", "#f59e0b", "مراجعة البقايا",
                                  lambda: app.show_page("apps"))
        for i, card in enumerate((self.card_junk, self.card_trash, self.card_large, self.card_apps)):
            card.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 8, 0 if i == 3 else 8))
            card.set("—", "اضغط «فحص ذكي» للبدء", enabled=False)

        # ---------------- التنظيف + الإحصاءات
        bottom = Card(self)
        bottom.grid(row=4, column=0, sticky="ew", pady=(18, 0))
        self.stats_label = ctk.CTkLabel(bottom, text="", font=T.font(14), anchor="w", justify="left")
        self.stats_label.pack(side="left", padx=22, pady=18)
        self.clean_btn = GradientButton(bottom, "🧹  تنظيف الآن", self.clean_now, width=230, height=50,
                                        colors=T.GRADIENT_SUCCESS, font_size=16)
        self.clean_btn.pack(side="right", padx=18, pady=14)
        self.clean_btn.configure_button(enabled=False)
        self._update_stats()

    def _legend(self, parent, color, text: str):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(anchor="w", pady=1)
        dot = ctk.CTkLabel(row, text="", width=12, height=12, corner_radius=6, fg_color=color)
        dot.pack(side="left", padx=(0, 8))
        label = ctk.CTkLabel(row, text=text, font=T.font(13), text_color=T.MUTED)
        label.pack(side="left")
        return label

    # ------------------------------------------------------------ القرص
    def on_show(self):
        self.app.refresh_disk()

    def update_disk(self, total: int, used: int, free: int):
        junk = self.result.junk_size if self.result else 0
        junk = min(junk, used)
        self.donut.set([(used - junk, T.resolve(T.ACCENT)), (junk, T.PINK)],
                       f"{used * 100 // max(total, 1)}%", "مستخدم")
        self.free_label.configure(text=f"{human_size(free)} متاح")
        self.used_legend.configure(text=f"مستخدم: {human_size(used)} من {human_size(total)}")
        self.junk_legend.configure(text=f"مهملات يمكن حذفها: {human_size(junk)}" if self.result
                                   else "مهملات يمكن حذفها: —")
        self.free_legend.configure(text=f"متاح: {human_size(free)}")

    def _update_stats(self):
        s = self.app.settings
        if s.total_cleaned:
            text = f"🏆  وفّرت حتى الآن {human_size(s.total_cleaned)} في {s.clean_count:,} عملية تنظيف"
        else:
            text = "🚀  نظّف جهازك بضغطة واحدة بعد الفحص الذكي"
        if self.result:
            text += f"\n✅  يمكن تنظيف {human_size(self._recommended_size())} بأمان الآن"
        self.stats_label.configure(text=text)

    # ------------------------------------------------------------ الفحص الذكي
    def start_scan(self):
        if self.busy:
            return
        self.scan_btn.configure_button(text="⏳  جارٍ الفحص...", enabled=False)
        self.progress.grid()
        self.progress.start("جارٍ التحضير...")
        self.start_job(smart_scan, self.app.settings.smart_large_mb * 1_000_000,
                       self.app.settings.excluded)

    def on_progress(self, fraction, text):
        self.progress.update_progress(fraction, text)

    def on_finished(self, result, job):
        self.scan_btn.configure_button(text="⚡  فحص من جديد", enabled=True)
        self.progress.finish(self.summary_text(job), complete=not job.cancelled)
        if result is None or job.cancelled:
            return
        self.result = result
        self.app.settings.last_smart_scan = time.time()
        self.app.publish_smart_result(result)
        self.app.refresh_disk()
        show_toast(self.app, f"اكتمل الفحص: وُجد {human_size(result.junk_size)} من المهملات", "🔍")

    def on_smart_result(self, result):
        self.result = result
        self._refresh_cards()

    def _refresh_cards(self):
        r = self.result
        if not r:
            return
        junk_no_trash = r.junk_size - r.size_of(Category.TRASH)
        n_junk = sum(len(v) for k, v in r.junk.items() if k != Category.TRASH)
        self.card_junk.set(human_size(junk_no_trash), f"{n_junk:,} عنصر في الكاش والسجلات والمؤقتات")
        trash = r.size_of(Category.TRASH)
        self.card_trash.set(human_size(trash), f"{len(r.junk.get(Category.TRASH, [])):,} عنصر في السلة",
                            enabled=trash > 0)
        self.card_large.set(human_size(r.large_size),
                            f"{len(r.large):,} ملف أكبر من {self.app.settings.smart_large_mb} MB")
        self.card_apps.set(human_size(r.orphans_size), f"{len(r.orphans):,} عنصر من تطبيقات محذوفة")
        self.clean_btn.configure_button(
            text=f"🧹  تنظيف {human_size(self._recommended_size())}",
            enabled=self._recommended_size() > 0)
        self._update_stats()

    # ------------------------------------------------------------ التنظيف
    def _recommended(self):
        if not self.result:
            return []
        return [i for c in JUNK_CATEGORIES if CATEGORY_INFO[c].safe
                for i in self.result.junk.get(c, [])]

    def _recommended_size(self) -> int:
        return sum(i.size for i in self._recommended())

    def clean_now(self):
        items = self._recommended()
        cats = "، ".join(CATEGORY_INFO[c].label for c in JUNK_CATEGORIES
                        if CATEGORY_INFO[c].safe and self.result.junk.get(c))
        self.app.delete_items(items, self._after_delete, action_text="تنظيف",
                              title="تنظيف المهملات", warning=f"سيتم تنظيف: {cats}.\n"
                              "يُفضّل إغلاق التطبيقات المفتوحة قبل حذف الكاش.")

    def _after_delete(self, deleted, _failed):
        if not self.result:
            return
        gone = {i.path for i in deleted}
        for cat, items in self.result.junk.items():
            self.result.junk[cat] = [i for i in items if i.path not in gone]
        self.app.publish_smart_result(self.result)
        self.app.refresh_disk()

    def empty_trash(self):
        if not messagebox.askyesno("إفراغ سلة المحذوفات",
                                   "سيتم حذف كل ما في سلة المحذوفات نهائياً.\nهل تريد المتابعة؟",
                                   icon="warning", parent=self.app):
            return
        trash_items = list(self.result.junk.get(Category.TRASH, [])) if self.result else []
        self.card_trash.set("…", "جارٍ إفراغ السلة...", enabled=False)
        self.app.run_job(_TrashListener(self, trash_items), lambda ctx: actions.empty_trash())


class _TrashListener:
    def __init__(self, page: DashboardPage, items):
        self.page = page
        self.items = items

    def on_job_event(self, job, kind, payload):
        if kind != "finished":
            return
        _result, error = payload
        page = self.page
        if error:
            messagebox.showerror("تعذّر إفراغ السلة", error.strip().splitlines()[-1], parent=page.app)
        else:
            freed = sum(i.size for i in self.items)
            page.app.settings.total_cleaned += freed
            page.app.settings.clean_count += 1
            page.app.settings.save()
            show_toast(page.app, f"تم إفراغ السلة وتحرير {human_size(freed)}", "🗑",
                       color=("#16a34a", "#15803d"))
            if page.result:
                page.result.junk[Category.TRASH] = []
                page.app.publish_smart_result(page.result)
        page.app.refresh_disk()
        page._refresh_cards()

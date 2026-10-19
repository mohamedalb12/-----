"""autopilot.py — صفحة التنظيف التلقائي: ينظّف الكاش من نفسه عندما يتجاوز حداً معيناً."""

from __future__ import annotations

import sys
import time
from tkinter import messagebox, ttk

import customtkinter as ctk

from ...core import autoclean
from ...core.models import CATEGORY_INFO, Category, human_size
from .. import theme as T
from ..widgets import Card, GradientButton, PageHeader, show_toast
from .base import CallbackListener, Page

IS_MAC = sys.platform == "darwin"

THRESHOLDS = {"500 MB": 500, "1 GB": 1000, "2 GB": 2000, "5 GB": 5000, "10 GB": 10000}
AGES = {"يوم": 1, "3 أيام": 3, "أسبوع": 7, "شهر": 30}
INTERVALS = {"كل ساعة": 1, "كل 6 ساعات": 6, "يومياً": 24}
TRASH = {"لا": 0, "أقدم من أسبوع": 7, "أقدم من 30 يوماً": 30}
LOW_DISK = {"بدون": 0, "5 GB": 5, "10 GB": 10, "20 GB": 20}


def _key_for(mapping: dict, value, default: str) -> str:
    return next((k for k, v in mapping.items() if v == value), default)


def _when(ts: float) -> str:
    return time.strftime("%Y-%m-%d  %H:%M", time.localtime(ts)) if ts else "—"


class AutopilotPage(Page):
    def __init__(self, master, app):
        super().__init__(master, app)
        s = app.settings
        self.measured = None
        self.grid_columnconfigure(0, weight=2, uniform="a")
        self.grid_columnconfigure(1, weight=3, uniform="a")
        self.grid_rowconfigure(2, weight=1)

        header = PageHeader(self, "🤖", "التنظيف التلقائي",
                            "ينظّف الكاش والمهملات من نفسه عندما تتجاوز الحد الذي تختاره — حتى والبرنامج مغلق")
        header.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.switch = ctk.CTkSwitch(header.actions, text="مفعّل", font=T.font(14, "bold"),
                                    command=self._toggle, switch_width=52, switch_height=26)
        if s.auto_enabled:
            self.switch.select()
        self.switch.pack()

        # ---------------- الحالة
        status = Card(self)
        status.grid(row=1, column=0, sticky="nsew", padx=(0, 7), pady=(14, 0))
        status.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(status, text="📊  حجم المهملات المراقَبة الآن", font=T.font(14), text_color=T.MUTED,
                     anchor="w").grid(row=0, column=0, sticky="w", padx=20, pady=(18, 0))
        self.size_value = ctk.CTkLabel(status, text="—", font=T.font(34, "bold"), anchor="w")
        self.size_value.grid(row=1, column=0, sticky="w", padx=20)
        self.bar = ctk.CTkProgressBar(status, height=12)
        self.bar.set(0)
        self.bar.grid(row=2, column=0, sticky="ew", padx=20, pady=(6, 2))
        self.bar_label = ctk.CTkLabel(status, text="", font=T.font(12), text_color=T.MUTED, anchor="w")
        self.bar_label.grid(row=3, column=0, sticky="w", padx=20)
        self.breakdown = ctk.CTkLabel(status, text="", font=T.font(12), text_color=T.MUTED, anchor="w",
                                      justify="left")
        self.breakdown.grid(row=4, column=0, sticky="w", padx=20, pady=(8, 0))
        self.state_label = ctk.CTkLabel(status, text="", font=T.font(13), anchor="w", justify="left")
        self.state_label.grid(row=5, column=0, sticky="w", padx=20, pady=(12, 0))
        buttons = ctk.CTkFrame(status, fg_color="transparent")
        buttons.grid(row=6, column=0, sticky="ew", padx=20, pady=(14, 20))
        self.clean_btn = GradientButton(buttons, "🧹  نظّف الآن", self.clean_now, width=170, height=44,
                                        colors=T.GRADIENT_SUCCESS, font_size=15)
        self.clean_btn.pack(side="left")
        ctk.CTkButton(buttons, text="🔄  قياس", width=100, height=40, fg_color=T.TRACK, hover_color=T.HOVER,
                      text_color=T.TEXT, command=self.measure).pack(side="left", padx=10)

        # ---------------- الإعدادات
        opts = Card(self)
        opts.grid(row=1, column=1, sticky="nsew", padx=(7, 0), pady=(14, 0))
        opts.grid_columnconfigure(1, weight=1)
        row = 0

        def label(text):
            ctk.CTkLabel(opts, text=text, font=T.font(13, "bold"), anchor="w").grid(
                row=row, column=0, sticky="w", padx=(18, 10), pady=(14 if row == 0 else 8, 0))

        def seg(mapping, value, default):
            nonlocal row
            w = ctk.CTkSegmentedButton(opts, values=list(mapping), font=T.font(12),
                                       command=lambda _v: self._save())
            w.set(_key_for(mapping, value, default))
            w.grid(row=row, column=1, sticky="w", padx=(0, 18), pady=(14 if row == 0 else 8, 0))
            row += 1
            return w

        label("نظّف عند تجاوز")
        self.threshold = seg(THRESHOLDS, s.auto_threshold_mb, "2 GB")
        label("الفئات")
        cats = ctk.CTkFrame(opts, fg_color="transparent")
        cats.grid(row=row, column=1, sticky="w", padx=(0, 18), pady=(8, 0))
        self.cat_vars = {}
        for i, cat in enumerate(autoclean.AUTO_CATEGORIES):
            var = ctk.BooleanVar(value=cat.value in s.auto_categories)
            self.cat_vars[cat.value] = var
            ctk.CTkCheckBox(cats, text=CATEGORY_INFO[cat].label, variable=var, font=T.font(12),
                            command=self._save).grid(row=i // 2, column=i % 2, sticky="w", padx=(0, 14), pady=2)
        row += 1
        label("احتفظ بالملفات الأحدث من")
        self.age = seg(AGES, s.auto_min_age_days, "3 أيام")
        label("تحقّق")
        self.interval = seg(INTERVALS, s.auto_interval_hours, "كل 6 ساعات")
        label("أفرغ من السلة")
        self.trash = seg(TRASH, s.auto_trash_days, "أقدم من 30 يوماً")
        label("نبّهني لو المساحة أقل من")
        self.low = seg(LOW_DISK, s.low_disk_alert_gb, "10 GB")
        self.notify = ctk.CTkSwitch(opts, text="إشعار بعد كل تنظيف", font=T.font(12), command=self._save)
        if s.auto_notify:
            self.notify.select()
        self.notify.grid(row=row, column=0, columnspan=2, sticky="w", padx=18, pady=(12, 16))

        # ---------------- السجل
        hist = Card(self)
        hist.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=(14, 0))
        hist.grid_columnconfigure(0, weight=1)
        hist.grid_rowconfigure(1, weight=1)
        self.hist_title = ctk.CTkLabel(hist, text="🗓  سجل التنظيف التلقائي", font=T.font(15, "bold"),
                                       anchor="w")
        self.hist_title.grid(row=0, column=0, sticky="w", padx=18, pady=(14, 4))
        self.tree = ttk.Treeview(hist, columns=("measured", "freed", "trash", "free"),
                                 style="Pro.Treeview", height=5)
        self.tree.heading("#0", text="الوقت", anchor="w")
        self.tree.column("#0", width=200, stretch=True)
        for col, title in (("measured", "الحجم المقاس"), ("freed", "تم تحريره"), ("trash", "من السلة"),
                           ("free", "المساحة الحرة بعدها")):
            self.tree.heading(col, text=title, anchor="e")
            self.tree.column(col, width=150, anchor="e", stretch=False)
        self.tree.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 12))
        self._render_state()

    # ------------------------------------------------------------ الحفظ
    def _save(self):
        s = self.app.settings
        s.auto_threshold_mb = THRESHOLDS[self.threshold.get()]
        s.auto_categories = [k for k, v in self.cat_vars.items() if v.get()] or ["cache"]
        s.auto_min_age_days = AGES[self.age.get()]
        s.auto_interval_hours = INTERVALS[self.interval.get()]
        s.auto_trash_days = TRASH[self.trash.get()]
        s.low_disk_alert_gb = LOW_DISK[self.low.get()]
        s.auto_notify = bool(self.notify.get())
        s.save()
        if s.auto_enabled:
            autoclean.ensure_agent(s)
        self._update_bar()
        self._render_state()

    def _toggle(self):
        s = self.app.settings
        enable = bool(self.switch.get())
        if enable:
            ok, msg = autoclean.install_agent(s.auto_interval_hours)
            if not ok:
                self.switch.deselect()
                messagebox.showerror("تعذّر التفعيل", msg, parent=self.app)
                return
            s.auto_enabled = True
            show_toast(self.app, "التنظيف التلقائي مفعّل — سيعمل في الخلفية حتى والبرنامج مغلق", "🤖",
                       color=("#16a34a", "#15803d"))
        else:
            autoclean.uninstall_agent()
            s.auto_enabled = False
            show_toast(self.app, "تم إيقاف التنظيف التلقائي", "⏸")
        s.save()
        self._render_state()

    # ------------------------------------------------------------ العرض
    def on_show(self):
        self._render_state()
        if self.measured is None and not self.busy:
            self.measure()

    def _render_state(self):
        s = self.app.settings
        state = autoclean.AutoState.load()
        last = state.last_run
        lines = []
        if s.auto_enabled:
            lines.append(f"🟢 يعمل في الخلفية — يتحقق {self.interval.get()}")
            if last:
                nxt = last["time"] + s.auto_interval_hours * 3600
                lines.append(f"آخر تشغيل: {_when(last['time'])}   •   القادم تقريباً: {_when(max(nxt, time.time()))}")
        else:
            lines.append("⏸ متوقف — فعّله من الزر في الأعلى")
        lines.append(f"🏆 حرّر التنظيف التلقائي حتى الآن: {human_size(state.total_freed)}")
        self.state_label.configure(text="\n".join(lines))
        self.tree.delete(*self.tree.get_children())
        for n, r in enumerate(state.runs[:40]):
            note = "" if r.get("triggered") else "  (أقل من الحد — لم يُنظّف)"
            self.tree.insert("", "end", iid=str(n), text=f"  {_when(r['time'])}{note}",
                             values=(human_size(r["measured"]), human_size(r["freed"]),
                                     human_size(r["trash_freed"]), human_size(r["free_space"])))
        if not state.runs:
            self.tree.insert("", "end", text="  لا توجد عمليات بعد.")

    def _update_bar(self):
        if self.measured is None:
            return
        cats = self.app.settings.auto_categories
        total = sum(v for k, v in self.measured.items() if k in cats)
        limit = self.app.settings.auto_threshold_mb * 1_000_000
        frac = min(total / limit, 1.0) if limit else 0
        self.size_value.configure(text=human_size(total))
        self.bar.set(frac)
        self.bar.configure(progress_color=T.DANGER if frac >= 1 else T.WARNING if frac > 0.75 else T.ACCENT)
        if frac >= 1:
            self.bar_label.configure(text=f"تجاوز الحد ({human_size(limit)}) — سيُنظَّف في التشغيل القادم")
        else:
            self.bar_label.configure(text=f"{frac * 100:.0f}% من الحد ({human_size(limit)})")
        self.breakdown.configure(text="\n".join(
            f"{CATEGORY_INFO[Category(k)].icon} {CATEGORY_INFO[Category(k)].label}: {human_size(v)}"
            for k, v in self.measured.items() if k in cats))

    # ------------------------------------------------------------ الإجراءات
    def measure(self):
        self.size_value.configure(text="…")
        self.bar_label.configure(text="جارٍ القياس...")

        def work(ctx, cats):
            found = autoclean.measure(ctx, cats)
            return {c.value: sum(i.size for i in found.get(c, [])) for c in autoclean.AUTO_CATEGORIES}

        self.start_job(work, [c.value for c in autoclean.AUTO_CATEGORIES])

    def on_finished(self, result, job):
        if result is not None:
            self.measured = result
            self._update_bar()

    def clean_now(self):
        s = self.app.settings
        if not messagebox.askyesno(
                "تنظيف الآن",
                f"سيتم حذف ملفات {autoclean.category_labels(s.auto_categories)} التي لم تُستخدم منذ "
                f"{self.age.get()} نهائياً (لا تحتاجها التطبيقات وتعيد إنشاءها عند اللزوم).\nمتابعة؟",
                parent=self.app):
            return
        self.clean_btn.configure_button(enabled=False, text="⏳  جارٍ التنظيف...")

        def done(record, _job):
            self.clean_btn.configure_button(enabled=True, text="🧹  نظّف الآن")
            if record:
                show_toast(self.app, f"تم تحرير {human_size(record.freed + record.trash_freed)}", "✨",
                           color=("#16a34a", "#15803d"))
            self.app.refresh_disk()
            self._render_state()
            self.measure()

        self.app.run_job(CallbackListener(on_finished=done, parent=self.app),
                         autoclean.run_autoclean, s, True)

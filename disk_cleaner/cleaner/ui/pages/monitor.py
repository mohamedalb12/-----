"""monitor.py — مراقب الأداء الحي: المعالج، الذاكرة، الشبكة، القرص، البطارية، والعمليات."""

from __future__ import annotations

from tkinter import messagebox, ttk

import customtkinter as ctk

from ...core import monitor as mon
from ...core.models import human_size
from .. import theme as T
from ..widgets import Card, PageHeader, Sparkline
from .base import CallbackListener, Page


class _MetricCard(Card):
    def __init__(self, master, icon: str, title: str, color: str, second_color=None, max_value=100.0):
        super().__init__(master)
        self.grid_columnconfigure(0, weight=1)
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 0))
        ctk.CTkLabel(top, text=f"{icon}  {title}", font=T.font(13), text_color=T.MUTED).pack(side="left")
        self.value = ctk.CTkLabel(self, text="—", font=T.font(26, "bold"), anchor="w")
        self.value.grid(row=1, column=0, sticky="w", padx=16)
        self.detail = ctk.CTkLabel(self, text="", font=T.font(12), text_color=T.MUTED, anchor="w")
        self.detail.grid(row=2, column=0, sticky="w", padx=16)
        self.chart = Sparkline(self, color, height=70, second_color=second_color, max_value=max_value)
        self.chart.grid(row=3, column=0, sticky="ew", padx=12, pady=(6, 12))


class MonitorPage(Page):
    def __init__(self, master, app):
        super().__init__(master, app)
        self.sort = "cpu"
        self.last = None
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        self.header = PageHeader(self, "📈", "مراقب الأداء", "حالة جهازك لحظة بلحظة")
        self.header.grid(row=0, column=0, sticky="ew")

        grid = ctk.CTkFrame(self, fg_color="transparent")
        grid.grid(row=1, column=0, sticky="ew", pady=(14, 0))
        for i in range(4):
            grid.grid_columnconfigure(i, weight=1, uniform="m")
        self.cpu = _MetricCard(grid, "⚙️", "المعالج", "#7c6cff")
        self.mem = _MetricCard(grid, "🧠", "الذاكرة", "#22c55e")
        self.net = _MetricCard(grid, "🌐", "الشبكة", "#3b82f6", second_color="#ff5ca8", max_value=None)
        self.disk = _MetricCard(grid, "💽", "نشاط القرص", "#f59e0b", second_color="#06b6d4", max_value=None)
        for i, c in enumerate((self.cpu, self.mem, self.net, self.disk)):
            c.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 6, 0 if i == 3 else 6))

        # ---------------- البطارية
        self.battery = Card(self)
        self.battery_label = ctk.CTkLabel(self.battery, text="", font=T.font(14), anchor="w", justify="left")
        self.battery_label.pack(side="left", padx=18, pady=12)
        self.health_label = ctk.CTkLabel(self.battery, text="", font=T.font(13), text_color=T.MUTED)
        self.health_label.pack(side="right", padx=18)

        # ---------------- العمليات
        procs = Card(self)
        procs.grid(row=3, column=0, sticky="nsew", pady=(12, 0))
        procs.grid_columnconfigure(0, weight=1)
        procs.grid_rowconfigure(1, weight=1)
        bar = ctk.CTkFrame(procs, fg_color="transparent")
        bar.grid(row=0, column=0, columnspan=2, sticky="ew", padx=14, pady=(12, 4))
        ctk.CTkLabel(bar, text="🔥  التطبيقات الأكثر استهلاكاً", font=T.font(15, "bold")).pack(side="left")
        self.sort_seg = ctk.CTkSegmentedButton(bar, values=["المعالج", "الذاكرة"], command=self._on_sort,
                                               font=T.font(12))
        self.sort_seg.set("المعالج")
        self.sort_seg.pack(side="left", padx=14)
        ctk.CTkButton(bar, text="إنهاء إجباري", width=100, fg_color=T.TRACK, hover_color=T.HOVER,
                      text_color=T.DANGER, command=lambda: self._end(True)).pack(side="right")
        ctk.CTkButton(bar, text="إنهاء العملية", width=110, fg_color=T.DANGER, hover_color=T.DANGER_HOVER,
                      command=lambda: self._end(False)).pack(side="right", padx=8)
        self.tree = ttk.Treeview(procs, columns=("cpu", "mem", "pid", "user"), style="Pro.Treeview",
                                 selectmode="browse")
        self.tree.heading("#0", text="العملية", anchor="w")
        for col, title, w in (("cpu", "المعالج", 90), ("mem", "الذاكرة", 110), ("pid", "PID", 80),
                              ("user", "المستخدم", 140)):
            self.tree.heading(col, text=title, anchor="e" if col != "user" else "w")
            self.tree.column(col, width=w, anchor="e" if col != "user" else "w", stretch=False)
        self.tree.column("#0", width=300, stretch=True)
        self.tree.grid(row=1, column=0, sticky="nsew", padx=(10, 0), pady=(0, 10))
        sb = ctk.CTkScrollbar(procs, command=self.tree.yview)
        sb.grid(row=1, column=1, sticky="ns", pady=(0, 10))
        self.tree.configure(yscrollcommand=sb.set)
        self._battery_info = None

    # ------------------------------------------------------------ دورة الحياة
    def on_show(self):
        if not self.busy:
            self.start_job(mon.run_monitor, 1.0)
        if self._battery_info is None:
            self._battery_info = False
            self.app.run_job(CallbackListener(on_finished=self._battery_done),
                             lambda ctx: mon.battery_health())

    def on_hide(self):
        self.cancel_job()

    def _battery_done(self, info, _job):
        self._battery_info = info
        if info:
            parts = []
            if info.health_percent is not None:
                parts.append(f"صحة البطارية: {info.health_percent:.0f}% ({info.condition})")
            if info.cycle_count is not None:
                parts.append(f"دورات الشحن: {info.cycle_count:,}")
            self.health_label.configure(text="  •  ".join(parts))

    def on_custom(self, kind, payload):
        if kind == "sample":
            self._update(payload[0])

    # ------------------------------------------------------------ التحديث
    def _update(self, s: "mon.Sample"):
        self.last = s
        self.header.subtitle.configure(text=f"يعمل منذ {mon.format_duration(s.uptime)}"
                                            + (f"  •  الحِمل: {s.load[0]:.2f}" if s.load else ""))
        self.cpu.value.configure(text=f"{s.cpu:.0f}%")
        self.cpu.detail.configure(text=f"{len(s.per_cpu)} نواة")
        self.cpu.chart.push(s.cpu)
        self.mem.value.configure(text=f"{s.mem_percent:.0f}%")
        self.mem.detail.configure(text=f"{human_size(s.mem_used)} من {human_size(s.mem_total)}"
                                       + (f" • التبديل {human_size(s.swap_used)}" if s.swap_used else ""))
        self.mem.chart.push(s.mem_percent)
        self.net.value.configure(text=f"↓ {mon.format_rate(s.net_down)}")
        self.net.detail.configure(text=f"↑ {mon.format_rate(s.net_up)}  (وردي = رفع)")
        self.net.chart.push(s.net_down, s.net_up)
        self.disk.value.configure(text=f"R {mon.format_rate(s.disk_read)}")
        self.disk.detail.configure(text=f"W {mon.format_rate(s.disk_write)}")
        self.disk.chart.push(s.disk_read, s.disk_write)

        if s.battery is not None:
            self.battery.grid(row=2, column=0, sticky="ew", pady=(12, 0))
            state = "🔌 متصل بالشاحن" if s.plugged else "🔋 على البطارية"
            remaining = ""
            if s.battery_secs and not s.plugged:
                remaining = f" — متبقٍ {mon.format_duration(s.battery_secs)}"
            self.battery_label.configure(text=f"البطارية {s.battery:.0f}%   {state}{remaining}")

        if s.procs_cpu:
            self._fill_procs()

    def _on_sort(self, value):
        self.sort = "cpu" if value == "المعالج" else "mem"
        self._fill_procs()

    def _fill_procs(self):
        if not self.last or not self.last.procs_cpu:
            return
        rows = self.last.procs_cpu if self.sort == "cpu" else self.last.procs_mem
        selected = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        for p in rows:
            iid = str(p.pid)
            self.tree.insert("", "end", iid=iid, text=f"  {p.name}",
                             values=(f"{p.cpu:.1f}%", human_size(p.memory), p.pid, p.user))
        if selected and self.tree.exists(selected[0]):
            self.tree.selection_set(selected[0])

    def _end(self, force: bool):
        sel = self.tree.selection()
        if not sel:
            return
        pid = int(sel[0])
        name = self.tree.item(sel[0], "text").strip()
        verb = "إنهاء إجباري لـ" if force else "إنهاء"
        if not messagebox.askyesno("إنهاء العملية", f"{verb} «{name}»؟\nقد تفقد أي عمل غير محفوظ فيها.",
                                   icon="warning", parent=self.app):
            return
        error = mon.end_process(pid, force)
        if error:
            messagebox.showerror("تعذّر الإنهاء", error, parent=self.app)

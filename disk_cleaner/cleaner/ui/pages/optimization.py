"""optimization.py — التحسين: عناصر بدء التشغيل والوكلاء الخلفيون."""

from __future__ import annotations

import sys
from tkinter import messagebox, ttk
from typing import Dict, List

import customtkinter as ctk

from ...core import startup
from .. import theme as T
from ..widgets import Card, EmptyState, PageHeader, ProgressPanel, show_toast
from .base import CallbackListener, Page

IS_MAC = sys.platform == "darwin"


class OptimizationPage(Page):
    def __init__(self, master, app):
        super().__init__(master, app)
        self.items: Dict[str, startup.LaunchItem] = {}
        self.login_items: List[startup.LoginItem] = []
        self.loaded = False
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        header = PageHeader(self, "🚀", "التحسين",
                            "تحكّم فيما يعمل تلقائياً عند تشغيل الجهاز وفي الخلفية — أقل = أسرع")
        header.grid(row=0, column=0, sticky="ew")
        self.mode = ctk.CTkSegmentedButton(header.actions, values=["عناصر تسجيل الدخول", "الوكلاء الخلفيون"],
                                           command=self._switch, font=T.font(13), height=36)
        self.mode.set("الوكلاء الخلفيون")
        self.mode.pack()

        self.progress = ProgressPanel(self)
        self.progress.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        self.progress.grid_remove()

        # ---------------- الوكلاء الخلفيون
        self.agents_view = Card(self)
        self.login_view = Card(self)
        for v in (self.agents_view, self.login_view):
            v.grid(row=2, column=0, sticky="nsew", pady=(12, 0))
            v.grid_columnconfigure(0, weight=1)
            v.grid_rowconfigure(1, weight=1)

        bar = ctk.CTkFrame(self.agents_view, fg_color="transparent")
        bar.grid(row=0, column=0, columnspan=2, sticky="ew", padx=14, pady=(12, 4))
        self.agents_info = ctk.CTkLabel(bar, text="", font=T.font(12), text_color=T.MUTED, justify="left")
        self.agents_info.pack(side="left")
        ctk.CTkButton(bar, text="🗑 حذف", width=80, fg_color=T.DANGER, hover_color=T.DANGER_HOVER,
                      command=self._remove).pack(side="right")
        ctk.CTkButton(bar, text="▶ تشغيل", width=80, fg_color=T.TRACK, hover_color=T.HOVER,
                      text_color=T.TEXT, command=lambda: self._toggle(True)).pack(side="right", padx=6)
        ctk.CTkButton(bar, text="⏸ إيقاف", width=80, command=lambda: self._toggle(False)).pack(side="right")
        ctk.CTkButton(bar, text="📂", width=40, fg_color=T.TRACK, hover_color=T.HOVER, text_color=T.TEXT,
                      command=self._reveal).pack(side="right", padx=6)

        self.tree = ttk.Treeview(self.agents_view, columns=("state", "scope", "program"),
                                 style="Pro.Treeview", selectmode="browse")
        self.tree.heading("#0", text="العنصر", anchor="w")
        self.tree.column("#0", width=280, stretch=False)
        for col, title, w, stretch in (("state", "الحالة", 110, False), ("scope", "النوع", 150, False),
                                       ("program", "البرنامج", 400, True)):
            self.tree.heading(col, text=title, anchor="w")
            self.tree.column(col, width=w, anchor="w", stretch=stretch)
        self.tree.grid(row=1, column=0, sticky="nsew", padx=(10, 0), pady=(0, 10))
        sb = ctk.CTkScrollbar(self.agents_view, command=self.tree.yview)
        sb.grid(row=1, column=1, sticky="ns", pady=(0, 10))
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.tag_configure("off", foreground=T.resolve(T.FAINT))
        self.tree.tag_configure("broken", foreground=T.WARNING)

        # ---------------- عناصر تسجيل الدخول
        lbar = ctk.CTkFrame(self.login_view, fg_color="transparent")
        lbar.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 4))
        self.login_info = ctk.CTkLabel(lbar, text="التطبيقات التي تُفتح تلقائياً عند تسجيل الدخول.",
                                       font=T.font(12), text_color=T.MUTED)
        self.login_info.pack(side="left")
        ctk.CTkButton(lbar, text="⚙️ إعدادات النظام", width=130, fg_color=T.TRACK, hover_color=T.HOVER,
                      text_color=T.TEXT, command=startup.open_login_items_settings).pack(side="right")
        ctk.CTkButton(lbar, text="🗑 إزالة من بدء التشغيل", width=170, fg_color=T.DANGER,
                      hover_color=T.DANGER_HOVER, command=self._remove_login).pack(side="right", padx=8)
        self.login_list = ttk.Treeview(self.login_view, columns=("path",), style="Pro.Treeview",
                                       selectmode="browse")
        self.login_list.heading("#0", text="التطبيق", anchor="w")
        self.login_list.heading("path", text="المكان", anchor="w")
        self.login_list.column("#0", width=260, stretch=False)
        self.login_list.column("path", width=500, stretch=True)
        self.login_list.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        self.login_empty = EmptyState(self.login_view, "🚀", "لا توجد عناصر",
                                      "لا تفتح أي تطبيقات تلقائياً عند تسجيل الدخول.")
        self.agents_view.tkraise()

    def _switch(self, value):
        (self.login_view if value == "عناصر تسجيل الدخول" else self.agents_view).tkraise()
        if value == "عناصر تسجيل الدخول":
            self._load_login()

    def on_show(self):
        if not self.loaded:
            self.loaded = True
            self.refresh()

    # ------------------------------------------------------------ الوكلاء
    def refresh(self):
        self.progress.grid()
        self.progress.start("قراءة العناصر الخلفية...")
        self.start_job(startup.list_launch_items)

    def on_finished(self, result, job):
        self.progress.grid_remove()
        if result is None:
            return
        self.items = {it.path: it for it in result}
        self.tree.delete(*self.tree.get_children())
        groups = {"user": "👤 وكلاء المستخدم", "agent": "👥 وكلاء لكل المستخدمين", "daemon": "🛠 خدمات النظام"}
        for scope, title in groups.items():
            members = [i for i in result if i.scope == scope]
            if not members:
                continue
            self.tree.insert("", "end", iid=scope, text=f"  {title}  ({len(members)})", open=True,
                             tags=("group",))
            for it in members:
                state = "🟢 يعمل" if it.enabled else "⏸ متوقف"
                tags = () if it.enabled else ("off",)
                if not it.program_exists:
                    state, tags = "⚠️ بقايا", ("broken",)
                self.tree.insert(scope, "end", iid=it.path, text=f"  {it.label}",
                                 values=(state, startup.SCOPE_LABEL[it.scope], it.program), tags=tags)
        on = sum(1 for i in result if i.enabled)
        broken = sum(1 for i in result if not i.program_exists)
        text = f"{len(result)} عنصر خلفي — {on} يعمل"
        if broken:
            text += f" — ⚠️ {broken} بقايا لبرامج محذوفة (يمكن حذفها بأمان)"
        self.agents_info.configure(text=text)
        self.tree.tag_configure("group", font=T.tk_font(13, "bold"))

    def _selected(self):
        sel = self.tree.selection()
        return self.items.get(sel[0]) if sel else None

    def _reveal(self):
        item = self._selected()
        if item:
            self.app.files.reveal(item.path)

    def _run_action(self, fn, *args, done_text: str):
        def work(ctx):
            return fn(*args)

        def done(result, _job):
            ok, msg = result if result else (False, "")
            if ok:
                show_toast(self.app, done_text, "✅")
            else:
                messagebox.showerror("تعذّر التنفيذ", msg or "فشلت العملية.", parent=self.app)
            self.refresh()

        self.app.run_job(CallbackListener(on_finished=done, parent=self.app), work)

    def _toggle(self, enable: bool):
        item = self._selected()
        if not item:
            return
        self._run_action(startup.set_enabled, item, enable,
                         done_text=f"تم {'تشغيل' if enable else 'إيقاف'} {item.label}")

    def _remove(self):
        item = self._selected()
        if not item:
            return
        if not messagebox.askyesno("حذف العنصر الخلفي",
                                   f"سيتم إيقاف «{item.label}» ونقل ملفه إلى سلة المحذوفات.\n"
                                   "قد يتوقف التحديث التلقائي للتطبيق المرتبط به. متابعة؟",
                                   icon="warning", parent=self.app):
            return
        self._run_action(startup.remove_item, item, done_text=f"تم حذف {item.label}")

    # ------------------------------------------------------------ تسجيل الدخول
    def _load_login(self):
        def done(result, _job):
            items, error = result if result else ([], None)
            self.login_items = items
            self.login_list.delete(*self.login_list.get_children())
            for n, it in enumerate(items):
                self.login_list.insert("", "end", iid=str(n), text=f"  {it.name}", values=(it.path,))
            if error:
                self.login_info.configure(text=error, text_color=T.WARNING)
            if not items and not error:
                self.login_empty.grid(row=1, column=0, sticky="nsew")
            else:
                self.login_empty.grid_remove()

        self.app.run_job(CallbackListener(on_finished=done, parent=self.app),
                         lambda ctx: startup.list_login_items())

    def _remove_login(self):
        sel = self.login_list.selection()
        if not sel:
            return
        item = self.login_items[int(sel[0])]

        def work(ctx):
            return startup.remove_login_item(item.name)

        def done(result, _job):
            ok, msg = result if result else (False, "")
            if ok:
                show_toast(self.app, f"لن يُفتح {item.name} تلقائياً بعد الآن", "✅")
            else:
                messagebox.showerror("تعذّر الإزالة", msg, parent=self.app)
            self._load_login()

        self.app.run_job(CallbackListener(on_finished=done, parent=self.app), work)

"""extensions.py — مدير الإضافات: إضافات النظام وإضافات المتصفحات."""

from __future__ import annotations

from tkinter import ttk

import customtkinter as ctk

from ...core import extensions as ext_core
from ...core.models import human_size
from .. import theme as T
from ..checktree import CheckTree, Group
from ..widgets import Card, EmptyState, GradientButton, PageHeader
from .base import CallbackListener, Page

COLUMNS = (("size", "الحجم", 100, "e"), ("info", "النوع", 180, "w"), ("path", "المكان", 420, "w"))


class ExtensionsPage(Page):
    def __init__(self, master, app):
        super().__init__(master, app)
        self.loaded = False
        self.browser_exts = []
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = PageHeader(self, "🧩", "الإضافات",
                            "إضافات النظام والمتصفحات — احذف ما لا تستخدمه لتسريع جهازك ومتصفحك")
        header.grid(row=0, column=0, sticky="ew")
        self.mode = ctk.CTkSegmentedButton(header.actions, values=["إضافات النظام", "إضافات المتصفحات"],
                                           command=self._switch, font=T.font(13), height=36)
        self.mode.set("إضافات النظام")
        self.mode.pack()

        # ---------------- إضافات النظام
        self.sys_view = ctk.CTkFrame(self, fg_color="transparent")
        self.browser_view = Card(self)
        for v in (self.sys_view, self.browser_view):
            v.grid(row=1, column=0, sticky="nsew", pady=(14, 0))
            v.grid_columnconfigure(0, weight=1)
        self.sys_view.grid_rowconfigure(0, weight=1)
        self.tree = CheckTree(self.sys_view, COLUMNS, on_change=self._update_footer, actions=app.files)
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.sys_empty = EmptyState(self.sys_view, "🧩", "لا توجد إضافات نظام",
                                    "لم نجد لوحات تفضيلات أو إضافات Quick Look أو Spotlight مثبتة.")
        footer = ctk.CTkFrame(self.sys_view, fg_color="transparent")
        footer.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        self.summary = ctk.CTkLabel(footer, text="", font=T.font(13), text_color=T.MUTED)
        self.summary.pack(side="left")
        self.remove_btn = GradientButton(footer, "🗑  إزالة المحدد", self.remove, width=200, height=46,
                                         colors=T.GRADIENT_DANGER)
        self.remove_btn.pack(side="right")

        # ---------------- إضافات المتصفحات
        self.browser_view.grid_rowconfigure(1, weight=1)
        bar = ctk.CTkFrame(self.browser_view, fg_color="transparent")
        bar.grid(row=0, column=0, columnspan=2, sticky="ew", padx=14, pady=(12, 4))
        ctk.CTkLabel(bar, text="لحذف إضافة متصفح بأمان نفتح صفحة الإضافات في المتصفح نفسه "
                               "(الحذف المباشر يجعل المزامنة تعيدها).", font=T.font(12),
                     text_color=T.MUTED).pack(side="left")
        ctk.CTkButton(bar, text="🌐 إدارة في المتصفح", width=150, command=self._open_browser).pack(side="right")
        self.btree = ttk.Treeview(self.browser_view, columns=("version", "id"), style="Pro.Treeview",
                                  selectmode="browse")
        self.btree.heading("#0", text="الإضافة", anchor="w")
        self.btree.heading("version", text="الإصدار", anchor="w")
        self.btree.heading("id", text="المعرّف", anchor="w")
        self.btree.column("#0", width=340, stretch=True)
        self.btree.column("version", width=110, stretch=False)
        self.btree.column("id", width=300, stretch=False)
        self.btree.grid(row=1, column=0, sticky="nsew", padx=(10, 0), pady=(0, 10))
        sb = ctk.CTkScrollbar(self.browser_view, command=self.btree.yview)
        sb.grid(row=1, column=1, sticky="ns", pady=(0, 10))
        self.btree.configure(yscrollcommand=sb.set)
        self.sys_view.tkraise()
        self._update_footer()

    def _switch(self, value):
        (self.browser_view if value == "إضافات المتصفحات" else self.sys_view).tkraise()

    def on_show(self):
        if self.loaded:
            return
        self.loaded = True

        def work(ctx):
            return ext_core.system_extensions(ctx), ext_core.browser_extensions()

        self.app.run_job(CallbackListener(on_finished=self._loaded, parent=self.app), work)

    def _loaded(self, result, _job):
        if not result:
            return
        system, browsers = result
        self.tree.set_groups([Group(k, k, v) for k, v in system.items()], expand=True)
        if not system:
            self.sys_empty.grid(row=0, column=0, sticky="nsew")
        self.browser_exts = browsers
        self.btree.delete(*self.btree.get_children())
        by_browser = {}
        for e in browsers:
            by_browser.setdefault(e.browser, []).append(e)
        for browser, exts in by_browser.items():
            self.btree.insert("", "end", iid=browser, text=f"  🌐 {browser}  ({len(exts)})", open=True)
            for n, e in enumerate(exts):
                self.btree.insert(browser, "end", iid=f"{browser}::{n}", text=f"  {e.name}",
                                  values=(e.version, e.ext_id))
        if not browsers:
            self.btree.insert("", "end", text="  لم يتم العثور على إضافات متصفحات.")

    def _open_browser(self):
        sel = self.btree.selection()
        if sel:
            ext_core.open_extensions_page(sel[0].split("::")[0])

    def _update_footer(self):
        items = self.tree.checked_items()
        self.summary.configure(text=f"{len(items)} محدد ({human_size(sum(i.size for i in items))})"
                               if items else "حدد الإضافات التي تريد إزالتها")
        self.remove_btn.configure_button(enabled=bool(items))

    def remove(self):
        self.app.delete_items(self.tree.checked_items(),
                              lambda d, f: self.tree.remove_paths({i.path for i in d}),
                              title="إزالة الإضافات", action_text="إزالة")

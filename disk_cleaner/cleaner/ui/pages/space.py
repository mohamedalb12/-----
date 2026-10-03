"""space.py — خريطة المساحة: تصفّح المجلدات مرتبة حسب الحجم مع توزيع الأنواع."""

from __future__ import annotations

import os
import sys
import tkinter as tk
from tkinter import filedialog

import customtkinter as ctk

from ...core.models import Category, FileItem, KINDS, human_size, kind_of, short_path
from ...core.space import DirNode, build_space_tree
from .. import theme as T
from ..widgets import BarList, Card, Donut, EmptyState, GradientButton, PageHeader, ProgressPanel
from .base import Page

IS_MAC = sys.platform == "darwin"
MAX_ROWS = 80


class SpacePage(Page):
    def __init__(self, master, app):
        super().__init__(master, app)
        self.tree: DirNode = None
        self.node: DirNode = None
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        header = PageHeader(self, "🗺", "خريطة المساحة",
                            "شاهد أين تذهب مساحتك، وتنقّل بين المجلدات مرتبة من الأكبر للأصغر")
        header.grid(row=0, column=0, sticky="ew")
        self.root_choice = ctk.CTkSegmentedButton(header.actions, values=["🏠 مجلد المستخدم", "💽 القرص كامل",
                                                                          "📁 اختيار..."],
                                                  command=self._on_root, font=T.font(12), height=36)
        self.root_choice.set("🏠 مجلد المستخدم")
        self.root_choice.pack(side="left", padx=(0, 10))
        self.root_path = os.path.expanduser("~")
        self.scan_btn = GradientButton(header.actions, "🔍  تحليل", self.scan, width=130, height=40,
                                       font_size=14)
        self.scan_btn.pack(side="left")

        self.progress = ProgressPanel(self, on_cancel=self.cancel_job)
        self.progress.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        self.progress.grid_remove()

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=2, column=0, sticky="nsew", pady=(12, 0))
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(0, weight=1)

        main = Card(body)
        main.grid(row=0, column=0, sticky="nsew")
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(1, weight=1)
        crumbs = ctk.CTkFrame(main, fg_color="transparent")
        crumbs.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 4))
        crumbs.grid_columnconfigure(1, weight=1)
        self.up_btn = ctk.CTkButton(crumbs, text="⬆︎ للأعلى", width=90, height=32, fg_color=T.TRACK,
                                    hover_color=T.HOVER, text_color=T.TEXT, command=self.go_up)
        self.up_btn.grid(row=0, column=0)
        self.path_label = ctk.CTkLabel(crumbs, text="", font=T.font(14, "bold"), anchor="w")
        self.path_label.grid(row=0, column=1, sticky="ew", padx=12)
        self.total_label = ctk.CTkLabel(crumbs, text="", font=T.font(13), text_color=T.ACCENT)
        self.total_label.grid(row=0, column=2)
        self.bars = BarList(main, on_open=self._open_row, on_menu=self._row_menu)
        self.bars.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 10))
        self.empty = EmptyState(main, "🗺", "اكتشف أين تذهب مساحتك",
                                "اضغط «تحليل» لبناء خريطة لكل المجلدات. بعدها يصبح التنقّل فورياً — "
                                "نقرة مزدوجة لفتح مجلد، وزر يمين لخيارات أكثر.")
        self.empty.grid(row=0, column=0, rowspan=2, sticky="nsew")

        side = Card(body, width=300)
        side.grid(row=0, column=1, sticky="ns", padx=(14, 0))
        side.grid_propagate(False)
        ctk.CTkLabel(side, text="حسب نوع الملف", font=T.font(15, "bold")).pack(pady=(18, 6))
        self.donut = Donut(side, size=190, thickness=20)
        self.donut.pack(pady=6)
        self.legend = ctk.CTkFrame(side, fg_color="transparent")
        self.legend.pack(fill="x", padx=18, pady=(6, 12))

        self.menu = tk.Menu(self, tearoff=0)
        self._menu_row = None
        self.menu.add_command(label="فتح", command=lambda: self._menu_action("open"))
        self.menu.add_command(label="معاينة سريعة", command=lambda: self._menu_action("quick_look"))
        self.menu.add_command(label="إظهار في Finder" if IS_MAC else "فتح في المجلد",
                              command=lambda: self._menu_action("reveal"))
        self.menu.add_separator()
        self.menu.add_command(label="حذف...", command=self._delete_row)

    # ------------------------------------------------------------ الفحص
    def _on_root(self, value):
        if value.startswith("📁"):
            folder = filedialog.askdirectory(parent=self.app, initialdir=self.root_path)
            if folder:
                self.root_path = folder
                self.root_choice.configure(values=["🏠 مجلد المستخدم", "💽 القرص كامل",
                                                   f"📁 {os.path.basename(folder) or folder}"])
                self.root_choice.set(f"📁 {os.path.basename(folder) or folder}")
            else:
                self.root_choice.set("🏠 مجلد المستخدم")
                self.root_path = os.path.expanduser("~")
        elif value.startswith("💽"):
            self.root_path = os.path.abspath(os.sep)
        else:
            self.root_path = os.path.expanduser("~")

    def scan(self):
        self.scan_btn.configure_button(enabled=False)
        self.progress.grid()
        self.progress.start(f"جارٍ تحليل {short_path(self.root_path)}...")
        self.start_job(build_space_tree, self.root_path, self.app.settings.excluded)

    def on_progress(self, fraction, text):
        self.progress.update_progress(fraction, text)

    def on_finished(self, result, job):
        self.scan_btn.configure_button(enabled=True)
        if result is None:
            self.progress.finish(self.summary_text(job), complete=False)
            return
        tree, kinds = result
        self.progress.finish(self.summary_text(job, f"{human_size(tree.size)} في {tree.file_count:,} ملف"),
                             complete=not job.cancelled)
        self.tree = tree
        self._show_kinds(kinds)
        self.show_node(tree)
        self.empty.lower()

    # ------------------------------------------------------------ العرض
    def _show_kinds(self, kinds):
        for w in self.legend.winfo_children():
            w.destroy()
        total = sum(kinds.values()) or 1
        ordered = sorted(kinds.items(), key=lambda kv: kv[1], reverse=True)
        self.donut.set([(v, KINDS[k][2]) for k, v in ordered], human_size(total), "إجمالي")
        for key, value in ordered:
            label, icon, color, _ = KINDS[key]
            row = ctk.CTkFrame(self.legend, fg_color="transparent")
            row.pack(fill="x", pady=2)
            row.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(row, text="", width=10, height=10, corner_radius=5, fg_color=color).grid(
                row=0, column=0, padx=(0, 8))
            ctk.CTkLabel(row, text=f"{icon} {label}", font=T.font(12), anchor="w").grid(
                row=0, column=1, sticky="w")
            ctk.CTkLabel(row, text=human_size(value), font=T.font(12, "bold"),
                         text_color=T.MUTED).grid(row=0, column=2, sticky="e", padx=(8, 0))

    def show_node(self, node: DirNode):
        self.node = node
        self.path_label.configure(text=short_path(node.path))
        self.total_label.configure(text=f"{human_size(node.size)} • {node.file_count:,} ملف")
        self.up_btn.configure(state="normal" if node.parent else "disabled")
        rows = []
        total = node.size or 1
        children = node.children()
        accent = T.resolve(T.ACCENT)
        for name, path, size, is_dir in children[:MAX_ROWS]:
            if is_dir:
                icon, color = "📁", accent
            else:
                _label, icon, color, _ = KINDS[kind_of(name)]
            rows.append((icon, name, human_size(size), size / total, color, (path, size, is_dir)))
        rest = children[MAX_ROWS:]
        if rest:
            rest_size = sum(r[2] for r in rest)
            rows.append(("…", f"{len(rest):,} عنصر آخر", human_size(rest_size), rest_size / total,
                         T.resolve(T.FAINT), None))
        hidden = node.size - sum(r[2] for r in children)
        if hidden > total * 0.001:
            rows.append(("📄", "ملفات أصغر", human_size(hidden), hidden / total, T.resolve(T.FAINT), None))
        self.bars.set_rows(rows)

    def go_up(self):
        if self.node and self.node.parent:
            self.show_node(self.node.parent)

    def _open_row(self, row):
        payload = row[5]
        if not payload:
            return
        path, _size, is_dir = payload
        if is_dir:
            child = self.node.find_dir(path)
            if child:
                self.show_node(child)
        else:
            self.app.files.open(path)

    def _row_menu(self, row, event):
        if not row[5]:
            return
        self._menu_row = row
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    def _menu_action(self, name):
        if self._menu_row and self._menu_row[5]:
            getattr(self.app.files, name)(self._menu_row[5][0])

    def _delete_row(self):
        if not self._menu_row or not self._menu_row[5]:
            return
        path, size, is_dir = self._menu_row[5]
        node = self.node
        item = FileItem(path, size, Category.LARGE, is_dir=is_dir)

        def done(deleted, _failed):
            if deleted:
                node.remove_child(path, size)
                if self.node is node:
                    self.show_node(node)
                self.total_label.configure(text=f"{human_size(node.size)} • {node.file_count:,} ملف")

        self.app.delete_items([item], done)

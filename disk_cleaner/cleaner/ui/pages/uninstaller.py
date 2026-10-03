"""uninstaller.py — إلغاء تثبيت التطبيقات بالكامل + بقايا التطبيقات المحذوفة."""

from __future__ import annotations

import sys
from collections import defaultdict
from tkinter import messagebox, ttk
from typing import Dict, List, Optional

import customtkinter as ctk

from ...core import apps as apps_core
from ...core.apps import AppInfo
from ...core.models import Category, FileItem, human_size, short_path
from .. import theme as T
from ..checktree import CheckTree, Group
from ..widgets import Card, EmptyState, GradientButton, PageHeader, ProgressPanel
from .base import CallbackListener, Page

IS_MAC = sys.platform == "darwin"
COLUMNS = (("size", "الحجم", 100, "e"), ("info", "النوع", 150, "w"), ("path", "المكان", 360, "w"))


def _placeholder_icon(size: int):
    from PIL import Image, ImageDraw
    s = 4
    img = Image.new("RGBA", (size * s, size * s), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle([s * 2, s * 2, size * s - s * 2, size * s - s * 2],
                                          radius=size * s // 4, fill=(124, 108, 255, 255))
    return img.resize((size, size), Image.LANCZOS)


class UninstallerPage(Page):
    def __init__(self, master, app):
        super().__init__(master, app)
        self.apps: List[AppInfo] = []
        self.by_path: Dict[str, AppInfo] = {}
        self.icons_big: Dict[str, object] = {}
        self.icons_small: Dict[str, object] = {}
        self.selected: Optional[AppInfo] = None
        self.files_job = None
        self.loaded = False
        self.sort_by = "name"
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = PageHeader(self, "🧩", "إلغاء تثبيت التطبيقات",
                            "احذف التطبيق مع كل ملفاته المتناثرة في النظام — بلا أي بقايا")
        header.grid(row=0, column=0, sticky="ew")
        self.mode = ctk.CTkSegmentedButton(header.actions, values=["التطبيقات", "بقايا تطبيقات محذوفة"],
                                           command=self._switch, font=T.font(13), height=36)
        self.mode.set("التطبيقات")
        self.mode.pack()

        self.apps_view = ctk.CTkFrame(self, fg_color="transparent")
        self.orphans_view = ctk.CTkFrame(self, fg_color="transparent")
        for v in (self.apps_view, self.orphans_view):
            v.grid(row=1, column=0, sticky="nsew", pady=(14, 0))
        self._build_apps_view()
        self._build_orphans_view()
        self.apps_view.tkraise()

    # ================================================================ التطبيقات
    def _build_apps_view(self):
        v = self.apps_view
        v.grid_columnconfigure(1, weight=1)
        v.grid_rowconfigure(0, weight=1)

        left = Card(v, width=330)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        left.grid_propagate(False)
        left.grid_columnconfigure(0, weight=1)
        left.grid_rowconfigure(2, weight=1)
        self.search = ctk.CTkEntry(left, placeholder_text="🔎  ابحث عن تطبيق...", height=36)
        self.search.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))
        self.search.bind("<KeyRelease>", lambda _e: self._fill_list())
        self.sort_seg = ctk.CTkSegmentedButton(left, values=["حسب الاسم", "حسب الحجم"],
                                               command=self._on_sort, font=T.font(12))
        self.sort_seg.set("حسب الاسم")
        self.sort_seg.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 6))
        self.list = ttk.Treeview(left, columns=("size",), style="Apps.Treeview", show="tree",
                                 selectmode="browse")
        self.list.column("#0", width=200, stretch=True)
        self.list.column("size", width=80, anchor="e", stretch=False)
        self.list.grid(row=2, column=0, sticky="nsew", padx=(10, 0), pady=(0, 10))
        sb = ctk.CTkScrollbar(left, command=self.list.yview)
        sb.grid(row=2, column=1, sticky="ns", pady=(0, 10))
        self.list.configure(yscrollcommand=sb.set)
        self.list.bind("<<TreeviewSelect>>", self._on_pick)
        self.list_status = ctk.CTkLabel(left, text="", font=T.font(11), text_color=T.MUTED)
        self.list_status.grid(row=3, column=0, columnspan=2, pady=(0, 8))

        right = Card(v)
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(2, weight=1)
        self.right = right

        head = ctk.CTkFrame(right, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 6))
        head.grid_columnconfigure(1, weight=1)
        self.icon_label = ctk.CTkLabel(head, text="", width=72, height=72)
        self.icon_label.grid(row=0, column=0, rowspan=3, padx=(0, 14))
        self.name_label = ctk.CTkLabel(head, text="", font=T.font(22, "bold"), anchor="w")
        self.name_label.grid(row=0, column=1, sticky="sw")
        self.meta_label = ctk.CTkLabel(head, text="", font=T.font(12), text_color=T.MUTED, anchor="w")
        self.meta_label.grid(row=1, column=1, sticky="w")
        self.size_label = ctk.CTkLabel(head, text="", font=T.font(13, "bold"), text_color=T.ACCENT,
                                       anchor="w")
        self.size_label.grid(row=2, column=1, sticky="nw")

        self.files_progress = ProgressPanel(right)
        self.files_progress.grid(row=1, column=0, sticky="ew", padx=18)
        self.files_progress.grid_remove()

        body = ctk.CTkFrame(right, fg_color="transparent")
        body.grid(row=2, column=0, sticky="nsew", padx=12, pady=6)
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(0, weight=1)
        self.files_tree = CheckTree(body, COLUMNS, on_change=self._update_buttons, actions=self.app.files)
        self.files_tree.grid(row=0, column=0, sticky="nsew")
        self.detail_empty = EmptyState(body, "🧩", "اختر تطبيقاً",
                                       "سنعرض لك التطبيق وكل ملفاته: الإعدادات، الكاش، بيانات الدعم، "
                                       "الحاويات، وعناصر بدء التشغيل.")
        self.detail_empty.grid(row=0, column=0, sticky="nsew")

        foot = ctk.CTkFrame(right, fg_color="transparent")
        foot.grid(row=3, column=0, sticky="ew", padx=18, pady=(4, 18))
        self.note_label = ctk.CTkLabel(foot, text="", font=T.font(12), text_color=T.WARNING)
        self.note_label.pack(side="left")
        self.uninstall_btn = GradientButton(foot, "🗑  إلغاء التثبيت", self.uninstall, width=230,
                                            height=48, colors=T.GRADIENT_DANGER)
        self.uninstall_btn.pack(side="right")
        self.reset_btn = ctk.CTkButton(foot, text="↺  إعادة ضبط", width=120, height=40,
                                       fg_color=T.TRACK, hover_color=T.HOVER, text_color=T.TEXT,
                                       command=self.reset_app)
        self.reset_btn.pack(side="right", padx=10)
        self._update_buttons()

    def on_show(self):
        if not self.loaded:
            self.loaded = True
            self._load_apps()

    def _load_apps(self):
        self.apps = apps_core.list_apps()
        self.by_path = {a.path: a for a in self.apps}
        placeholder = _placeholder_icon(28)
        from PIL import ImageTk
        self._placeholder = ImageTk.PhotoImage(placeholder)
        self._fill_list()
        if self.apps:
            self.list_status.configure(text="جارٍ حساب الأحجام وتحميل الأيقونات...")
            self.app.run_job(CallbackListener(on_custom=self._on_app_details,
                                              on_finished=self._details_done, parent=self.app),
                             apps_core.compute_app_details, self.apps, 72)
        else:
            self.list_status.configure(text="لم يتم العثور على تطبيقات في /Applications")

    def _on_app_details(self, kind, payload):
        if kind != "app_details":
            return
        path, size, icon = payload
        app = self.by_path.get(path)
        if not app:
            return
        app.size = size
        if icon is not None:
            from PIL import ImageTk
            self.icons_big[path] = icon
            self.icons_small[path] = ImageTk.PhotoImage(icon.resize((28, 28)))
        if self.list.exists(path):
            self.list.item(path, image=self.icons_small.get(path, self._placeholder),
                           values=(human_size(size),))
        if self.selected and self.selected.path == path:
            self._show_header(app)

    def _details_done(self, _result, _job):
        total = sum(a.size for a in self.apps if a.size > 0)
        self.list_status.configure(text=f"{len(self.apps)} تطبيق — {human_size(total)}")
        if self.sort_by == "size":
            self._fill_list()

    def _on_sort(self, value):
        self.sort_by = "size" if value == "حسب الحجم" else "name"
        self._fill_list()

    def _fill_list(self):
        query = self.search.get().strip().lower()
        apps = [a for a in self.apps if not query or query in a.name.lower()]
        if self.sort_by == "size":
            apps.sort(key=lambda a: a.size, reverse=True)
        self.list.delete(*self.list.get_children())
        for a in apps:
            self.list.insert("", "end", iid=a.path, text=f"  {a.name}",
                             image=self.icons_small.get(a.path, self._placeholder),
                             values=(human_size(a.size) if a.size >= 0 else "…",))
        if self.selected and self.list.exists(self.selected.path):
            self.list.selection_set(self.selected.path)

    def _on_pick(self, _event):
        sel = self.list.selection()
        if not sel or (self.selected and self.selected.path == sel[0]):
            return
        app = self.by_path.get(sel[0])
        if app:
            self.select_app(app)

    def _show_header(self, app: AppInfo):
        icon = self.icons_big.get(app.path) or _placeholder_icon(72)
        self._big_icon = ctk.CTkImage(icon, size=(72, 72))
        self.icon_label.configure(image=self._big_icon)
        self.name_label.configure(text=app.name)
        meta = "  •  ".join(x for x in (f"الإصدار {app.version}" if app.version else "", app.bundle_id) if x)
        self.meta_label.configure(text=meta or short_path(app.path))
        self.size_label.configure(text=f"حجم التطبيق: {human_size(app.size)}" if app.size >= 0 else "")

    def select_app(self, app: AppInfo):
        self.selected = app
        self._show_header(app)
        self.files_tree.set_groups([])
        self.detail_empty.set("جارٍ البحث عن ملفات التطبيق...", "")
        self.detail_empty.lift()
        self.files_progress.grid()
        self.files_progress.start("جارٍ البحث عن ملفات التطبيق في ~/Library ...")
        self._update_buttons()

        def work(ctx, app):
            size = app.size if app.size >= 0 else apps_core.dir_size(app.path, ctx)
            return size, apps_core.find_app_files(app, ctx)

        self.files_job = self.app.run_job(
            CallbackListener(on_finished=lambda r, j: self._files_found(app, r, j), parent=self.app),
            work, app)

    def _files_found(self, app: AppInfo, result, job):
        if job is not self.files_job or self.selected is not app:
            return
        self.files_progress.grid_remove()
        if result is None:
            return
        size, files = result
        app.size = size
        bundle = FileItem(app.path, size, Category.APP, is_dir=True, note="حزمة التطبيق")
        groups = [Group("app", "🧩  التطبيق", [bundle], checked=not app.is_system)]
        by_note = defaultdict(list)
        for f in files:
            by_note[f.note].append(f)
        for note, items in by_note.items():
            groups.append(Group(note, f"📁  {note}", items, checked=not app.is_system))
        self.files_tree.set_groups(groups, expand=True)
        self.detail_empty.lower()
        total = size + sum(f.size for f in files)
        self.size_label.configure(text=f"الحجم الكلي مع الملفات المرتبطة: {human_size(total)}")
        self._update_buttons()

    def _update_buttons(self):
        app = self.selected
        checked = self.files_tree.checked_items() if app else []
        size = sum(i.size for i in checked)
        if app and app.is_system:
            self.note_label.configure(text="🔒 تطبيق نظام من Apple — لا يمكن حذفه")
        else:
            self.note_label.configure(text="")
        can = bool(app and checked and not app.is_system)
        self.uninstall_btn.configure_button(
            text=f"🗑  إلغاء التثبيت ({human_size(size)})" if can else "🗑  إلغاء التثبيت", enabled=can)
        leftovers = [i for i in checked if app and i.path != app.path]
        self.reset_btn.configure(state="normal" if leftovers and not app.is_system else "disabled")

    def _ensure_closed(self, app: AppInfo) -> bool:
        if not apps_core.is_running(app):
            return True
        answer = messagebox.askyesnocancel(
            "التطبيق يعمل الآن", f"«{app.name}» مفتوح حالياً.\nهل تريد إغلاقه والمتابعة؟",
            parent=self.app)
        if not answer:
            return False
        apps_core.quit_app(app)
        return True

    def uninstall(self):
        app = self.selected
        if not app or not self._ensure_closed(app):
            return
        self.app.delete_items(self.files_tree.checked_items(), lambda d, f: self._after_delete(app, d),
                              title="إلغاء تثبيت التطبيق", action_text="إلغاء تثبيت")

    def reset_app(self):
        """حذف ملفات التطبيق فقط مع إبقائه — يعيده لحالته عند أول تثبيت."""
        app = self.selected
        if not app or not self._ensure_closed(app):
            return
        items = [i for i in self.files_tree.checked_items() if i.path != app.path]
        self.app.delete_items(items, lambda d, f: self._after_delete(app, d),
                              title="إعادة ضبط التطبيق", action_text="إعادة ضبط",
                              warning="سيبقى التطبيق مثبتاً، لكن ستُحذف إعداداته وبياناته.")

    def _after_delete(self, app: AppInfo, deleted):
        gone = {i.path for i in deleted}
        if app.path in gone:
            self.apps = [a for a in self.apps if a.path != app.path]
            self.by_path.pop(app.path, None)
            if self.selected is app:
                self.selected = None
                self.files_tree.set_groups([])
                self.icon_label.configure(image=None)
                self.name_label.configure(text="")
                self.meta_label.configure(text="")
                self.size_label.configure(text="")
                self.detail_empty.set("تم إلغاء التثبيت بنجاح ✨", "اختر تطبيقاً آخر من القائمة.")
                self.detail_empty.lift()
            self._fill_list()
        else:
            self.files_tree.remove_paths(gone)
        self._update_buttons()

    # ================================================================ البقايا
    def _build_orphans_view(self):
        v = self.orphans_view
        v.grid_columnconfigure(0, weight=1)
        v.grid_rowconfigure(2, weight=1)
        bar = Card(v)
        bar.grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(bar, text="🧹  ملفات بقيت من تطبيقات حذفتها سابقاً (إعدادات، كاش، بيانات دعم).\n"
                               "راجعها قبل الحذف — لا يتم تحديد شيء تلقائياً.",
                     font=T.font(13), justify="left", anchor="w").pack(side="left", padx=18, pady=14)
        self.orphan_btn = GradientButton(bar, "🔍  بحث", self.scan_orphans, width=130, height=40,
                                         font_size=14)
        self.orphan_btn.pack(side="right", padx=18)
        self.orphan_progress = ProgressPanel(v, on_cancel=self.cancel_job)
        self.orphan_progress.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        self.orphan_progress.grid_remove()
        body = ctk.CTkFrame(v, fg_color="transparent")
        body.grid(row=2, column=0, sticky="nsew", pady=(12, 0))
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(0, weight=1)
        self.orphan_tree = CheckTree(body, COLUMNS, on_change=self._update_orphan_footer,
                                     actions=self.app.files)
        self.orphan_tree.grid(row=0, column=0, sticky="nsew")
        self.orphan_empty = EmptyState(body, "🕵️", "ابحث عن بقايا التطبيقات",
                                       "نقارن ملفات ~/Library بالتطبيقات المثبتة لنجد ما تبقى من "
                                       "تطبيقات لم تعد موجودة.")
        self.orphan_empty.grid(row=0, column=0, sticky="nsew")
        foot = ctk.CTkFrame(v, fg_color="transparent")
        foot.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        self.orphan_summary = ctk.CTkLabel(foot, text="", font=T.font(13), text_color=T.MUTED)
        self.orphan_summary.pack(side="left")
        self.orphan_delete = GradientButton(foot, "🗑  حذف المحدد", self.delete_orphans, width=210,
                                            height=48, colors=T.GRADIENT_DANGER)
        self.orphan_delete.pack(side="right")
        self._update_orphan_footer()

    def _switch(self, value):
        (self.orphans_view if value == "بقايا تطبيقات محذوفة" else self.apps_view).tkraise()

    def show_orphans(self, items: List[FileItem]):
        by_app = defaultdict(list)
        for i in items:
            by_app[i.note].append(i)
        groups = [Group(k, f"📦  {k}", v) for k, v in by_app.items()]
        groups.sort(key=lambda g: sum(i.size for i in g.items), reverse=True)
        self.orphan_tree.set_groups(groups)
        if items:
            self.orphan_empty.lower()
        else:
            self.orphan_empty.set("لا توجد بقايا 🎉", "لم نجد ملفات لتطبيقات محذوفة.")
            self.orphan_empty.lift()

    def on_smart_result(self, result):
        if not self.busy:
            self.show_orphans(result.orphans)

    def scan_orphans(self):
        self.orphan_btn.configure_button(enabled=False)
        self.orphan_progress.grid()
        self.orphan_progress.start("جارٍ البحث...")
        self.start_job(apps_core.find_orphans)

    def on_progress(self, fraction, text):
        self.orphan_progress.update_progress(fraction, text)

    def on_finished(self, result, job):
        self.orphan_btn.configure_button(enabled=True)
        self.orphan_progress.finish(self.summary_text(job, f"وُجد {len(result or []):,} عنصر"),
                                    complete=not job.cancelled)
        if result is not None:
            self.show_orphans(result)

    def _update_orphan_footer(self):
        size = self.orphan_tree.checked_size()
        self.orphan_summary.configure(text=f"الإجمالي {human_size(self.orphan_tree.total_size())}"
                                           + (f"  •  المحدد: {human_size(size)}" if size else ""))
        self.orphan_delete.configure_button(enabled=size > 0)

    def delete_orphans(self):
        self.app.delete_items(self.orphan_tree.checked_items(),
                              lambda d, f: self.orphan_tree.remove_paths({i.path for i in d}))

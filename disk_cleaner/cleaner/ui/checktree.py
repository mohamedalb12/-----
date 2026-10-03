"""
checktree.py — جدول نتائج بمجموعات قابلة للطيّ ومربعات تحديد.

يُستخدم في كل صفحات البرنامج: مجموعة (مثل «الكاش» أو «فيديو») وتحتها العناصر.
- النقر على مربع التحديد يحدد/يلغي العنصر، وعلى المجموعة يحدد كل عناصرها.
- العناصر تُحمَّل عند فتح المجموعة فقط (سريع حتى مع عشرات آلاف الملفات).
- نقر مزدوج = فتح، مسافة = معاينة سريعة، زر يمين = قائمة الإجراءات.
"""

from __future__ import annotations

import sys
import tkinter as tk
from dataclasses import dataclass, field
from tkinter import ttk
from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple

import customtkinter as ctk

from ..core.models import FileItem, human_size, relative_age, short_path
from . import theme as T

IS_MAC = sys.platform == "darwin"
MAX_CHILDREN = 2000


@dataclass
class Group:
    key: str
    title: str
    items: List[FileItem]
    checked: bool = False
    subtitle: str = ""
    keep: Set[str] = field(default_factory=set)   # عناصر لا تُحدَّد عند تحديد المجموعة


def _check_images(size: int = 18):
    """صور مربعات التحديد الثلاث (مرسومة بـ Pillow بحواف ناعمة)."""
    from PIL import Image, ImageDraw, ImageTk

    s = 4
    S = size * s
    accent = T.resolve(T.ACCENT)
    border = T.resolve(T.FAINT)

    def base(fill, outline):
        img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([s, s, S - s, S - s], radius=5 * s, fill=fill, outline=outline,
                            width=int(1.6 * s))
        return img, d

    off, _ = base(None, border)
    on, d = base(accent, accent)
    d.line([(S * .28, S * .52), (S * .44, S * .68), (S * .74, S * .34)], fill="white",
           width=int(2.2 * s), joint="curve")
    mixed, d2 = base(accent, accent)
    d2.line([(S * .3, S * .5), (S * .7, S * .5)], fill="white", width=int(2.2 * s))
    return {k: ImageTk.PhotoImage(v.resize((size, size), Image.LANCZOS))
            for k, v in (("off", off), ("on", on), ("mixed", mixed))}


DEFAULT_COLUMNS = (("size", "الحجم", 110, "e"), ("used", "آخر استخدام", 130, "w"),
                   ("path", "المكان", 420, "w"))


class CheckTree(ctk.CTkFrame):
    def __init__(self, master, columns: Sequence[Tuple[str, str, int, str]] = DEFAULT_COLUMNS,
                 on_change: Optional[Callable[[], None]] = None,
                 on_select: Optional[Callable[[Optional[FileItem]], None]] = None,
                 actions=None, name_title: str = "الاسم"):
        super().__init__(master, fg_color=T.CARD, corner_radius=16, border_width=1,
                         border_color=T.BORDER)
        self.on_change = on_change
        self.on_select = on_select
        self.actions = actions          # كائن فيه open/reveal/quick_look/delete
        self.columns = columns
        self.groups: Dict[str, Group] = {}
        self.group_order: List[str] = []
        self.checked: Set[str] = set()
        self.item_rows: Dict[str, FileItem] = {}     # iid → FileItem
        self.loaded: Set[str] = set()
        self.sort_col, self.sort_rev = "size", True

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        cols = [c[0] for c in columns]
        self.tree = ttk.Treeview(self, columns=cols, style="Pro.Treeview", selectmode="extended")
        self.tree.heading("#0", text=name_title, anchor="w", command=lambda: self._sort("name"))
        self.tree.column("#0", width=300, minwidth=180, stretch=True)
        for key, title, width, anchor in columns:
            self.tree.heading(key, text=title, anchor=anchor, command=lambda k=key: self._sort(k))
            self.tree.column(key, width=width, minwidth=60, anchor=anchor, stretch=key == "path")
        self.tree.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=8)
        sb = ctk.CTkScrollbar(self, command=self.tree.yview)
        sb.grid(row=0, column=1, sticky="ns", pady=8, padx=(0, 4))
        self.tree.configure(yscrollcommand=sb.set)

        self.images = _check_images()
        self._mode_cb = lambda _m: self.after_idle(self._refresh_images)
        T.AppearanceModeTracker.add(self._mode_cb, self)
        self.tree.tag_configure("group", font=T.tk_font(13 if IS_MAC else 10, "bold"))
        self.tree.tag_configure("keep", foreground=T.resolve(T.MUTED))

        self.tree.bind("<Button-1>", self._on_click, add=True)
        self.tree.bind("<<TreeviewOpen>>", self._on_open)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Double-1>", self._on_double)
        self.tree.bind("<Return>", lambda _e: self._act("open"))
        self.tree.bind("<space>", lambda _e: (self._act("quick_look"), "break")[1])
        for seq in (("<Button-2>", "<Control-Button-1>") if IS_MAC else ("<Button-3>",)):
            self.tree.bind(seq, self._on_menu)
        self.menu = tk.Menu(self, tearoff=0)
        self.menu.add_command(label="فتح", command=lambda: self._act("open"))
        self.menu.add_command(label="معاينة سريعة (مسافة)", command=lambda: self._act("quick_look"))
        self.menu.add_command(label="إظهار في Finder" if IS_MAC else "فتح في المجلد",
                              command=lambda: self._act("reveal"))
        self.menu.add_command(label="نسخ المسار", command=self._copy_path)
        self.menu.add_separator()
        self.menu.add_command(label="تحديد", command=lambda: self._check_selection(True))
        self.menu.add_command(label="إلغاء التحديد", command=lambda: self._check_selection(False))

    def destroy(self):
        T.AppearanceModeTracker.remove(self._mode_cb)
        super().destroy()

    # ------------------------------------------------------------ البيانات
    def set_groups(self, groups: List[Group], expand: bool = False):
        self.tree.delete(*self.tree.get_children())
        self.groups = {g.key: g for g in groups if g.items}
        self.group_order = [g.key for g in groups if g.items]
        self.checked = set()
        self.item_rows = {}
        self.loaded = set()
        for g in self.groups.values():
            if g.checked:
                self.checked.update(i.path for i in g.items if i.path not in g.keep)
        for key in self.group_order:
            self._insert_group(key)
        if expand or len(self.group_order) == 1:
            for key in self.group_order[:200]:
                self.tree.item(key, open=True)
                self._load_children(key)
        self._changed()

    def _insert_group(self, key: str, index="end"):
        g = self.groups[key]
        self.tree.insert("", index, iid=key, text="  " + g.title, image=self.images[self._group_state(g)],
                         values=self._group_values(g), tags=("group",))
        self.tree.insert(key, "end", iid=key + "::placeholder", text="…")

    def _group_values(self, g: Group):
        size = sum(i.size for i in g.items)
        vals = []
        for col, *_ in self.columns:
            if col == "size":
                vals.append(human_size(size))
            elif col == "used":
                vals.append(g.subtitle or f"{len(g.items):,} عنصر")
            elif col == "path":
                vals.append("")
            else:
                vals.append(g.subtitle if col == "info" else "")
        return vals

    def _item_values(self, item: FileItem):
        vals = []
        for col, *_ in self.columns:
            if col == "size":
                vals.append(human_size(item.size))
            elif col == "used":
                vals.append(relative_age(item.last_used))
            elif col == "path":
                vals.append(short_path(item.path))
            elif col == "info":
                vals.append(item.note)
            else:
                vals.append("")
        return vals

    def _sorted_items(self, g: Group) -> List[FileItem]:
        key = {
            "size": lambda i: i.size,
            "used": lambda i: i.last_used,
            "name": lambda i: i.name.lower(),
            "path": lambda i: i.path.lower(),
            "info": lambda i: i.note,
        }.get(self.sort_col, lambda i: i.size)
        return sorted(g.items, key=key, reverse=self.sort_rev)

    def _load_children(self, key: str):
        if key in self.loaded:
            return
        self.loaded.add(key)
        g = self.groups[key]
        self.tree.delete(*self.tree.get_children(key))
        items = self._sorted_items(g)
        for n, item in enumerate(items[:MAX_CHILDREN]):
            iid = f"{key}::{n}"
            self.item_rows[iid] = item
            state = "on" if item.path in self.checked else "off"
            tags = ("keep",) if item.path in g.keep else ()
            icon = "📁 " if item.is_dir else ""
            self.tree.insert(key, "end", iid=iid, text=f"  {icon}{item.name}", image=self.images[state],
                             values=self._item_values(item), tags=tags)
        if len(items) > MAX_CHILDREN:
            self.tree.insert(key, "end", iid=key + "::more",
                             text=f"  … و {len(items) - MAX_CHILDREN:,} عنصر آخر (تتبع تحديد المجموعة)")

    def _group_state(self, g: Group) -> str:
        n = sum(1 for i in g.items if i.path in self.checked)
        return "off" if n == 0 else "on" if n == len(g.items) else "mixed"

    # ------------------------------------------------------------ التحديد
    def _on_click(self, event):
        if self.tree.identify_element(event.x, event.y) != "image":
            return None
        iid = self.tree.identify_row(event.y)
        if not iid:
            return None
        self._toggle(iid)
        return "break"

    def _toggle(self, iid: str, value: Optional[bool] = None):
        if iid in self.groups:
            g = self.groups[iid]
            if value is None:
                value = self._group_state(g) != "on"
            for item in g.items:
                if value and item.path not in g.keep:
                    self.checked.add(item.path)
                elif not value:
                    self.checked.discard(item.path)
            if value and all(i.path in g.keep for i in g.items):
                self.checked.update(i.path for i in g.items)
            self._refresh_group(iid)
        elif iid in self.item_rows:
            item = self.item_rows[iid]
            if value is None:
                value = item.path not in self.checked
            (self.checked.add if value else self.checked.discard)(item.path)
            self.tree.item(iid, image=self.images["on" if value else "off"])
            self.tree.item(self.tree.parent(iid),
                           image=self.images[self._group_state(self.groups[self.tree.parent(iid)])])
        self._changed()

    def _refresh_group(self, key: str):
        g = self.groups[key]
        self.tree.item(key, image=self.images[self._group_state(g)], values=self._group_values(g))
        for iid in self.tree.get_children(key):
            item = self.item_rows.get(iid)
            if item:
                self.tree.item(iid, image=self.images["on" if item.path in self.checked else "off"])

    def _check_selection(self, value: bool):
        for iid in self.tree.selection():
            self._toggle(iid, value)

    def set_all(self, value: bool):
        for key in self.group_order:
            self._toggle(key, value)

    def set_group_checked(self, key: str, value: bool):
        if key in self.groups:
            self._toggle(key, value)

    def checked_items(self) -> List[FileItem]:
        result, seen = [], set()
        for key in self.group_order:
            for item in self.groups[key].items:
                if item.path in self.checked and item.path not in seen:
                    seen.add(item.path)
                    result.append(item)
        return result

    def checked_size(self) -> int:
        return sum(i.size for i in self.checked_items())

    def total_size(self) -> int:
        return sum(i.size for g in self.groups.values() for i in g.items)

    def remove_paths(self, paths: Set[str]):
        """إزالة العناصر المحذوفة من الجدول."""
        for key in list(self.group_order):
            g = self.groups[key]
            before = len(g.items)
            g.items = [i for i in g.items if i.path not in paths]
            if len(g.items) == before:
                continue
            index = self.tree.index(key)
            was_open = self.tree.item(key, "open")
            self.tree.delete(key)
            self.loaded.discard(key)
            self.item_rows = {k: v for k, v in self.item_rows.items() if not k.startswith(key + "::")}
            if g.items:
                self._insert_group(key, index)
                if was_open:
                    self.tree.item(key, open=True)
                    self._load_children(key)
            else:
                del self.groups[key]
                self.group_order.remove(key)
        self.checked -= paths
        self._changed()

    def _changed(self):
        if self.on_change:
            self.on_change()

    # ------------------------------------------------------------ أحداث أخرى
    def _on_open(self, _event):
        iid = self.tree.focus()
        if iid in self.groups:
            self._load_children(iid)

    def selected_item(self) -> Optional[FileItem]:
        for iid in self.tree.selection():
            if iid in self.item_rows:
                return self.item_rows[iid]
        return None

    def _on_select(self, _event):
        if self.on_select:
            self.on_select(self.selected_item())

    def _on_double(self, event):
        iid = self.tree.identify_row(event.y)
        if iid in self.item_rows and self.tree.identify_element(event.x, event.y) != "image":
            self._act("open")

    def _on_menu(self, event):
        iid = self.tree.identify_row(event.y)
        if not iid:
            return
        if iid not in self.tree.selection():
            self.tree.selection_set(iid)
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    def _act(self, name: str):
        item = self.selected_item()
        if item and self.actions:
            getattr(self.actions, name)(item.path)

    def _copy_path(self):
        items = [self.item_rows[i] for i in self.tree.selection() if i in self.item_rows]
        if items:
            self.clipboard_clear()
            self.clipboard_append("\n".join(i.path for i in items))

    def _sort(self, col: str):
        if self.sort_col == col:
            self.sort_rev = not self.sort_rev
        else:
            self.sort_col, self.sort_rev = col, col in ("size", "used")
        for key in list(self.loaded):
            self.loaded.discard(key)
            self.item_rows = {k: v for k, v in self.item_rows.items() if not k.startswith(key + "::")}
            self._load_children(key)

    def _refresh_images(self):
        if not self.winfo_exists():
            return
        self.images = _check_images()
        self.tree.tag_configure("keep", foreground=T.resolve(T.MUTED))
        for key in self.group_order:
            self._refresh_group(key)

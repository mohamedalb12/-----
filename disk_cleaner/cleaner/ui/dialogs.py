"""dialogs.py — نافذة تأكيد الحذف."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox
from typing import List, Optional

import customtkinter as ctk

from ..core.actions import is_in_trash
from ..core.models import FileItem, human_size, short_path
from . import theme as T
from .widgets import GradientButton


class ConfirmDeleteDialog(ctk.CTkToplevel):
    """
    تأكيد قبل أي حذف. الافتراضي: النقل إلى سلة المحذوفات (قابل للاسترجاع).
    النتيجة في self.result: None (إلغاء) أو "trash" أو "permanent".
    """

    def __init__(self, master, items: List[FileItem], default_mode: str = "trash",
                 title: str = "تأكيد الحذف", action_text: str = "حذف", warning: str = ""):
        super().__init__(master)
        self.title(title)
        self.resizable(False, False)
        self.configure(fg_color=T.BG)
        self.result: Optional[str] = None
        self.mode = tk.StringVar(value=default_mode)

        total = sum(i.size for i in items)
        in_trash = sum(1 for i in items if is_in_trash(i.path))

        card = ctk.CTkFrame(self, fg_color=T.CARD, corner_radius=20, border_width=1,
                            border_color=T.BORDER)
        card.pack(padx=18, pady=18, fill="both", expand=True)

        ctk.CTkLabel(card, text="🗑", font=T.font(44)).pack(pady=(20, 0))
        head = items[0].name if len(items) == 1 else f"{len(items):,} عنصر"
        ctk.CTkLabel(card, text=f"{action_text} {head}؟", font=T.font(18, "bold"),
                     wraplength=440).pack(padx=24, pady=(6, 2))
        ctk.CTkLabel(card, text=f"سيتم تحرير {human_size(total)}", font=T.font(14),
                     text_color=T.ACCENT).pack()

        preview = "\n".join(short_path(i.path) for i in items[:7])
        if len(items) > 7:
            preview += f"\n… و {len(items) - 7:,} عنصر آخر"
        box = ctk.CTkTextbox(card, width=470, height=min(130, 22 * min(len(items), 7) + 22),
                             font=T.font(11), wrap="none")
        box.insert("1.0", preview)
        box.configure(state="disabled")
        box.pack(padx=24, pady=(12, 6))

        notes = []
        if warning:
            notes.append(warning)
        if in_trash:
            notes.append(f"• {in_trash:,} عنصر موجود في سلة المحذوفات بالفعل وسيُحذف نهائياً.")
        if notes:
            ctk.CTkLabel(card, text="\n".join(notes), font=T.font(12), text_color=T.WARNING,
                         justify="right", wraplength=460).pack(padx=24, pady=(4, 0))

        opts = ctk.CTkFrame(card, fg_color="transparent")
        opts.pack(padx=24, pady=10, fill="x")
        ctk.CTkRadioButton(opts, text="نقل إلى سلة المحذوفات (يمكن استرجاعه) — موصى به",
                           variable=self.mode, value="trash", font=T.font(13)).pack(anchor="w", pady=4)
        ctk.CTkRadioButton(opts, text="حذف نهائي فوري (لا يمكن التراجع)", variable=self.mode,
                           value="permanent", font=T.font(13), text_color=T.DANGER).pack(anchor="w", pady=4)

        buttons = ctk.CTkFrame(card, fg_color="transparent")
        buttons.pack(pady=(6, 22))
        ctk.CTkButton(buttons, text="إلغاء", width=130, height=44, corner_radius=22,
                      fg_color=T.TRACK, hover_color=T.HOVER, text_color=T.TEXT,
                      font=T.font(14, "bold"), command=self._cancel).pack(side="left", padx=8)
        GradientButton(buttons, text=f"{action_text} الآن", width=170, height=44,
                       colors=T.GRADIENT_DANGER, font_size=14, command=self._confirm).pack(side="left", padx=8)

        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.bind("<Escape>", lambda _e: self._cancel())
        self.bind("<Return>", lambda _e: self._confirm())
        self.transient(master)
        self.update_idletasks()
        x = master.winfo_rootx() + (master.winfo_width() - self.winfo_reqwidth()) // 2
        y = master.winfo_rooty() + (master.winfo_height() - self.winfo_reqheight()) // 3
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        self.after(60, self._grab)

    def _grab(self):
        try:
            self.lift()
            self.grab_set()
            self.focus_force()
        except tk.TclError:
            pass

    def _confirm(self):
        if self.mode.get() == "permanent" and not messagebox.askyesno(
                "تأكيد أخير", "الحذف النهائي لا يمكن التراجع عنه.\nهل أنت متأكد تماماً؟",
                icon="warning", parent=self):
            return
        self.result = self.mode.get()
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()


def confirm_delete(master, items: List[FileItem], default_mode: str = "trash", **kw) -> Optional[str]:
    dialog = ConfirmDeleteDialog(master, items, default_mode, **kw)
    master.wait_window(dialog)
    return dialog.result

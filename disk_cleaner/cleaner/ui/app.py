"""
app.py — النافذة الرئيسية: الشريط الجانبي، التنقل بين الصفحات، وتشغيل المهام في الخلفية.
"""

from __future__ import annotations

import queue
import sys
import traceback
from tkinter import messagebox
from typing import Callable, Dict, List, Optional

import customtkinter as ctk

from .. import APP_NAME, APP_NAME_AR, __version__
from ..core import actions
from ..core.jobs import Job
from ..core.models import FileItem, human_size
from ..core.settings import Settings
from ..resources import asset_path
from . import theme as T
from .dialogs import confirm_delete
from .widgets import show_toast

IS_MAC = sys.platform == "darwin"
POLL_MS = 60


class FileActions:
    """فتح / معاينة / إظهار في Finder مع رسائل خطأ واضحة."""

    def __init__(self, root):
        self.root = root

    def _safe(self, fn: Callable, path: str):
        try:
            fn(path)
        except actions.FileActionError as exc:
            messagebox.showerror("تعذّر تنفيذ العملية", str(exc), parent=self.root)
        except OSError as exc:
            messagebox.showerror("تعذّر تنفيذ العملية", str(exc), parent=self.root)

    def open(self, path: str):
        self._safe(actions.open_file, path)

    def reveal(self, path: str):
        self._safe(actions.reveal_in_folder, path)

    def quick_look(self, path: str):
        self._safe(actions.quick_look, path)


class _DeleteListener:
    def __init__(self, app: "App", on_done: Optional[Callable]):
        self.app = app
        self.on_done = on_done

    def on_job_event(self, job, kind, payload):
        if kind != "finished":
            return
        result, error = payload
        deleted, failed = result if result else ([], [])
        self.app.after_delete(deleted, failed, error)
        if self.on_done:
            self.on_done(deleted, failed)


class App(ctk.CTk):
    def __init__(self):
        T.setup_theme()
        self.settings = Settings.load()
        ctk.set_appearance_mode(self.settings.appearance)
        super().__init__()
        self.title(APP_NAME_AR)
        self.geometry("1340x860")
        self.minsize(1120, 720)

        self.queue: "queue.Queue" = queue.Queue()
        self.jobs: set = set()
        self.files = FileActions(self)
        self.smart_result = None
        self.pages: Dict[str, ctk.CTkFrame] = {}
        self.nav_buttons: Dict[str, ctk.CTkButton] = {}
        self.current: Optional[str] = None

        self._set_icon()
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_sidebar()
        self.content = ctk.CTkFrame(self, fg_color="transparent")
        self.content.grid(row=0, column=1, sticky="nsew", padx=28, pady=(22, 18))
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)

        T.apply_tree_style(self)
        T.on_appearance_change(lambda: T.apply_tree_style(self), self)
        self.show_page("dashboard")
        self.refresh_disk()
        self.after(POLL_MS, self._poll)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------ الواجهة
    def _set_icon(self):
        try:
            from PIL import Image, ImageTk
            img = Image.open(asset_path("icon.png"))
            self._icon_photo = ImageTk.PhotoImage(img.resize((256, 256)))
            self.iconphoto(True, self._icon_photo)
            self.logo = ctk.CTkImage(img, size=(38, 38))
        except Exception:
            self.logo = None

    def _build_sidebar(self):
        from .pages import PAGES

        side = ctk.CTkFrame(self, width=258, corner_radius=0, fg_color=T.SIDEBAR)
        side.grid(row=0, column=0, sticky="nsew")
        side.grid_propagate(False)
        side.grid_columnconfigure(0, weight=1)

        brand = ctk.CTkFrame(side, fg_color="transparent")
        brand.grid(row=0, column=0, sticky="ew", padx=18, pady=(26, 22))
        if self.logo:
            ctk.CTkLabel(brand, text="", image=self.logo).pack(side="left", padx=(0, 10))
        names = ctk.CTkFrame(brand, fg_color="transparent")
        names.pack(side="left")
        ctk.CTkLabel(names, text=APP_NAME, font=T.font(16, "bold"), anchor="w").pack(anchor="w")
        ctk.CTkLabel(names, text=f"{APP_NAME_AR} • v{__version__}", font=T.font(11),
                     text_color=T.MUTED, anchor="w").pack(anchor="w")

        for row, (key, icon, label, _cls) in enumerate(PAGES, start=1):
            btn = ctk.CTkButton(side, text=f"{icon}   {label}", anchor="w", height=42,
                                corner_radius=12, font=T.font(14), fg_color="transparent",
                                hover_color=T.HOVER, text_color=T.TEXT,
                                command=lambda k=key: self.show_page(k))
            btn.grid(row=row, column=0, sticky="ew", padx=14, pady=2)
            self.nav_buttons[key] = btn

        side.grid_rowconfigure(len(PAGES) + 1, weight=1)

        disk = ctk.CTkFrame(side, fg_color=T.CARD, corner_radius=16, border_width=1,
                            border_color=T.BORDER)
        disk.grid(row=len(PAGES) + 2, column=0, sticky="ew", padx=14, pady=(0, 18))
        ctk.CTkLabel(disk, text="💽  قرص التشغيل", font=T.font(13, "bold"), anchor="w").pack(
            fill="x", padx=14, pady=(12, 4))
        self.disk_bar = ctk.CTkProgressBar(disk, height=8)
        self.disk_bar.pack(fill="x", padx=14)
        self.disk_label = ctk.CTkLabel(disk, text="", font=T.font(12), text_color=T.MUTED, anchor="w")
        self.disk_label.pack(fill="x", padx=14, pady=(4, 12))

    def show_page(self, key: str):
        from .pages import PAGES

        if key not in self.pages:
            cls = next(c for k, _i, _l, c in PAGES if k == key)
            page = cls(self.content, self)
            page.grid(row=0, column=0, sticky="nsew")
            self.pages[key] = page
            if self.smart_result is not None:
                page.on_smart_result(self.smart_result)
        for k, btn in self.nav_buttons.items():
            active = k == key
            btn.configure(fg_color=T.ACCENT if active else "transparent",
                          text_color="#ffffff" if active else T.TEXT,
                          hover_color=T.ACCENT_HOVER if active else T.HOVER,
                          font=T.font(14, "bold" if active else "normal"))
        self.pages[key].tkraise()
        self.current = key
        self.pages[key].on_show()

    def refresh_disk(self):
        try:
            total, used, free = actions.disk_usage("/")
        except OSError:
            return
        self.disk_bar.set(used / total if total else 0)
        self.disk_label.configure(text=f"{human_size(free)} متاح من {human_size(total)}")
        dash = self.pages.get("dashboard")
        if dash:
            dash.update_disk(total, used, free)

    def publish_smart_result(self, result):
        self.smart_result = result
        for page in self.pages.values():
            page.on_smart_result(result)

    # ------------------------------------------------------------ المهام
    def run_job(self, listener, fn, *args, **kwargs) -> Job:
        job = Job(self.queue, listener, fn, *args, **kwargs)
        self.jobs.add(job)
        job.start()
        return job

    def _poll(self):
        try:
            for _ in range(400):
                job, kind, payload = self.queue.get_nowait()
                if kind == "finished":
                    self.jobs.discard(job)
                try:
                    job.listener.on_job_event(job, kind, payload)
                except Exception:
                    traceback.print_exc()
        except queue.Empty:
            pass
        self.after(POLL_MS, self._poll)

    # ------------------------------------------------------------ الحذف
    def delete_items(self, items: List[FileItem], on_done: Optional[Callable] = None,
                     **dialog_kw) -> bool:
        """تأكيد ثم حذف في الخلفية. on_done(deleted, failed) بعد الانتهاء."""
        if not items:
            return False
        mode = confirm_delete(self, items, self.settings.delete_mode, **dialog_kw)
        if not mode:
            return False
        show_toast(self, f"جارٍ حذف {len(items):,} عنصر...", "⏳", 2000)
        self.run_job(_DeleteListener(self, on_done), actions.delete_items, items, mode)
        return True

    def after_delete(self, deleted: List[FileItem], failed, error: Optional[str]):
        freed = sum(i.size for i in deleted)
        if deleted:
            self.settings.total_cleaned += freed
            self.settings.clean_count += 1
            self.settings.save()
            show_toast(self, f"رائع! تم تحرير {human_size(freed)}", "✨",
                       color=("#16a34a", "#15803d"))
        self.refresh_disk()
        if error:
            messagebox.showerror("حدث خطأ", error.strip().splitlines()[-1], parent=self)
        if failed:
            details = "\n\n".join(f"• {item.name}:\n{err}" for item, err in failed[:6])
            if len(failed) > 6:
                details += f"\n\n… و {len(failed) - 6} أخطاء أخرى"
            messagebox.showwarning("بعض العناصر لم تُحذف",
                                   f"تعذّر حذف {len(failed):,} عنصر:\n\n{details}", parent=self)

    # ------------------------------------------------------------ الإغلاق
    def _on_close(self):
        for job in list(self.jobs):
            job.cancel()
        self.settings.save()
        self.destroy()


def run():
    app = App()
    if IS_MAC:  # إحضار النافذة للأمام عند التشغيل
        app.after(200, lambda: (app.lift(), app.focus_force()))
    app.mainloop()

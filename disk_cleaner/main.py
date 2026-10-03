"""
main.py
=======
منظّف القرص (Disk Cleaner) — الواجهة الرسومية.

التشغيل:
    python3 main.py

بنية البرنامج:
    main.py          ← الواجهة الرسومية (CustomTkinter + جدول ttk.Treeview)
    scanner.py       ← منطق الفحص في خيط خلفي
    file_actions.py  ← فتح / إظهار في Finder / سلة المحذوفات / حذف نهائي

ملاحظة عن الخيوط (Threads):
    مكتبة Tkinter لا تسمح بتعديل الواجهة إلا من الخيط الرئيسي. لذلك ترسل الخيوط
    الخلفية رسائلها إلى طابور (queue.Queue)، والواجهة تقرأ هذا الطابور كل 100ms
    عبر self.after(...). هكذا تبقى الواجهة سريعة الاستجابة دائماً.
"""

from __future__ import annotations

import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Dict, List, Optional

try:
    import customtkinter as ctk
except ImportError:  # رسالة واضحة إذا لم تُثبَّت المكتبة
    sys.exit("مكتبة customtkinter غير مثبتة. نفّذ:  pip3 install -r requirements.txt")

import file_actions
from scanner import Category, FileItem, Scanner, ScanOptions, ScanStats, human_size

# --------------------------------------------------------------------------- #
#  إعدادات عامة
# --------------------------------------------------------------------------- #

APP_TITLE = "منظّف القرص — Disk Cleaner"
IS_MAC = sys.platform == "darwin"

# قيم شريط التمرير للحد الأدنى للحجم (بالميجابايت) — متدرجة لتسهيل الاختيار
SIZE_STEPS_MB = [10, 25, 50, 100, 250, 500, 1024, 2048, 5120, 10240]
DEFAULT_STEP = SIZE_STEPS_MB.index(100)

# أقصى عدد صفوف يُعرض في الجدول (الأكبر حجماً أولاً) للحفاظ على سرعة الواجهة
MAX_ROWS = 10_000
POLL_MS = 100

FILTER_ALL = "الكل"
FILTER_LARGE_ONLY = "الملفات الكبيرة فقط"
FILTER_JUNK_ONLY = "كل الملفات المهملة"
FILTER_VALUES = [FILTER_ALL, FILTER_LARGE_ONLY, FILTER_JUNK_ONLY] + [
    c.value for c in Category if c is not Category.LARGE
]

COLUMNS = ("name", "size", "type", "category", "path")
COLUMN_TITLES = {
    "name": "اسم الملف",
    "size": "الحجم",
    "type": "النوع",
    "category": "التصنيف",
    "path": "المسار الكامل",
}
COLUMN_WIDTHS = {"name": 220, "size": 100, "type": 150, "category": 120, "path": 480}


def mb_label(mb: int) -> str:
    return f"{mb / 1024:g} GB" if mb >= 1024 else f"{mb} MB"


# --------------------------------------------------------------------------- #
#  نافذة تأكيد الحذف
# --------------------------------------------------------------------------- #


class DeleteDialog(ctk.CTkToplevel):
    """
    نافذة تأكيد قبل الحذف. الخيار الافتراضي هو النقل إلى سلة المحذوفات (آمن).
    بعد الإغلاق: self.result = None (إلغاء) أو "trash" أو "permanent".
    """

    def __init__(self, master, items: List[FileItem]):
        super().__init__(master)
        self.title("تأكيد الحذف")
        self.resizable(False, False)
        self.result: Optional[str] = None
        self.mode = tk.StringVar(value="trash")

        total = sum(i.size for i in items)
        if len(items) == 1:
            header = f"هل تريد حذف الملف التالي؟\n\n{items[0].name}\n({human_size(total)})"
        else:
            header = f"هل تريد حذف {len(items)} ملفات؟\nالحجم الإجمالي: {human_size(total)}"

        ctk.CTkLabel(self, text="⚠️", font=ctk.CTkFont(size=40)).pack(pady=(18, 0))
        ctk.CTkLabel(self, text=header, font=ctk.CTkFont(size=14), wraplength=420,
                     justify="center").pack(padx=24, pady=(6, 10))

        # عرض أول بضعة مسارات حتى يتأكد المستخدم مما سيُحذف
        preview = "\n".join(i.path for i in items[:6])
        if len(items) > 6:
            preview += f"\n... و {len(items) - 6} ملفات أخرى"
        box = ctk.CTkTextbox(self, width=460, height=110, font=ctk.CTkFont(size=11))
        box.insert("1.0", preview)
        box.configure(state="disabled")
        box.pack(padx=24, pady=4)

        options = ctk.CTkFrame(self, fg_color="transparent")
        options.pack(padx=24, pady=10, fill="x")
        ctk.CTkRadioButton(options, text="نقل إلى سلة المحذوفات (يمكن استرجاعه) — موصى به",
                           variable=self.mode, value="trash").pack(anchor="w", pady=4)
        ctk.CTkRadioButton(options, text="حذف نهائي (لا يمكن التراجع عنه!)",
                           variable=self.mode, value="permanent",
                           text_color=("#b3261e", "#ff6b6b")).pack(anchor="w", pady=4)

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.pack(pady=(4, 18))
        ctk.CTkButton(buttons, text="إلغاء", width=120, fg_color="gray50",
                      hover_color="gray40", command=self._cancel).pack(side="left", padx=8)
        ctk.CTkButton(buttons, text="تأكيد الحذف", width=140, fg_color="#c0392b",
                      hover_color="#992d22", command=self._confirm).pack(side="left", padx=8)

        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.bind("<Escape>", lambda _e: self._cancel())

        # جعل النافذة مشروطة (Modal) وفي منتصف النافذة الرئيسية
        self.transient(master)
        self.update_idletasks()
        x = master.winfo_rootx() + (master.winfo_width() - self.winfo_width()) // 2
        y = master.winfo_rooty() + (master.winfo_height() - self.winfo_height()) // 3
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        self.after(50, self._grab)

    def _grab(self):
        try:
            self.grab_set()
            self.focus_force()
        except tk.TclError:
            pass

    def _confirm(self):
        if self.mode.get() == "permanent":
            ok = messagebox.askyesno(
                "تحذير أخير",
                "سيتم حذف الملفات نهائياً ولن تتمكن من استرجاعها.\nهل أنت متأكد تماماً؟",
                icon="warning", parent=self,
            )
            if not ok:
                return
        self.result = self.mode.get()
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()


# --------------------------------------------------------------------------- #
#  النافذة الرئيسية
# --------------------------------------------------------------------------- #


class DiskCleanerApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1280x780")
        self.minsize(1000, 620)

        # حالة البرنامج
        self.ui_queue: "queue.Queue[tuple]" = queue.Queue()
        self.scanner: Optional[Scanner] = None
        self.all_items: List[FileItem] = []          # كل النتائج
        self.row_items: Dict[str, FileItem] = {}     # معرّف الصف في الجدول → الملف
        self.sort_column = "size"
        self.sort_reverse = True
        self.busy_deleting = False
        self.indeterminate = False

        self._build_sidebar()
        self._build_main_area()
        self._apply_treeview_style()

        self.after(POLL_MS, self._process_queue)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ================================================================ بناء الواجهة
    def _build_sidebar(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        side = ctk.CTkFrame(self, width=300, corner_radius=0)
        side.grid(row=0, column=0, sticky="nsew")
        side.grid_propagate(False)
        side.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(side, text="🧹 منظّف القرص",
                     font=ctk.CTkFont(size=22, weight="bold")).grid(row=0, column=0, pady=(22, 2))
        ctk.CTkLabel(side, text="اكتشف الملفات الكبيرة والمهملة",
                     text_color="gray60").grid(row=1, column=0, pady=(0, 16))

        # ---------- مسار الفحص
        ctk.CTkLabel(side, text="مسار الفحص:", anchor="w",
                     font=ctk.CTkFont(weight="bold")).grid(row=2, column=0, sticky="ew", padx=18)
        self.path_var = tk.StringVar(value=os.path.expanduser("~"))
        ctk.CTkEntry(side, textvariable=self.path_var).grid(row=3, column=0, sticky="ew",
                                                             padx=18, pady=(4, 6))
        ctk.CTkButton(side, text="📁  اختيار مجلد...", command=self._choose_folder).grid(
            row=4, column=0, sticky="ew", padx=18, pady=3)

        quick = ctk.CTkFrame(side, fg_color="transparent")
        quick.grid(row=5, column=0, sticky="ew", padx=18, pady=3)
        quick.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkButton(quick, text="🏠 مجلد المستخدم", fg_color="gray35", hover_color="gray25",
                      command=lambda: self.path_var.set(os.path.expanduser("~"))).grid(
            row=0, column=0, sticky="ew", padx=(0, 3))
        ctk.CTkButton(quick, text="💽 القرص كامل", fg_color="gray35", hover_color="gray25",
                      command=lambda: self.path_var.set(os.path.abspath(os.sep))).grid(
            row=0, column=1, sticky="ew", padx=(3, 0))

        # ---------- خيارات الفحص
        ctk.CTkLabel(side, text="ماذا تريد أن تبحث عنه؟", anchor="w",
                     font=ctk.CTkFont(weight="bold")).grid(row=6, column=0, sticky="ew",
                                                          padx=18, pady=(20, 4))
        self.large_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(side, text="الملفات الكبيرة", variable=self.large_var,
                        command=self._toggle_slider).grid(row=7, column=0, sticky="w",
                                                          padx=18, pady=4)

        self.threshold_label = ctk.CTkLabel(side, anchor="w")
        self.threshold_label.grid(row=8, column=0, sticky="ew", padx=40)
        self.size_slider = ctk.CTkSlider(side, from_=0, to=len(SIZE_STEPS_MB) - 1,
                                         number_of_steps=len(SIZE_STEPS_MB) - 1,
                                         command=self._on_slider)
        self.size_slider.set(DEFAULT_STEP)
        self.size_slider.grid(row=9, column=0, sticky="ew", padx=(40, 18), pady=(0, 8))
        self._on_slider(DEFAULT_STEP)

        self.junk_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(side, text="الملفات المؤقتة والمهملة", variable=self.junk_var).grid(
            row=10, column=0, sticky="w", padx=18, pady=4)
        ctk.CTkLabel(side, text="كاش، .tmp، .log، سلة المحذوفات،\nبقايا البرامج، .DS_Store ...",
                     text_color="gray60", justify="left", anchor="w").grid(
            row=11, column=0, sticky="ew", padx=46)

        # ---------- أزرار الفحص
        self.scan_button = ctk.CTkButton(side, text="▶  بدء الفحص", height=44,
                                         font=ctk.CTkFont(size=16, weight="bold"),
                                         command=self._start_scan)
        self.scan_button.grid(row=12, column=0, sticky="ew", padx=18, pady=(26, 6))
        self.stop_button = ctk.CTkButton(side, text="■  إيقاف", height=36, state="disabled",
                                         fg_color="#c0392b", hover_color="#992d22",
                                         command=self._stop_scan)
        self.stop_button.grid(row=13, column=0, sticky="ew", padx=18, pady=4)

        side.grid_rowconfigure(14, weight=1)

        # ---------- المظهر
        ctk.CTkLabel(side, text="المظهر:", anchor="w").grid(row=15, column=0, sticky="ew", padx=18)
        appearance = ctk.CTkOptionMenu(side, values=["System", "Dark", "Light"],
                                       command=self._change_appearance)
        appearance.set("System")
        appearance.grid(row=16, column=0, sticky="ew", padx=18, pady=(4, 18))

    def _build_main_area(self):
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.grid(row=0, column=1, sticky="nsew", padx=14, pady=14)
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(1, weight=1)

        # ---------- شريط التصفية والبحث
        top = ctk.CTkFrame(main, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        top.grid_columnconfigure(3, weight=1)
        ctk.CTkLabel(top, text="عرض:").grid(row=0, column=0, padx=(0, 6))
        self.filter_menu = ctk.CTkOptionMenu(top, values=FILTER_VALUES, width=190,
                                             command=lambda _v: self._refresh_table())
        self.filter_menu.set(FILTER_ALL)
        self.filter_menu.grid(row=0, column=1)
        ctk.CTkLabel(top, text="بحث:").grid(row=0, column=2, padx=(16, 6))
        self.search_entry = ctk.CTkEntry(top, placeholder_text="جزء من اسم الملف أو المسار...")
        self.search_entry.grid(row=0, column=3, sticky="ew")
        self.search_entry.bind("<KeyRelease>", lambda _e: self._schedule_refresh())

        # ---------- الجدول
        table_frame = ctk.CTkFrame(main)
        table_frame.grid(row=1, column=0, sticky="nsew")
        table_frame.grid_columnconfigure(0, weight=1)
        table_frame.grid_rowconfigure(0, weight=1)

        self.tree = ttk.Treeview(table_frame, columns=COLUMNS, show="headings",
                                 selectmode="extended", style="Cleaner.Treeview")
        for col in COLUMNS:
            self.tree.heading(col, text=COLUMN_TITLES[col],
                              command=lambda c=col: self._sort_by(c))
            anchor = "e" if col == "size" else "w"
            self.tree.column(col, width=COLUMN_WIDTHS[col], anchor=anchor,
                             stretch=(col == "path"))
        self.tree.grid(row=0, column=0, sticky="nsew", padx=(4, 0), pady=4)

        vsb = ctk.CTkScrollbar(table_frame, orientation="vertical", command=self.tree.yview)
        hsb = ctk.CTkScrollbar(table_frame, orientation="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        # ألوان مميزة للصفوف حسب التصنيف
        self.tree.tag_configure("junk", foreground="#e67e22")
        self.tree.tag_configure("large", foreground="#3b8ed0")

        # التفاعل: نقر مزدوج يفتح الملف، Enter يفتح، Delete يحذف، زر يمين قائمة
        self.tree.bind("<Double-1>", self._on_double_click)
        self.tree.bind("<Return>", lambda _e: self._open_selected())
        self.tree.bind("<Delete>", lambda _e: self._delete_selected())
        self.tree.bind("<BackSpace>", lambda _e: self._delete_selected())
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._update_action_buttons())
        right_click = ("<Button-2>", "<Control-Button-1>") if IS_MAC else ("<Button-3>",)
        for seq in right_click:
            self.tree.bind(seq, self._show_context_menu)

        self.context_menu = tk.Menu(self, tearoff=0)
        self.context_menu.add_command(label="فتح الملف", command=self._open_selected)
        self.context_menu.add_command(label="إظهار في Finder" if IS_MAC else "فتح في المجلد",
                                      command=self._reveal_selected)
        self.context_menu.add_command(label="نسخ المسار", command=self._copy_path)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="حذف...", command=self._delete_selected)

        # ---------- أزرار الإجراءات
        actions = ctk.CTkFrame(main, fg_color="transparent")
        actions.grid(row=2, column=0, sticky="ew", pady=(8, 4))
        actions.grid_columnconfigure(3, weight=1)
        self.open_btn = ctk.CTkButton(actions, text="📄 فتح الملف", width=130,
                                      command=self._open_selected)
        self.open_btn.grid(row=0, column=0, padx=(0, 6))
        self.reveal_btn = ctk.CTkButton(
            actions, text="📂 إظهار في Finder" if IS_MAC else "📂 فتح في المجلد", width=160,
            command=self._reveal_selected)
        self.reveal_btn.grid(row=0, column=1, padx=6)
        self.delete_btn = ctk.CTkButton(actions, text="🗑 حذف المحدد", width=140,
                                        fg_color="#c0392b", hover_color="#992d22",
                                        command=self._delete_selected)
        self.delete_btn.grid(row=0, column=2, padx=6)
        self.summary_label = ctk.CTkLabel(actions, text="", anchor="e")
        self.summary_label.grid(row=0, column=3, sticky="ew")

        # ---------- شريط التقدم والحالة
        progress_row = ctk.CTkFrame(main, fg_color="transparent")
        progress_row.grid(row=3, column=0, sticky="ew", pady=(6, 0))
        progress_row.grid_columnconfigure(0, weight=1)
        self.progress = ctk.CTkProgressBar(progress_row, height=14)
        self.progress.set(0)
        self.progress.grid(row=0, column=0, sticky="ew")
        self.percent_label = ctk.CTkLabel(progress_row, text="0%", width=60,
                                          font=ctk.CTkFont(weight="bold"))
        self.percent_label.grid(row=0, column=1, padx=(8, 0))
        self.status_label = ctk.CTkLabel(main, text="جاهز. اختر مساراً ثم اضغط «بدء الفحص».",
                                         anchor="w", text_color="gray60")
        self.status_label.grid(row=4, column=0, sticky="ew")

        self._update_action_buttons()

    # ================================================================ المظهر
    def _apply_treeview_style(self):
        """تنسيق جدول ttk ليتناسب مع الوضع الداكن/الفاتح في CustomTkinter."""
        dark = ctk.get_appearance_mode() == "Dark"
        bg = "#2b2b2b" if dark else "#ffffff"
        fg = "#e8e8e8" if dark else "#1a1a1a"
        head_bg = "#1f1f1f" if dark else "#e4e4e4"
        sel = "#1f6aa5"
        style = ttk.Style(self)
        style.theme_use("clam")
        row_font = ("SF Pro Text", 13) if IS_MAC else ("Segoe UI", 10)
        style.configure("Cleaner.Treeview", background=bg, fieldbackground=bg, foreground=fg,
                        rowheight=28, borderwidth=0, font=row_font)
        style.map("Cleaner.Treeview", background=[("selected", sel)],
                  foreground=[("selected", "#ffffff")])
        style.configure("Cleaner.Treeview.Heading", background=head_bg, foreground=fg,
                        relief="flat", font=(row_font[0], row_font[1], "bold"), padding=6)
        style.map("Cleaner.Treeview.Heading", background=[("active", sel)])

    def _change_appearance(self, mode: str):
        ctk.set_appearance_mode(mode)
        self.after(50, self._apply_treeview_style)

    # ================================================================ عناصر التحكم
    def _on_slider(self, value):
        mb = SIZE_STEPS_MB[int(round(float(value)))]
        self.threshold_label.configure(text=f"الحد الأدنى للحجم:  ≥ {mb_label(mb)}")

    def _threshold_bytes(self) -> int:
        return SIZE_STEPS_MB[int(round(self.size_slider.get()))] * 1024 * 1024

    def _toggle_slider(self):
        self.size_slider.configure(state="normal" if self.large_var.get() else "disabled")

    def _choose_folder(self):
        folder = filedialog.askdirectory(initialdir=self.path_var.get() or os.path.expanduser("~"),
                                         title="اختر المجلد أو القرص المراد فحصه")
        if folder:
            self.path_var.set(folder)

    # ================================================================ الفحص
    def _start_scan(self):
        if self.scanner and self.scanner.is_alive():
            return
        root = os.path.expanduser(self.path_var.get().strip())
        if not os.path.isdir(root):
            messagebox.showerror("مسار غير صالح", f"المجلد غير موجود:\n{root}")
            return
        if not (self.large_var.get() or self.junk_var.get()):
            messagebox.showwarning("لا يوجد ما يُفحص", "اختر نوعاً واحداً على الأقل من الملفات.")
            return

        # تفريغ النتائج السابقة
        self.all_items.clear()
        self._clear_table()
        self._update_summary()

        options = ScanOptions(root=root, find_large=self.large_var.get(),
                              large_threshold_bytes=self._threshold_bytes(),
                              find_junk=self.junk_var.get())
        self.scanner = Scanner(options, self.ui_queue)
        self.scanner.start()

        self.scan_button.configure(state="disabled", text="⏳  جارٍ الفحص...")
        self.stop_button.configure(state="normal")
        self.progress.configure(mode="indeterminate")
        self.progress.start()
        self.indeterminate = True
        self.percent_label.configure(text="...")

    def _stop_scan(self):
        if self.scanner and self.scanner.is_alive():
            self.scanner.cancel()
            self.status_label.configure(text="جارٍ إيقاف الفحص...")
            self.stop_button.configure(state="disabled")

    def _process_queue(self):
        """قراءة رسائل الخيوط الخلفية وتحديث الواجهة (يعمل في الخيط الرئيسي)."""
        new_items: List[FileItem] = []
        try:
            for _ in range(500):  # حد أقصى لكل دورة حتى لا تتأخر الواجهة
                msg = self.ui_queue.get_nowait()
                kind = msg[0]
                if kind == "status":
                    self.status_label.configure(text=msg[1])
                elif kind == "counting":
                    self.status_label.configure(text=f"جارٍ حصر الملفات... ({msg[1]:,} ملف)")
                elif kind == "progress":
                    self._set_progress(*msg[1:])
                elif kind == "items":
                    new_items.extend(msg[1])
                elif kind == "finished":
                    if new_items:
                        self._add_items(new_items)
                        new_items = []
                    self._scan_finished(msg[1])
                elif kind == "deleted":
                    self._deletion_finished(msg[1], msg[2])
        except queue.Empty:
            pass
        if new_items:
            self._add_items(new_items)
        self.after(POLL_MS, self._process_queue)

    def _stop_indeterminate(self):
        if self.indeterminate:
            self.progress.stop()
            self.progress.configure(mode="determinate")
            self.indeterminate = False

    def _set_progress(self, fraction: float, done: int, total: int):
        self._stop_indeterminate()
        self.progress.set(fraction)
        self.percent_label.configure(text=f"{fraction * 100:.0f}%")
        self.status_label.configure(text=f"جارٍ الفحص... {done:,} من {total:,} ملف")

    def _scan_finished(self, stats: ScanStats):
        self._stop_indeterminate()
        if not stats.cancelled:
            self.progress.set(1.0)
            self.percent_label.configure(text="100%")

        self.scan_button.configure(state="normal", text="▶  بدء الفحص")
        self.stop_button.configure(state="disabled")
        self._refresh_table()

        state = "تم إيقاف الفحص" if stats.cancelled else "اكتمل الفحص"
        text = (f"{state} خلال {stats.elapsed:.1f} ثانية — تم فحص {stats.files_scanned:,} ملف "
                f"في {stats.dirs_scanned:,} مجلد")
        if stats.errors:
            text += f" — تم تخطي {stats.errors:,} عنصر بسبب الصلاحيات أو أخطاء القراءة"
        self.status_label.configure(text=text)

    # ================================================================ الجدول
    def _matches_filter(self, item: FileItem) -> bool:
        flt = self.filter_menu.get()
        if flt == FILTER_LARGE_ONLY and not item.is_large:
            return False
        if flt == FILTER_JUNK_ONLY and not item.category.is_junk:
            return False
        if flt not in (FILTER_ALL, FILTER_LARGE_ONLY, FILTER_JUNK_ONLY) and item.category.value != flt:
            return False
        query = self.search_entry.get().strip().lower()
        return not query or query in item.path.lower()

    def _insert_row(self, item: FileItem):
        category = item.category.value
        if item.is_large and item.category.is_junk:
            category += " (كبير)"
        tag = "junk" if item.category.is_junk else "large"
        iid = self.tree.insert("", "end", values=(item.name, human_size(item.size),
                                                  item.file_type, category, item.path),
                               tags=(tag,))
        self.row_items[iid] = item

    def _add_items(self, items: List[FileItem]):
        """إضافة نتائج جديدة أثناء الفحص (بدون إعادة رسم الجدول بالكامل)."""
        self.all_items.extend(items)
        for item in items:
            if len(self.row_items) >= MAX_ROWS:
                break
            if self._matches_filter(item):
                self._insert_row(item)
        self._update_summary()

    def _clear_table(self):
        self.tree.delete(*self.tree.get_children())
        self.row_items.clear()

    def _sort_key(self, item: FileItem):
        col = self.sort_column
        if col == "size":
            return item.size
        if col == "category":
            return item.category.value
        if col == "type":
            return item.file_type
        if col == "name":
            return item.name.lower()
        return item.path.lower()

    def _refresh_table(self):
        """إعادة بناء الجدول بالكامل وفق التصفية والترتيب الحاليين."""
        self._refresh_job = None
        self._clear_table()
        visible = [i for i in self.all_items if self._matches_filter(i)]
        # نعرض الأكبر حجماً أولاً عند تجاوز الحد الأقصى، ثم نرتب حسب اختيار المستخدم
        if len(visible) > MAX_ROWS:
            visible.sort(key=lambda i: i.size, reverse=True)
            visible = visible[:MAX_ROWS]
        visible.sort(key=self._sort_key, reverse=self.sort_reverse)
        for item in visible:
            self._insert_row(item)

        for col in COLUMNS:  # سهم يوضح عمود الترتيب
            arrow = (" ▼" if self.sort_reverse else " ▲") if col == self.sort_column else ""
            self.tree.heading(col, text=COLUMN_TITLES[col] + arrow)
        self._update_summary()

    _refresh_job = None

    def _schedule_refresh(self):
        """تأخير بسيط عند الكتابة في خانة البحث لتجنّب إعادة الرسم مع كل حرف."""
        if self._refresh_job:
            self.after_cancel(self._refresh_job)
        self._refresh_job = self.after(250, self._refresh_table)

    def _sort_by(self, column: str):
        if self.sort_column == column:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_column = column
            self.sort_reverse = column == "size"
        self._refresh_table()

    def _update_summary(self):
        total_size = sum(i.size for i in self.all_items)
        junk_size = sum(i.size for i in self.all_items if i.category.is_junk)
        text = (f"النتائج: {len(self.all_items):,} ملف  |  الإجمالي: {human_size(total_size)}"
                f"  |  المهملات: {human_size(junk_size)}")
        if len(self.row_items) >= MAX_ROWS:
            text += f"  |  يُعرض أكبر {MAX_ROWS:,} ملف"
        self.summary_label.configure(text=text)
        self._update_action_buttons()

    # ================================================================ الإجراءات
    def _selected_items(self) -> List[FileItem]:
        return [self.row_items[iid] for iid in self.tree.selection() if iid in self.row_items]

    def _update_action_buttons(self):
        count = len(self.tree.selection())
        single = "normal" if count == 1 else "disabled"
        self.open_btn.configure(state=single)
        self.reveal_btn.configure(state=single)
        self.delete_btn.configure(state="normal" if count and not self.busy_deleting else "disabled")

    def _on_double_click(self, event):
        # نتجاهل النقر المزدوج على رأس العمود
        if self.tree.identify_region(event.x, event.y) == "cell":
            self._open_selected()

    def _show_context_menu(self, event):
        row = self.tree.identify_row(event.y)
        if not row:
            return
        if row not in self.tree.selection():
            self.tree.selection_set(row)
        try:
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()

    def _run_action(self, action, item: FileItem):
        try:
            action(item.path)
        except file_actions.FileActionError as exc:
            messagebox.showerror("تعذّر تنفيذ العملية", str(exc))
        except OSError as exc:
            messagebox.showerror("تعذّر تنفيذ العملية", f"{exc}")

    def _open_selected(self):
        items = self._selected_items()
        if items:
            self._run_action(file_actions.open_file, items[0])

    def _reveal_selected(self):
        items = self._selected_items()
        if items:
            self._run_action(file_actions.reveal_in_folder, items[0])

    def _copy_path(self):
        items = self._selected_items()
        if items:
            self.clipboard_clear()
            self.clipboard_append("\n".join(i.path for i in items))

    def _delete_selected(self):
        items = self._selected_items()
        if not items or self.busy_deleting:
            return
        dialog = DeleteDialog(self, items)
        self.wait_window(dialog)
        if not dialog.result:
            return

        action = (file_actions.move_to_trash if dialog.result == "trash"
                  else file_actions.delete_permanently)
        self.busy_deleting = True
        self._update_action_buttons()
        self.status_label.configure(text=f"جارٍ حذف {len(items)} ملف...")

        def worker():
            deleted, failed = [], []
            for item in items:
                try:
                    action(item.path)
                    deleted.append(item)
                except Exception as exc:  # نتابع مع باقي الملفات حتى لو فشل أحدها
                    failed.append((item, str(exc)))
            self.ui_queue.put(("deleted", deleted, failed))

        threading.Thread(target=worker, daemon=True).start()

    def _deletion_finished(self, deleted: List[FileItem], failed: list):
        self.busy_deleting = False
        removed_paths = {i.path for i in deleted}
        self.all_items = [i for i in self.all_items if i.path not in removed_paths]
        for iid, item in list(self.row_items.items()):
            if item.path in removed_paths:
                self.tree.delete(iid)
                del self.row_items[iid]
        self._update_summary()

        freed = human_size(sum(i.size for i in deleted))
        self.status_label.configure(text=f"تم حذف {len(deleted)} ملف وتحرير {freed}.")
        if failed:
            details = "\n\n".join(f"{item.name}:\n{err}" for item, err in failed[:8])
            if len(failed) > 8:
                details += f"\n\n... و {len(failed) - 8} أخطاء أخرى"
            messagebox.showwarning("بعض الملفات لم تُحذف",
                                   f"تعذّر حذف {len(failed)} ملف:\n\n{details}")

    # ================================================================ الإغلاق
    def _on_close(self):
        if self.scanner and self.scanner.is_alive():
            self.scanner.cancel()
        self.destroy()


def main():
    ctk.set_appearance_mode("System")
    ctk.set_default_color_theme("blue")
    app = DiskCleanerApp()
    app.mainloop()


if __name__ == "__main__":
    main()

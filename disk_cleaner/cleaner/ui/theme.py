"""
theme.py — نظام التصميم: الألوان، الخطوط، وتنسيق عناصر CustomTkinter و ttk.

كل لون معرّف كزوج (الوضع الفاتح، الوضع الداكن) ويتبدّل تلقائياً مع مظهر النظام.
"""

from __future__ import annotations

import sys
from typing import Callable, Tuple, Union

import customtkinter as ctk

try:
    from customtkinter import AppearanceModeTracker
except ImportError:  # pragma: no cover
    from customtkinter.windows.widgets.appearance_mode import AppearanceModeTracker

IS_MAC = sys.platform == "darwin"
Color = Union[str, Tuple[str, str]]

# ---------------------------------------------------------------- لوحة الألوان
BG = ("#f3f4fa", "#0d0f17")
SIDEBAR = ("#e9ebf6", "#121522")
CARD = ("#ffffff", "#181c2b")
CARD_ALT = ("#f6f7fc", "#1e2335")
HOVER = ("#eceefa", "#232842")
BORDER = ("#e0e3f0", "#252a40")
TEXT = ("#141726", "#eef0fa")
MUTED = ("#6b7088", "#8b91aa")
FAINT = ("#a3a8bd", "#565c78")
TRACK = ("#e6e8f3", "#252a3d")
SEGMENT = ("#9a9fbb", "#252a3d")
SEGMENT_HOVER = ("#878cab", "#2e3450")

ACCENT = ("#6c5ce7", "#7c6cff")
ACCENT_HOVER = ("#5b4bd8", "#6a5af0")
ACCENT_SOFT = ("#ece9ff", "#2a2550")
PINK = "#ff5ca8"
GRADIENT = ("#7c6cff", "#ff5ca8")
GRADIENT_DANGER = ("#ff6b6b", "#ff3d7f")
GRADIENT_SUCCESS = ("#22c55e", "#14b8a6")

SUCCESS = "#22c55e"
WARNING = "#f59e0b"
DANGER = ("#e5484d", "#ff5c63")
DANGER_HOVER = ("#c93a3f", "#e5484d")
INFO = "#3b82f6"


def is_dark() -> bool:
    return ctk.get_appearance_mode() == "Dark"


def resolve(color: Color) -> str:
    """تحويل اللون الثنائي إلى اللون المناسب للوضع الحالي."""
    if isinstance(color, (tuple, list)):
        return color[1] if is_dark() else color[0]
    return color


def on_appearance_change(callback: Callable[[], None], widget=None) -> None:
    AppearanceModeTracker.add(lambda _mode: callback(), widget)


# ---------------------------------------------------------------- الخطوط
FONT_FAMILY = None


def font(size: int = 13, weight: str = "normal") -> ctk.CTkFont:
    return ctk.CTkFont(family=FONT_FAMILY, size=size, weight=weight)


def tk_font(size: int = 13, weight: str = "normal") -> tuple:
    family = FONT_FAMILY or ctk.ThemeManager.theme["CTkFont"]["family"]
    return (family, size, weight) if weight != "normal" else (family, size)


# ---------------------------------------------------------------- تهيئة CTk
def setup_theme() -> None:
    """تعديل الثيم الافتراضي لـ CustomTkinter ليطابق هوية البرنامج."""
    global FONT_FAMILY
    ctk.set_default_color_theme("blue")
    t = ctk.ThemeManager.theme
    FONT_FAMILY = t["CTkFont"]["family"]
    if not IS_MAC and sys.platform.startswith("win"):
        FONT_FAMILY = "Segoe UI"

    def L(c):  # tuple → list كما يتوقعها CTk
        return list(c) if isinstance(c, tuple) else [c, c]

    t["CTk"]["fg_color"] = L(BG)
    t["CTkToplevel"]["fg_color"] = L(BG)
    t["CTkFrame"].update(fg_color=L(CARD), top_fg_color=L(CARD_ALT), border_color=L(BORDER),
                         corner_radius=14)
    t["CTkButton"].update(fg_color=L(ACCENT), hover_color=L(ACCENT_HOVER), corner_radius=10,
                          text_color=["#ffffff", "#ffffff"], border_color=L(BORDER))
    t["CTkLabel"]["text_color"] = L(TEXT)
    t["CTkEntry"].update(fg_color=L(CARD_ALT), border_color=L(BORDER), text_color=L(TEXT),
                         placeholder_text_color=L(FAINT), corner_radius=10, border_width=1)
    for name in ("CTkCheckBox", "CTkRadioButton"):
        t[name].update(fg_color=L(ACCENT), hover_color=L(ACCENT_HOVER), border_color=L(FAINT),
                       text_color=L(TEXT))
    t["CTkSwitch"].update(progress_color=L(ACCENT), fg_color=L(TRACK), text_color=L(TEXT))
    t["CTkProgressBar"].update(fg_color=L(TRACK), progress_color=L(ACCENT), corner_radius=8)
    t["CTkSlider"].update(fg_color=L(TRACK), progress_color=L(ACCENT), button_color=L(ACCENT),
                          button_hover_color=L(ACCENT_HOVER))
    t["CTkOptionMenu"].update(fg_color=L(CARD_ALT), button_color=L(CARD_ALT),
                              button_hover_color=L(HOVER), text_color=L(TEXT), corner_radius=10)
    t["CTkComboBox"].update(fg_color=L(CARD_ALT), border_color=L(BORDER), button_color=L(BORDER),
                            text_color=L(TEXT))
    t["CTkSegmentedButton"].update(fg_color=L(SEGMENT), selected_color=L(ACCENT),
                                   selected_hover_color=L(ACCENT_HOVER), unselected_color=L(SEGMENT),
                                   unselected_hover_color=L(SEGMENT_HOVER),
                                   text_color=["#ffffff", "#ffffff"], corner_radius=10)
    t["CTkScrollbar"].update(button_color=L(TRACK), button_hover_color=L(FAINT))
    t["CTkScrollableFrame"]["label_fg_color"] = L(CARD_ALT)
    t["CTkTextbox"].update(fg_color=L(CARD_ALT), border_color=L(BORDER), text_color=L(TEXT))
    t["DropdownMenu"].update(fg_color=L(CARD), hover_color=L(HOVER), text_color=L(TEXT))


# ---------------------------------------------------------------- جداول ttk
def apply_tree_style(root) -> None:
    from tkinter import ttk
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass
    bg, fg = resolve(CARD), resolve(TEXT)
    style.configure("Pro.Treeview", background=bg, fieldbackground=bg, foreground=fg,
                    rowheight=32, borderwidth=0, relief="flat", font=tk_font(13 if IS_MAC else 10))
    style.map("Pro.Treeview",
              background=[("selected", resolve(ACCENT_SOFT))],
              foreground=[("selected", resolve(TEXT))])
    style.configure("Pro.Treeview.Heading", background=resolve(CARD), foreground=resolve(MUTED),
                    relief="flat", borderwidth=0, padding=(8, 8),
                    font=tk_font(12 if IS_MAC else 9, "bold"))
    style.map("Pro.Treeview.Heading", background=[("active", resolve(HOVER))])
    style.layout("Pro.Treeview", [("Pro.Treeview.treearea", {"sticky": "nswe"})])
    # جداول أطول صفاً (للتطبيقات مع الأيقونات)
    style.configure("Apps.Treeview", background=bg, fieldbackground=bg, foreground=fg,
                    rowheight=44, borderwidth=0, font=tk_font(13 if IS_MAC else 10))
    style.map("Apps.Treeview", background=[("selected", resolve(ACCENT_SOFT))],
              foreground=[("selected", resolve(TEXT))])
    style.layout("Apps.Treeview", [("Apps.Treeview.treearea", {"sticky": "nswe"})])
    style.configure("Apps.Treeview.Heading", background=resolve(CARD), foreground=resolve(MUTED),
                    relief="flat", borderwidth=0, padding=(8, 8),
                    font=tk_font(12 if IS_MAC else 9, "bold"))

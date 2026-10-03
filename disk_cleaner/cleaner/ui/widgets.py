"""
widgets.py — عناصر واجهة مخصصة بتصميم عصري:

GradientButton  زر بتدرّج لوني وحواف دائرية مع تأثير المرور
Donut           رسم دائري متحرك (لمساحة القرص وتوزيع الأنواع)
Card / StatCard بطاقات المعلومات
ProgressPanel   شريط تقدّم + نسبة مئوية + حالة + زر إيقاف
BarList         قائمة أعمدة سريعة على Canvas (لخريطة المساحة)
EmptyState      حالة فارغة لطيفة قبل الفحص
show_toast      إشعار عائم مؤقت
"""

from __future__ import annotations

import sys
import tkinter as tk
import tkinter.font as tkfont
from typing import Callable, List, Optional, Sequence, Tuple

import customtkinter as ctk

from . import theme as T

IS_MAC = sys.platform == "darwin"
CURSOR = "pointinghand" if IS_MAC else "hand2"


def effective_bg(widget) -> str:
    """لون الخلفية الفعلي خلف عنصر (لإخفاء حواف عناصر Canvas)."""
    w = widget
    while w is not None:
        if hasattr(w, "_fg_color"):
            try:
                color = w.cget("fg_color")
            except Exception:
                color = "transparent"
            if color != "transparent":
                return T.resolve(tuple(color) if isinstance(color, list) else color)
        elif isinstance(w, (tk.Canvas, tk.Frame)):
            try:
                return w.cget("bg")
            except Exception:
                pass
        w = getattr(w, "master", None)
    return T.resolve(T.BG)


def fit_font(text: str, max_width: int, size: int, weight: str = "normal", min_size: int = 9):
    """أكبر خط يجعل النص يتسع في العرض المتاح."""
    while size > min_size:
        f = tkfont.Font(font=T.tk_font(size, weight))
        if f.measure(text) <= max_width:
            break
        size -= 1
    return T.tk_font(size, weight)


class _ThemedCanvas(tk.Canvas):
    """Canvas يتبع الوضع الداكن/الفاتح تلقائياً."""

    def __init__(self, master, **kw):
        super().__init__(master, highlightthickness=0, bd=0, **kw)
        self._mode_cb = lambda _m: self.after_idle(self._on_mode)
        T.AppearanceModeTracker.add(self._mode_cb, self)
        self.after_idle(lambda: self.configure(bg=effective_bg(self.master)))

    def _on_mode(self):
        if self.winfo_exists():
            self.configure(bg=effective_bg(self.master))
            self.redraw()

    def redraw(self):
        pass

    def destroy(self):
        T.AppearanceModeTracker.remove(self._mode_cb)
        super().destroy()


# --------------------------------------------------------------------------- #
#  زر بتدرّج لوني
# --------------------------------------------------------------------------- #


def _gradient_image(w: int, h: int, colors: Sequence[str], radius: int, factor: float = 1.0):
    """صورة مستطيل دائري الحواف بتدرّج أفقي (مرسومة بدقة 3x ثم مصغّرة لحواف ناعمة)."""
    from PIL import Image, ImageDraw, ImageTk

    s = 3
    W, H = max(w * s, 2), max(h * s, 2)

    def rgb(c):
        c = c.lstrip("#")
        return tuple(min(255, int(int(c[i:i + 2], 16) * factor)) for i in (0, 2, 4))

    c1, c2 = rgb(colors[0]), rgb(colors[-1])
    line = Image.new("RGB", (W, 1))
    for x in range(W):
        t = x / (W - 1)
        line.putpixel((x, 0), tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3)))
    img = line.resize((W, H))
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, W - 1, H - 1], radius=radius * s, fill=255)
    img.putalpha(mask)
    return ImageTk.PhotoImage(img.resize((w, h), Image.LANCZOS))


class GradientButton(_ThemedCanvas):
    def __init__(self, master, text: str, command: Optional[Callable] = None, width: int = 220,
                 height: int = 50, colors: Sequence[str] = T.GRADIENT, font_size: int = 16,
                 radius: Optional[int] = None):
        super().__init__(master, width=width, height=height, cursor=CURSOR)
        self.text = text
        self.command = command
        self.colors = colors
        self.radius = radius if radius is not None else height // 2
        self.font_size = font_size
        self.enabled = True
        self._state = "normal"
        self._images = {}
        self._bw, self._bh = width, height
        self.bind("<Enter>", lambda _e: self._set("hover"))
        self.bind("<Leave>", lambda _e: self._set("normal"))
        self.bind("<ButtonPress-1>", lambda _e: self._set("pressed"))
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<Configure>", self._on_resize)
        self.redraw()

    def _on_resize(self, event):
        if (event.width, event.height) != (self._bw, self._bh) and event.width > 4:
            self._bw, self._bh = event.width, event.height
            self._images.clear()
            self.redraw()

    def _image(self, key: str):
        if key not in self._images:
            if key == "disabled":
                colors, factor = ("#9aa0b5", "#7d8399") if not T.is_dark() else ("#3a3f55", "#2f3446"), 1.0
            else:
                colors = self.colors
                factor = {"normal": 1.0, "hover": 1.08, "pressed": 0.88}[key]
            self._images[key] = _gradient_image(self._bw, self._bh, colors, min(self.radius, self._bh // 2), factor)
        return self._images[key]

    def redraw(self):
        self.delete("all")
        key = self._state if self.enabled else "disabled"
        self.create_image(0, 0, image=self._image(key), anchor="nw")
        font = fit_font(self.text, self._bw - 28, self.font_size, "bold")
        self.create_text(self._bw // 2, self._bh // 2, text=self.text, fill="#ffffff", font=font)

    def _on_mode(self):
        self._images.pop("disabled", None)
        super()._on_mode()

    def _set(self, state: str):
        self._state = state
        if self.enabled:
            self.redraw()

    def _release(self, event):
        inside = 0 <= event.x <= self._bw and 0 <= event.y <= self._bh
        self._set("hover" if inside else "normal")
        if inside and self.enabled and self.command:
            self.command()

    def configure_button(self, text: Optional[str] = None, enabled: Optional[bool] = None,
                         colors: Optional[Sequence[str]] = None):
        if text is not None:
            self.text = text
        if enabled is not None:
            self.enabled = enabled
            self.configure(cursor=CURSOR if enabled else "")
        if colors is not None and colors != self.colors:
            self.colors = colors
            self._images.clear()
        self.redraw()


# --------------------------------------------------------------------------- #
#  رسم دائري (Donut)
# --------------------------------------------------------------------------- #


class Donut(_ThemedCanvas):
    def __init__(self, master, size: int = 200, thickness: int = 20):
        super().__init__(master, width=size, height=size)
        self.size = size
        self.thickness = thickness
        self.segments: List[Tuple[float, str]] = []
        self.title = ""
        self.subtitle = ""
        self._t = 1.0
        self._anim = None
        self.redraw()

    def set(self, segments: List[Tuple[float, str]], title: str = "", subtitle: str = "",
            animate: bool = True):
        self.segments = [(v, c) for v, c in segments if v > 0]
        self.title, self.subtitle = title, subtitle
        if self._anim:
            self.after_cancel(self._anim)
        self._t = 0.0 if animate else 1.0
        self._step()

    def _step(self):
        self.redraw()
        if self._t < 1.0:
            self._t = min(1.0, self._t + 0.07)
            self._anim = self.after(16, self._step)
        else:
            self._anim = None

    def redraw(self):
        self.delete("all")
        pad = self.thickness // 2 + 4
        box = (pad, pad, self.size - pad, self.size - pad)
        self.create_oval(*box, outline=T.resolve(T.TRACK), width=self.thickness)
        total = sum(v for v, _ in self.segments)
        if total > 0:
            ease = 1 - (1 - self._t) ** 3
            start = 90.0
            for value, color in self.segments:
                extent = -360.0 * value / total * ease
                if abs(extent) >= 359.9:
                    self.create_oval(*box, outline=color, width=self.thickness)
                elif abs(extent) > 0.3:
                    self.create_arc(*box, start=start, extent=extent, style="arc", outline=color,
                                    width=self.thickness)
                start += extent
        c = self.size / 2
        inner = self.size - 2 * self.thickness - 28
        self.create_text(c, c - 10, text=self.title, fill=T.resolve(T.TEXT),
                         font=fit_font(self.title, inner, max(14, self.size // 9), "bold"))
        self.create_text(c, c + self.size // 9, text=self.subtitle, fill=T.resolve(T.MUTED),
                         font=T.tk_font(max(10, self.size // 17)))


# --------------------------------------------------------------------------- #
#  بطاقات
# --------------------------------------------------------------------------- #


class Card(ctk.CTkFrame):
    def __init__(self, master, **kw):
        kw.setdefault("fg_color", T.CARD)
        kw.setdefault("corner_radius", 18)
        kw.setdefault("border_width", 1)
        kw.setdefault("border_color", T.BORDER)
        super().__init__(master, **kw)


class StatCard(Card):
    """بطاقة: أيقونة ملوّنة + عنوان + قيمة كبيرة + وصف + زر."""

    def __init__(self, master, icon: str, title: str, color: str, button_text: str = "",
                 command: Optional[Callable] = None):
        super().__init__(master)
        self.grid_columnconfigure(1, weight=1)
        bubble = ctk.CTkLabel(self, text=icon, width=46, height=46, corner_radius=14,
                              fg_color=color, font=T.font(22), text_color="#ffffff")
        bubble.grid(row=0, column=0, rowspan=2, padx=(16, 12), pady=(16, 6), sticky="n")
        ctk.CTkLabel(self, text=title, font=T.font(13), text_color=T.MUTED, anchor="w").grid(
            row=0, column=1, sticky="sw", pady=(16, 0), padx=(0, 16))
        self.value = ctk.CTkLabel(self, text="—", font=T.font(24, "bold"), anchor="w")
        self.value.grid(row=1, column=1, sticky="nw", padx=(0, 16))
        self.subtitle = ctk.CTkLabel(self, text="", font=T.font(12), text_color=T.MUTED, anchor="w",
                                     justify="left", wraplength=260)
        self.subtitle.grid(row=2, column=0, columnspan=2, sticky="ew", padx=16, pady=(2, 8))
        self.button = None
        if button_text:
            self.button = ctk.CTkButton(self, text=button_text, height=32, command=command,
                                        fg_color=T.ACCENT_SOFT, hover_color=T.HOVER,
                                        text_color=T.ACCENT, font=T.font(13, "bold"))
            self.button.grid(row=3, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 16))

    def set(self, value: str, subtitle: str = "", enabled: bool = True):
        self.value.configure(text=value)
        self.subtitle.configure(text=subtitle)
        if self.button:
            self.button.configure(state="normal" if enabled else "disabled")


class PageHeader(ctk.CTkFrame):
    def __init__(self, master, icon: str, title: str, subtitle: str):
        super().__init__(master, fg_color="transparent")
        self.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(self, text=icon, font=T.font(30)).grid(row=0, column=0, rowspan=2, padx=(0, 12))
        ctk.CTkLabel(self, text=title, font=T.font(26, "bold"), anchor="w").grid(
            row=0, column=1, sticky="sw")
        self.subtitle = ctk.CTkLabel(self, text=subtitle, font=T.font(13), text_color=T.MUTED,
                                     anchor="w")
        self.subtitle.grid(row=1, column=1, sticky="nw")
        # ارتفاع 1 حتى لا يأخذ الإطار الفارغ ارتفاعه الافتراضي (200px)
        self.actions = ctk.CTkFrame(self, fg_color="transparent", width=1, height=1)
        self.actions.grid(row=0, column=2, rowspan=2, sticky="e")


# --------------------------------------------------------------------------- #
#  شريط التقدّم
# --------------------------------------------------------------------------- #


class ProgressPanel(ctk.CTkFrame):
    def __init__(self, master, on_cancel: Optional[Callable] = None):
        super().__init__(master, fg_color="transparent")
        self.grid_columnconfigure(0, weight=1)
        self.bar = ctk.CTkProgressBar(self, height=10)
        self.bar.set(0)
        self.bar.grid(row=0, column=0, sticky="ew", pady=(4, 0))
        self.percent = ctk.CTkLabel(self, text="", width=52, font=T.font(13, "bold"),
                                    text_color=T.ACCENT)
        self.percent.grid(row=0, column=1, padx=(10, 0))
        self.cancel_btn = ctk.CTkButton(self, text="إيقاف", width=70, height=26, command=on_cancel,
                                        fg_color=T.TRACK, hover_color=T.HOVER, text_color=T.TEXT)
        if on_cancel:
            self.cancel_btn.grid(row=0, column=2, padx=(8, 0))
        self.status = ctk.CTkLabel(self, text="", font=T.font(12), text_color=T.MUTED, anchor="w")
        self.status.grid(row=1, column=0, columnspan=3, sticky="ew")
        self._indeterminate = False

    def start(self, text: str = "جارٍ التحضير..."):
        self.bar.configure(mode="indeterminate")
        self.bar.start()
        self._indeterminate = True
        self.percent.configure(text="")
        self.status.configure(text=text)
        self.cancel_btn.configure(state="normal")

    def update_progress(self, fraction: Optional[float], text: str = ""):
        if fraction is None:
            if not self._indeterminate:
                self.bar.configure(mode="indeterminate")
                self.bar.start()
                self._indeterminate = True
                self.percent.configure(text="")
        else:
            if self._indeterminate:
                self.bar.stop()
                self.bar.configure(mode="determinate")
                self._indeterminate = False
            self.bar.set(fraction)
            self.percent.configure(text=f"{fraction * 100:.0f}%")
        if text:
            self.status.configure(text=text)

    def finish(self, text: str = "", complete: bool = True):
        if self._indeterminate:
            self.bar.stop()
            self.bar.configure(mode="determinate")
            self._indeterminate = False
        if complete:
            self.bar.set(1.0)
            self.percent.configure(text="100%")
        self.status.configure(text=text)
        self.cancel_btn.configure(state="disabled")

    def reset(self, text: str = ""):
        self.finish(text, complete=False)
        self.bar.set(0)
        self.percent.configure(text="")


# --------------------------------------------------------------------------- #
#  حالة فارغة
# --------------------------------------------------------------------------- #


class EmptyState(ctk.CTkFrame):
    def __init__(self, master, icon: str, title: str, subtitle: str):
        super().__init__(master, fg_color="transparent")
        inner = ctk.CTkFrame(self, fg_color="transparent")
        inner.place(relx=0.5, rely=0.45, anchor="center")
        ctk.CTkLabel(inner, text=icon, font=T.font(64)).pack()
        self.title = ctk.CTkLabel(inner, text=title, font=T.font(20, "bold"))
        self.title.pack(pady=(8, 4))
        self.subtitle = ctk.CTkLabel(inner, text=subtitle, font=T.font(13), text_color=T.MUTED,
                                     wraplength=420, justify="center")
        self.subtitle.pack()

    def set(self, title: str, subtitle: str = ""):
        self.title.configure(text=title)
        self.subtitle.configure(text=subtitle)


# --------------------------------------------------------------------------- #
#  قائمة أعمدة (خريطة المساحة)
# --------------------------------------------------------------------------- #


class BarList(ctk.CTkFrame):
    """
    قائمة سريعة مرسومة على Canvas: أيقونة، اسم، عمود نسبي، حجم، نسبة.
    rows: [(icon, name, size, fraction, color, payload)]
    """

    ROW_H = 46

    def __init__(self, master, on_open: Callable, on_menu: Callable):
        super().__init__(master, fg_color="transparent")
        self.on_open = on_open
        self.on_menu = on_menu
        self.rows: List[tuple] = []
        self.hover = -1
        self.selected = -1
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.canvas = _ThemedCanvas(self)
        self.canvas.redraw = self.redraw
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scroll = ctk.CTkScrollbar(self, command=self.canvas.yview)
        self.scroll.grid(row=0, column=1, sticky="ns")
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.canvas.bind("<Configure>", lambda _e: self.redraw())
        self.canvas.bind("<Motion>", self._motion)
        self.canvas.bind("<Leave>", lambda _e: self._set_hover(-1))
        self.canvas.bind("<Button-1>", self._click)
        self.canvas.bind("<Double-1>", self._double)
        for seq in (("<Button-2>", "<Control-Button-1>") if IS_MAC else ("<Button-3>",)):
            self.canvas.bind(seq, self._menu)
        self.canvas.bind("<MouseWheel>", self._wheel)
        self.canvas.bind("<Button-4>", lambda _e: self.canvas.yview_scroll(-3, "units"))
        self.canvas.bind("<Button-5>", lambda _e: self.canvas.yview_scroll(3, "units"))
        self._font = tkfont.Font(font=T.tk_font(13))
        self._bold = tkfont.Font(font=T.tk_font(13, "bold"))

    def _wheel(self, event):
        delta = -event.delta if IS_MAC else -event.delta // 120
        self.canvas.yview_scroll(int(delta), "units")

    def set_rows(self, rows: List[tuple]):
        self.rows = rows
        self.hover = self.selected = -1
        self.canvas.yview_moveto(0)
        self.redraw()

    def _index(self, event) -> int:
        y = self.canvas.canvasy(event.y)
        i = int(y // self.ROW_H)
        return i if 0 <= i < len(self.rows) else -1

    def _set_hover(self, i: int):
        if i != self.hover:
            self.hover = i
            self.redraw()

    def _motion(self, event):
        self._set_hover(self._index(event))

    def _click(self, event):
        self.selected = self._index(event)
        self.redraw()

    def _double(self, event):
        i = self._index(event)
        if i >= 0:
            self.on_open(self.rows[i])

    def _menu(self, event):
        i = self._index(event)
        if i >= 0:
            self.selected = i
            self.redraw()
            self.on_menu(self.rows[i], event)

    def _fit(self, text: str, width: int, font) -> str:
        if font.measure(text) <= width:
            return text
        while text and font.measure(text + "…") > width:
            text = text[:-1]
        return text + "…"

    def redraw(self):
        c = self.canvas
        c.delete("all")
        width = max(c.winfo_width(), 300)
        h = self.ROW_H
        c.configure(scrollregion=(0, 0, width, max(len(self.rows) * h, 1)))
        name_w = int(width * 0.38)
        bar_x1 = 56 + name_w + 12
        bar_x2 = width - 170
        text, muted, track = T.resolve(T.TEXT), T.resolve(T.MUTED), T.resolve(T.TRACK)
        for i, (icon, name, size_text, fraction, color, _payload) in enumerate(self.rows):
            y0 = i * h
            yc = y0 + h / 2
            if i in (self.hover, self.selected):
                c.create_rectangle(6, y0 + 3, width - 6, y0 + h - 3, width=0,
                                   fill=T.resolve(T.ACCENT_SOFT if i == self.selected else T.HOVER))
            c.create_text(30, yc, text=icon, font=T.tk_font(18))
            c.create_text(56, yc, text=self._fit(name, name_w, self._bold), anchor="w", fill=text,
                          font=self._bold)
            if bar_x2 > bar_x1 + 20:
                c.create_line(bar_x1, yc, bar_x2, yc, width=8, capstyle="round", fill=track)
                fill_x = bar_x1 + (bar_x2 - bar_x1) * max(0.0, min(1.0, fraction))
                if fill_x > bar_x1 + 1:
                    c.create_line(bar_x1, yc, fill_x, yc, width=8, capstyle="round", fill=color)
            c.create_text(width - 80, yc, text=size_text, anchor="e", fill=text, font=self._font)
            c.create_text(width - 16, yc, text=f"{fraction * 100:.1f}%", anchor="e", fill=muted,
                          font=self._font)


# --------------------------------------------------------------------------- #
#  إشعار عائم
# --------------------------------------------------------------------------- #


def show_toast(root, text: str, icon: str = "✨", duration: int = 3500, color=None):
    toast = ctk.CTkFrame(root, fg_color=color or ("#1f2333", "#2a2f47"), corner_radius=14)
    ctk.CTkLabel(toast, text=f"{icon}  {text}", text_color="#ffffff", font=T.font(14, "bold")).pack(
        padx=20, pady=12)
    toast.place(relx=0.5, rely=0.97, anchor="s")
    toast.lift()
    root.after(duration, lambda: toast.winfo_exists() and toast.destroy())
    return toast

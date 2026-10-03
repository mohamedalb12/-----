"""
make_icon.py — يرسم أيقونة البرنامج (assets/icon.png و assets/icon.icns).

    python3 tools/make_icon.py
"""

import math
import os

from PIL import Image, ImageDraw, ImageFilter

SIZE = 1024
HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "..", "assets")


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def star(draw, cx, cy, r, fill):
    """نجمة لامعة رباعية."""
    pts = []
    for i in range(8):
        ang = math.pi / 4 * i - math.pi / 2
        rad = r if i % 2 == 0 else r * 0.28
        pts.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
    draw.polygon(pts, fill=fill)


def main():
    s = 2  # رسم بدقة مضاعفة ثم تصغير لحواف ناعمة
    S = SIZE * s
    c1, c2, c3 = (108, 92, 231), (171, 92, 246), (255, 92, 168)

    # تدرّج قطري بثلاثة ألوان
    grad = Image.new("RGB", (S, S))
    px = grad.load()
    for y in range(0, S, 2):
        for x in range(0, S, 2):
            t = (x + y) / (2 * S)
            col = lerp(c1, c2, t * 2) if t < 0.5 else lerp(c2, c3, (t - 0.5) * 2)
            for dx in (0, 1):
                for dy in (0, 1):
                    px[x + dx, y + dy] = col

    # شكل الأيقونة حسب شبكة أيقونات macOS (هامش 100px من 1024)
    margin, radius = 100 * s, 185 * s
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([margin, margin, S - margin, S - margin], radius=radius,
                                           fill=255)
    icon = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    icon.paste(grad, (0, 0), mask)

    # ظل ناعم أسفل الأيقونة
    shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle([margin, margin + 18 * s, S - margin, S - margin + 18 * s],
                                             radius=radius, fill=(40, 20, 90, 110))
    shadow = shadow.filter(ImageFilter.GaussianBlur(22 * s))
    base = Image.alpha_composite(shadow, icon)

    d = ImageDraw.Draw(base)
    cx, cy = S // 2, S // 2 + 10 * s
    r = 245 * s
    w = 62 * s
    # حلقة القرص (رسم دائري) مع جزء "محرَّر"
    d.arc([cx - r, cy - r, cx + r, cy + r], start=-90, end=200, fill=(255, 255, 255, 255), width=w)
    d.arc([cx - r, cy - r, cx + r, cy + r], start=212, end=258, fill=(255, 255, 255, 120), width=w)
    # نقطة مركزية
    d.ellipse([cx - 62 * s, cy - 62 * s, cx + 62 * s, cy + 62 * s], fill=(255, 255, 255, 255))
    # نجوم اللمعان
    star(d, cx + 250 * s, cy - 250 * s, 95 * s, (255, 255, 255, 255))
    star(d, cx + 115 * s, cy - 345 * s, 45 * s, (255, 255, 255, 230))
    star(d, cx + 345 * s, cy - 110 * s, 38 * s, (255, 255, 255, 210))

    final = base.resize((SIZE, SIZE), Image.LANCZOS)
    os.makedirs(ASSETS, exist_ok=True)
    final.save(os.path.join(ASSETS, "icon.png"))
    final.save(os.path.join(ASSETS, "icon.icns"))
    print("تم إنشاء assets/icon.png و assets/icon.icns")


if __name__ == "__main__":
    main()

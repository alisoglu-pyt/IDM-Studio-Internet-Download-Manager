"""Canvas tabanlı Material ikonları ve yuvarlatılmış şekiller."""

from __future__ import annotations

import math
import tkinter as tk

from .theme import Theme


def rounded_rect(canvas: tk.Canvas, x1: float, y1: float, x2: float, y2: float,
                 radius: float, **kwargs) -> int:
    """Canvas üzerine yumuşak köşeli bir dikdörtgen çizer."""
    if x2 < x1:
        x1, x2 = x2, x1
    if y2 < y1:
        y1, y2 = y2, y1
    radius = max(0.0, min(radius, (x2 - x1) / 2, (y2 - y1) / 2))
    r = radius
    points = (
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    )
    return canvas.create_polygon(points, smooth=True, splinesteps=24, **kwargs)


def draw_icon(canvas: tk.Canvas, name: str, cx: float, cy: float, size: float,
              color: str, width: float = 2.0, bg: str | None = None,
              tags: tuple[str, ...] = ()) -> None:
    """Merkezi (cx, cy) olacak şekilde vektörel bir ikon çizer."""
    s = float(size)
    w = max(1.3, float(width))
    line_kw = dict(fill=color, width=w, capstyle=tk.ROUND,
                   joinstyle=tk.ROUND, tags=tags)
    shape_kw = dict(fill=color, outline="", tags=tags)

    def line(*points: float, **extra) -> None:
        opts = dict(line_kw)
        opts.update(extra)
        canvas.create_line(*points, **opts)

    if name == "download":
        line(cx, cy - 0.36 * s, cx, cy + 0.10 * s)
        line(cx - 0.21 * s, cy - 0.09 * s, cx, cy + 0.13 * s,
             cx + 0.21 * s, cy - 0.09 * s)
        line(cx - 0.33 * s, cy + 0.22 * s, cx - 0.33 * s, cy + 0.31 * s,
             cx + 0.33 * s, cy + 0.31 * s, cx + 0.33 * s, cy + 0.22 * s)

    elif name == "pause":
        line(cx - 0.17 * s, cy - 0.27 * s, cx - 0.17 * s, cy + 0.27 * s,
             width=0.17 * s)
        line(cx + 0.17 * s, cy - 0.27 * s, cx + 0.17 * s, cy + 0.27 * s,
             width=0.17 * s)

    elif name == "play":
        canvas.create_polygon(
            cx - 0.18 * s, cy - 0.30 * s,
            cx + 0.31 * s, cy,
            cx - 0.18 * s, cy + 0.30 * s,
            fill=color, outline="", joinstyle=tk.ROUND, tags=tags,
        )

    elif name == "check":
        line(cx - 0.32 * s, cy + 0.01 * s, cx - 0.09 * s, cy + 0.23 * s,
             cx + 0.33 * s, cy - 0.23 * s)

    elif name == "close":
        line(cx - 0.26 * s, cy - 0.26 * s, cx + 0.26 * s, cy + 0.26 * s)
        line(cx + 0.26 * s, cy - 0.26 * s, cx - 0.26 * s, cy + 0.26 * s)

    elif name == "trash":
        line(cx - 0.30 * s, cy - 0.23 * s, cx + 0.30 * s, cy - 0.23 * s)
        line(cx - 0.10 * s, cy - 0.23 * s, cx - 0.08 * s, cy - 0.33 * s,
             cx + 0.08 * s, cy - 0.33 * s, cx + 0.10 * s, cy - 0.23 * s)
        line(cx - 0.23 * s, cy - 0.14 * s, cx - 0.19 * s, cy + 0.32 * s,
             cx + 0.19 * s, cy + 0.32 * s, cx + 0.23 * s, cy - 0.14 * s)
        line(cx - 0.09 * s, cy - 0.03 * s, cx - 0.08 * s, cy + 0.21 * s)
        line(cx + 0.09 * s, cy - 0.03 * s, cx + 0.08 * s, cy + 0.21 * s)

    elif name == "folder":
        canvas.create_line(
            cx - 0.36 * s, cy - 0.22 * s,
            cx - 0.08 * s, cy - 0.22 * s,
            cx + 0.00 * s, cy - 0.10 * s,
            cx + 0.34 * s, cy - 0.10 * s,
            cx + 0.31 * s, cy + 0.28 * s,
            cx - 0.31 * s, cy + 0.28 * s,
            cx - 0.36 * s, cy - 0.22 * s,
            fill=color, width=w, capstyle=tk.ROUND,
            joinstyle=tk.ROUND, tags=tags,
        )

    elif name == "plus":
        line(cx - 0.30 * s, cy, cx + 0.30 * s, cy)
        line(cx, cy - 0.30 * s, cx, cy + 0.30 * s)

    elif name == "minus":
        line(cx - 0.30 * s, cy, cx + 0.30 * s, cy)

    elif name == "moon":
        canvas.create_oval(cx - 0.35 * s, cy - 0.35 * s,
                           cx + 0.35 * s, cy + 0.35 * s, **shape_kw)
        cut_bg = bg or "#000000"
        canvas.create_oval(cx - 0.14 * s, cy - 0.40 * s,
                           cx + 0.46 * s, cy + 0.20 * s,
                           fill=cut_bg, outline="", tags=tags)

    elif name == "sun":
        canvas.create_oval(cx - 0.15 * s, cy - 0.15 * s,
                           cx + 0.15 * s, cy + 0.15 * s,
                           outline=color, width=w, tags=tags)
        for angle in range(0, 360, 45):
            rad = math.radians(angle)
            x1 = cx + math.cos(rad) * 0.25 * s
            y1 = cy + math.sin(rad) * 0.25 * s
            x2 = cx + math.cos(rad) * 0.35 * s
            y2 = cy + math.sin(rad) * 0.35 * s
            line(x1, y1, x2, y2)

    elif name == "alert":
        canvas.create_line(
            cx, cy - 0.34 * s,
            cx + 0.34 * s, cy + 0.28 * s,
            cx - 0.34 * s, cy + 0.28 * s,
            cx, cy - 0.34 * s,
            fill=color, width=w, capstyle=tk.ROUND,
            joinstyle=tk.ROUND, tags=tags,
        )
        line(cx, cy - 0.10 * s, cx, cy + 0.08 * s)
        canvas.create_oval(cx - 0.02 * s, cy + 0.15 * s,
                           cx + 0.02 * s, cy + 0.19 * s, **shape_kw)

    elif name == "info":
        canvas.create_oval(cx - 0.34 * s, cy - 0.34 * s,
                           cx + 0.34 * s, cy + 0.34 * s,
                           outline=color, width=w, tags=tags)
        line(cx, cy - 0.06 * s, cx, cy + 0.19 * s)
        canvas.create_oval(cx - 0.035 * s, cy - 0.22 * s,
                           cx + 0.035 * s, cy - 0.15 * s, **shape_kw)

    elif name == "globe":
        radius = 0.34 * s
        canvas.create_oval(
            cx - radius, cy - radius, cx + radius, cy + radius,
            outline=color, width=w, tags=tags,
        )
        line(cx - radius, cy, cx + radius, cy)
        canvas.create_oval(
            cx - 0.15 * s, cy - radius, cx + 0.15 * s, cy + radius,
            outline=color, width=w, tags=tags,
        )
        canvas.create_arc(
            cx - radius, cy - 0.19 * s, cx + radius, cy + 0.19 * s,
            start=0, extent=180, style=tk.ARC, outline=color,
            width=w, tags=tags,
        )

    elif name == "refresh":
        canvas.create_arc(
            cx - 0.30 * s, cy - 0.30 * s, cx + 0.30 * s, cy + 0.30 * s,
            start=35, extent=285, style=tk.ARC, outline=color,
            width=w, tags=tags,
        )
        canvas.create_polygon(
            cx + 0.08 * s, cy - 0.34 * s,
            cx + 0.36 * s, cy - 0.28 * s,
            cx + 0.22 * s, cy - 0.04 * s,
            fill=color, outline="", tags=tags,
        )

    elif name == "grid":
        gap = 0.07 * s
        cell = 0.24 * s
        for dx, dy in ((-cell - gap, -cell - gap), (gap, -cell - gap),
                       (-cell - gap, gap), (gap, gap)):
            rounded_rect(
                canvas, cx + dx, cy + dy, cx + dx + cell, cy + dy + cell,
                cell * 0.28, fill=color, outline="", tags=tags,
            )

    elif name == "clock":
        canvas.create_oval(cx - 0.32 * s, cy - 0.32 * s,
                           cx + 0.32 * s, cy + 0.32 * s,
                           outline=color, width=w, tags=tags)
        line(cx, cy - 0.18 * s, cx, cy, cx + 0.15 * s, cy + 0.08 * s)

    elif name == "file":
        canvas.create_line(
            cx - 0.24 * s, cy - 0.34 * s,
            cx + 0.10 * s, cy - 0.34 * s,
            cx + 0.26 * s, cy - 0.16 * s,
            cx + 0.26 * s, cy + 0.34 * s,
            cx - 0.24 * s, cy + 0.34 * s,
            cx - 0.24 * s, cy - 0.34 * s,
            fill=color, width=w, capstyle=tk.ROUND,
            joinstyle=tk.ROUND, tags=tags,
        )
        line(cx + 0.10 * s, cy - 0.34 * s, cx + 0.10 * s, cy - 0.16 * s,
             cx + 0.26 * s, cy - 0.16 * s)
        line(cx - 0.12 * s, cy + 0.04 * s, cx + 0.14 * s, cy + 0.04 * s)
        line(cx - 0.12 * s, cy + 0.16 * s, cx + 0.14 * s, cy + 0.16 * s)


def make_app_icon(theme: Theme) -> tk.PhotoImage:
    """Pencere simgesi için 64x64 boyutunda bir PhotoImage üretir."""
    size = 64
    radius = 17
    img = tk.PhotoImage(width=size, height=size)
    primary = theme.c("primary")
    foreground = theme.c("on_primary")

    for y in range(size):
        if y < radius:
            inset = radius - int(math.sqrt(max(0, radius ** 2 - (radius - y) ** 2)))
        elif y >= size - radius:
            yy = size - 1 - y
            inset = radius - int(math.sqrt(max(0, radius ** 2 - (radius - yy) ** 2)))
        else:
            inset = 0
        img.put(primary, to=(inset, y, size - inset, y + 1))

    img.put(foreground, to=(28, 15, 37, 35))
    for y in range(30, 47):
        half = int((47 - y) * 0.82)
        if half > 0:
            img.put(foreground, to=(32 - half, y, 32 + half + 1, y + 1))
    img.put(foreground, to=(18, 48, 46, 52))
    img.put(foreground, to=(18, 42, 22, 52))
    img.put(foreground, to=(42, 42, 46, 52))
    return img

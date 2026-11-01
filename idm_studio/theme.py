"""Material 3 renk paleti ve tipografi yardımcıları."""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont

PALETTES = {
    "light": {
        "primary": "#6750A4",
        "on_primary": "#FFFFFF",
        "primary_container": "#EADDFF",
        "on_primary_container": "#21005D",
        "secondary": "#625B71",
        "secondary_container": "#E8DEF8",
        "on_secondary_container": "#1D192B",
        "surface": "#FEF7FF",
        "surface_container_lowest": "#FFFFFF",
        "surface_container_low": "#F7F2FA",
        "surface_container": "#F3EDF7",
        "surface_container_high": "#ECE6F0",
        "surface_container_highest": "#E6E0E9",
        "on_surface": "#1D1B20",
        "on_surface_variant": "#49454F",
        "outline": "#79747E",
        "outline_variant": "#CAC4D0",
        "surface_variant": "#E7E0EC",
        "error": "#B3261E",
        "error_container": "#F9DEDC",
        "on_error_container": "#410E0B",
        "success": "#2E7D32",
        "success_container": "#DCF2DE",
        "on_success_container": "#0B3D10",
        "warning": "#8A5A00",
        "warning_container": "#FCEBC0",
        "on_warning_container": "#3B2F00",
        "inverse_surface": "#322F35",
        "inverse_on_surface": "#F5EFF7",
        "inverse_primary": "#D0BCFF",
    },
    "dark": {
        "primary": "#D0BCFF",
        "on_primary": "#381E72",
        "primary_container": "#4F378B",
        "on_primary_container": "#EADDFF",
        "secondary": "#CCC2DC",
        "secondary_container": "#4A4458",
        "on_secondary_container": "#E8DEF8",
        "surface": "#141218",
        "surface_container_lowest": "#0F0D13",
        "surface_container_low": "#1D1B20",
        "surface_container": "#211F26",
        "surface_container_high": "#2B2930",
        "surface_container_highest": "#36343B",
        "on_surface": "#E6E0E9",
        "on_surface_variant": "#CAC4D0",
        "outline": "#938F99",
        "outline_variant": "#49454F",
        "surface_variant": "#49454F",
        "error": "#F2B8B5",
        "error_container": "#8C1D18",
        "on_error_container": "#F9DEDC",
        "success": "#9BD49F",
        "success_container": "#1F3A22",
        "on_success_container": "#C7F0C9",
        "warning": "#FFB869",
        "warning_container": "#4A3200",
        "on_warning_container": "#FFDEA8",
        "inverse_surface": "#E6E0E9",
        "inverse_on_surface": "#322F35",
        "inverse_primary": "#6750A4",
    },
}

_FONT_STACK = (
    "Roboto",
    "Inter",
    "Segoe UI",
    "Ubuntu",
    "Noto Sans",
    "Cantarell",
    "DejaVu Sans",
)


def _rgb(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    if len(color) == 3:
        color = "".join(ch * 2 for ch in color)
    return int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)


def blend(color_a: str, color_b: str, amount: float) -> str:
    """color_a'dan color_b'ye doğru yumuşak geçiş rengi üretir."""
    amount = max(0.0, min(1.0, amount))
    ar, ag, ab = _rgb(color_a)
    br, bg, bb = _rgb(color_b)
    return "#%02X%02X%02X" % (
        round(ar + (br - ar) * amount),
        round(ag + (bg - ag) * amount),
        round(ab + (bb - ab) * amount),
    )


def luminance(color: str) -> float:
    r, g, b = (c / 255.0 for c in _rgb(color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


class Theme:
    """Tema durumunu, renkleri ve font önbelleğini tutar."""

    def __init__(self, root: tk.Misc, mode: str = "light") -> None:
        self.root = root
        self.mode = mode if mode in PALETTES else "light"
        self.family = self._pick_family()
        self._fonts: dict[tuple[int, str], tkfont.Font] = {}

    def _pick_family(self) -> str:
        try:
            available = set(tkfont.families(self.root))
        except tk.TclError:
            return "DejaVu Sans"
        for family in _FONT_STACK:
            if family in available:
                return family
        return "DejaVu Sans"

    @property
    def colors(self) -> dict[str, str]:
        return PALETTES[self.mode]

    def c(self, token: str) -> str:
        return self.colors[token]

    def font(self, size: int, weight: str = "normal") -> tkfont.Font:
        key = (size, weight)
        if key not in self._fonts:
            self._fonts[key] = tkfont.Font(
                root=self.root,
                family=self.family,
                size=size,
                weight=weight,
            )
        return self._fonts[key]

    def set_mode(self, mode: str) -> None:
        if mode in PALETTES:
            self.mode = mode

    def toggle(self) -> str:
        self.mode = "dark" if self.mode == "light" else "light"
        return self.mode

    def hover(self, base: str, fg: str | None = None, amount: float = 0.09) -> str:
        fg = fg or self.c("on_surface")
        return blend(base, fg, amount)

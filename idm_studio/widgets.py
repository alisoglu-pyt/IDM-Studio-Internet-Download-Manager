"""Material 3 görünümlü özel Tkinter bileşenleri."""

from __future__ import annotations

import tkinter as tk
from typing import Callable, Optional

from .draw import draw_icon, rounded_rect
from .theme import Theme, blend
from .utils import ellipsize


class Tooltip:
    """Küçük, gecikmeli bir fare ipucu penceresi."""

    def __init__(self, widget: tk.Widget, theme: Theme, text: str) -> None:
        self.widget = widget
        self.theme = theme
        self.text = text
        self._window: Optional[tk.Toplevel] = None
        self._after_id: Optional[str] = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self.hide, add="+")
        widget.bind("<ButtonPress>", self.hide, add="+")

    def _schedule(self, _event=None) -> None:
        self._cancel()
        self._after_id = self.widget.after(550, self._show)

    def _cancel(self) -> None:
        if self._after_id:
            try:
                self.widget.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None

    def _show(self) -> None:
        self._after_id = None
        if self._window or not self.widget.winfo_exists():
            return
        window = tk.Toplevel(self.widget)
        window.wm_overrideredirect(True)
        window.configure(bg=self.theme.c("inverse_surface"))
        try:
            window.attributes("-topmost", True)
        except tk.TclError:
            pass
        label = tk.Label(
            window,
            text=self.text,
            bg=self.theme.c("inverse_surface"),
            fg=self.theme.c("inverse_on_surface"),
            font=self.theme.font(9),
            padx=10,
            pady=6,
        )
        label.pack()
        window.update_idletasks()
        x = self.widget.winfo_rootx() + self.widget.winfo_width() // 2
        x -= window.winfo_width() // 2
        x = max(8, min(x, self.widget.winfo_screenwidth() - window.winfo_width() - 8))
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 8
        window.wm_geometry(f"+{x}+{y}")
        self._window = window

    def hide(self, _event=None) -> None:
        self._cancel()
        if self._window is not None:
            try:
                self._window.destroy()
            except tk.TclError:
                pass
            self._window = None


class MaterialButton(tk.Canvas):
    """Dolgulu, tonlu, çerçeveli veya metin görünümlü buton."""

    def __init__(
        self,
        master: tk.Misc,
        theme: Theme,
        text: str,
        command: Optional[Callable[[], None]] = None,
        icon: Optional[str] = None,
        kind: str = "filled",
        height: int = 42,
        font_size: int = 10,
        bg: Optional[str] = None,
        width: Optional[int] = None,
    ) -> None:
        self.theme = theme
        self._text = text
        self._icon = icon
        self._kind = kind
        self._command = command
        self._height = height
        self._font = theme.font(font_size, "bold")
        self._bg = bg or theme.c("surface")
        self._enabled = True
        self._hovered = False
        self._pressed = False

        content = self._font.measure(text) + (25 if icon else 0)
        self._width = width or max(96, content + 44)

        super().__init__(
            master,
            width=self._width,
            height=self._height,
            bg=self._bg,
            highlightthickness=0,
            bd=0,
            takefocus=1,
        )
        self.configure(cursor="hand2")
        self.bind("<Configure>", lambda _e: self._draw())
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Return>", lambda _e: self._activate())
        self.bind("<space>", lambda _e: self._activate())
        self._draw()

    def _palette(self) -> tuple[str, str, str]:
        t = self.theme
        if self._kind == "filled":
            return t.c("primary"), t.c("on_primary"), ""
        if self._kind == "tonal":
            return t.c("primary_container"), t.c("on_primary_container"), ""
        if self._kind == "outlined":
            return self._bg, t.c("primary"), t.c("outline")
        return self._bg, t.c("primary"), ""

    def _draw(self) -> None:
        self.delete("all")
        width = self.winfo_width()
        if width <= 1:
            width = self._width
        height = self._height
        base, fg, border = self._palette()

        if not self._enabled:
            base = blend(base, self._bg, 0.6)
            fg = self.theme.c("on_surface_variant")

        fill = base
        outline = border or base
        if self._kind == "text":
            fill = self._bg
            outline = fill
            if self._hovered and self._enabled:
                fill = blend(self._bg, self.theme.c("primary"), 0.08)
                outline = fill
        elif self._kind == "outlined":
            fill = (
                blend(self._bg, self.theme.c("primary"), 0.06)
                if (self._hovered and self._enabled) else self._bg
            )
            outline = self.theme.c("primary") if (self._hovered and self._enabled) else border
        else:
            if self._hovered and self._enabled:
                fill = blend(base, fg, 0.10)
            if self._pressed and self._enabled:
                fill = blend(base, fg, 0.16)
            outline = fill

        rounded_rect(
            self, 1, 1, width - 1, height - 1, height / 2,
            fill=fill, outline=outline,
            width=1 if border else 0,
        )

        content = self._font.measure(self._text) + (25 if self._icon else 0)
        x = (width - content) / 2
        if self._icon:
            draw_icon(
                self, self._icon, x + 8, height / 2 + 0.5, 16, fg,
                width=1.8, bg=fill,
            )
            x += 25
        self.create_text(
            x, height / 2 + 0.5, text=self._text, anchor="w",
            fill=fg, font=self._font,
        )

    def _on_enter(self, _event=None) -> None:
        self._hovered = True
        self._draw()

    def _on_leave(self, _event=None) -> None:
        self._hovered = False
        self._pressed = False
        self._draw()

    def _on_press(self, _event=None) -> None:
        if not self._enabled:
            return
        self._pressed = True
        self._draw()

    def _on_release(self, event) -> None:
        if not self._enabled:
            return
        was_pressed = self._pressed
        self._pressed = False
        self._draw()
        if was_pressed and 0 <= event.x <= self.winfo_width() and 0 <= event.y <= self._height:
            self._activate()

    def _activate(self) -> None:
        if self._enabled and self._command:
            self._command()

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        self.configure(cursor="hand2" if enabled else "arrow")
        self._draw()


class IconButton(tk.Canvas):
    """Dairesel arka planlı, ikonlu buton."""

    def __init__(
        self,
        master: tk.Misc,
        theme: Theme,
        icon: str,
        command: Optional[Callable[[], None]] = None,
        size: int = 42,
        bg: Optional[str] = None,
        kind: str = "standard",
        icon_color: Optional[str] = None,
        tooltip: Optional[str] = None,
    ) -> None:
        self.theme = theme
        self._icon = icon
        self._command = command
        self._size = size
        self._kind = kind
        self._bg = bg or theme.c("surface")
        self._icon_color = icon_color
        self._hovered = False
        self._pressed = False

        super().__init__(
            master,
            width=size,
            height=size,
            bg=self._bg,
            highlightthickness=0,
            bd=0,
            takefocus=1,
        )
        self.configure(cursor="hand2")
        self.bind("<Configure>", lambda _e: self._draw())
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Return>", lambda _e: self._activate())
        self.bind("<space>", lambda _e: self._activate())
        if tooltip:
            Tooltip(self, theme, tooltip)
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        size = self._size
        center = size / 2

        if self._kind == "filled":
            base = self.theme.c("primary")
            fg = self._icon_color or self.theme.c("on_primary")
        elif self._kind == "tonal":
            base = self.theme.c("surface_container_high")
            fg = self._icon_color or self.theme.c("on_surface")
        else:
            base = self._bg
            fg = self._icon_color or self.theme.c("on_surface_variant")

        fill = base
        if self._kind == "standard":
            fill = self._bg
            if self._hovered:
                fill = blend(self._bg, self.theme.c("on_surface"), 0.09)
        else:
            if self._hovered:
                fill = blend(base, fg, 0.12)
            if self._pressed:
                fill = blend(base, fg, 0.18)

        if self._kind != "standard" or self._hovered or self._pressed:
            self.create_oval(
                1, 1, size - 1, size - 1,
                fill=fill, outline="",
            )
        draw_icon(
            self, self._icon, center, center, size * 0.50, fg,
            width=1.8, bg=fill,
        )

    def _on_enter(self, _event=None) -> None:
        self._hovered = True
        self._draw()

    def _on_leave(self, _event=None) -> None:
        self._hovered = False
        self._pressed = False
        self._draw()

    def _on_press(self, _event=None) -> None:
        self._pressed = True
        self._draw()

    def _on_release(self, event) -> None:
        was_pressed = self._pressed
        self._pressed = False
        self._draw()
        if was_pressed and 0 <= event.x <= self._size and 0 <= event.y <= self._size:
            self._activate()

    def _activate(self) -> None:
        if self._command:
            self._command()

    def set_icon(self, icon: str) -> None:
        self._icon = icon
        self._draw()


class PartPicker(tk.Canvas):
    """Parça sayısını 1–10 arasında seçmeye yarayan segmentli kontrol."""

    def __init__(
        self,
        master: tk.Misc,
        theme: Theme,
        value: int = 4,
        maximum: int = 10,
        command: Optional[Callable[[int], None]] = None,
        bg: Optional[str] = None,
        height: int = 44,
    ) -> None:
        self.theme = theme
        self._bg = bg or theme.c("surface")
        self._maximum = max(1, int(maximum))
        self._value = max(1, min(int(value), self._maximum))
        self._command = command
        self._height = height
        self._hover: Optional[int] = None
        self._pressed: Optional[int] = None

        super().__init__(
            master,
            height=height,
            bg=self._bg,
            highlightthickness=0,
            bd=0,
            takefocus=1,
        )
        self.configure(cursor="hand2")
        self.bind("<Configure>", lambda _e: self._draw())
        self.bind("<Motion>", self._on_motion)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Left>", lambda _e: self._step(-1))
        self.bind("<Right>", lambda _e: self._step(1))
        self.bind("<Home>", lambda _e: self._select(1))
        self.bind("<End>", lambda _e: self._select(self._maximum))
        self._draw()

    def _segments(self, width: float) -> list[tuple[float, float]]:
        gap = 4.0
        usable = max(1.0, width - 2.0 - gap * (self._maximum - 1))
        segment_width = usable / self._maximum
        return [
            (
                1.0 + index * (segment_width + gap),
                1.0 + index * (segment_width + gap) + segment_width,
            )
            for index in range(self._maximum)
        ]

    def _index_at(self, x: float) -> Optional[int]:
        width = self.winfo_width()
        if width <= 1:
            return None
        for index, (x1, x2) in enumerate(self._segments(width)):
            if x1 <= x <= x2:
                return index
        return None

    def _draw(self) -> None:
        self.delete("all")
        width = self.winfo_width()
        if width <= 1:
            width = 480
        height = self._height
        theme = self.theme
        font = theme.font(9, "bold")
        normal_font = theme.font(9)

        for index, (x1, x2) in enumerate(self._segments(width)):
            selected = index + 1 == self._value
            hovered = index == self._hover
            if selected:
                fill = theme.c("primary")
                color = theme.c("on_primary")
            elif hovered:
                fill = theme.c("surface_container_highest")
                color = theme.c("on_surface")
            else:
                fill = theme.c("surface_container_high")
                color = theme.c("on_surface_variant")
            rounded_rect(
                self, x1, 1, x2, height - 1, (height - 2) / 2,
                fill=fill, outline="",
            )
            self.create_text(
                (x1 + x2) / 2, height / 2 + 0.5,
                text=str(index + 1),
                fill=color,
                font=font if selected else normal_font,
            )

    def _on_motion(self, event) -> None:
        index = self._index_at(event.x)
        if index != self._hover:
            self._hover = index
            self.configure(cursor="hand2" if index is not None else "")
            self._draw()

    def _on_leave(self, _event=None) -> None:
        self._hover = None
        self._pressed = None
        self._draw()

    def _on_press(self, event) -> None:
        self._pressed = self._index_at(event.x)
        if self._pressed is not None:
            self.focus_set()
            self._hover = self._pressed
            self._draw()

    def _on_release(self, event) -> None:
        index = self._index_at(event.x)
        pressed = self._pressed
        self._pressed = None
        if index is not None and index == pressed:
            self._select(index + 1)
        else:
            self._draw()

    def _step(self, delta: int) -> str:
        self._select(self._value + delta)
        return "break"

    def _select(self, value: int) -> None:
        value = max(1, min(int(value), self._maximum))
        if value == self._value:
            return
        self._value = value
        self._draw()
        if self._command:
            self._command(value)

    def get(self) -> int:
        return self._value

    def set(self, value: int) -> None:
        value = max(1, min(int(value), self._maximum))
        if value != self._value:
            self._value = value
            self._draw()


class MaterialEntry(tk.Frame):
    """Yuvarlatılmış, etiketli metin giriş alanı."""

    def __init__(
        self,
        master: tk.Misc,
        theme: Theme,
        label: str,
        bg: Optional[str] = None,
        width: int = 380,
        font_size: int = 10,
    ) -> None:
        self.theme = theme
        self._bg = bg or theme.c("surface")
        self._label = label
        self._font = theme.font(font_size)
        self._label_font = theme.font(8)
        self._invalid = False
        self._focused = False
        self._width = width

        super().__init__(master, bg=self._bg, height=62)
        self.canvas = tk.Canvas(
            self, bg=self._bg, height=62, width=width,
            highlightthickness=0, bd=0,
        )
        self.canvas.pack(fill="both", expand=True)

        self.var = tk.StringVar()
        self.entry = tk.Entry(
            self.canvas,
            textvariable=self.var,
            bd=0,
            relief="flat",
            highlightthickness=0,
            bg=theme.c("surface_container_high"),
            fg=theme.c("on_surface"),
            insertbackground=theme.c("primary"),
            selectbackground=theme.c("primary"),
            selectforeground=theme.c("on_primary"),
            font=self._font,
        )
        self._entry_item = self.canvas.create_window(
            18, 30, window=self.entry, anchor="nw", width=width - 36, height=26,
        )
        self.canvas.bind("<Configure>", self._on_configure)
        self.entry.bind("<FocusIn>", self._on_focus_in, add="+")
        self.entry.bind("<FocusOut>", self._on_focus_out, add="+")
        self.entry.bind("<Return>", lambda _e: self.canvas.event_generate("<<EntryReturn>>"))
        self._draw()

    def _on_configure(self, event) -> None:
        self.canvas.coords(self._entry_item, 18, 30)
        self.canvas.itemconfigure(self._entry_item, width=max(40, event.width - 36))
        self._draw()

    def _on_focus_in(self, _event=None) -> None:
        self._focused = True
        self._draw()

    def _on_focus_out(self, _event=None) -> None:
        self._focused = False
        self._draw()

    def _draw(self) -> None:
        self.canvas.delete("bg")
        width = self.canvas.winfo_width()
        if width <= 1:
            width = self._width
        fill = self.theme.c("surface_container_high")
        if self._invalid:
            outline = self.theme.c("error")
            border = 2
            label_color = self.theme.c("error")
        elif self._focused:
            outline = self.theme.c("primary")
            border = 2
            label_color = self.theme.c("primary")
        else:
            outline = self.theme.c("outline_variant")
            border = 1
            label_color = self.theme.c("on_surface_variant")
        rounded_rect(
            self.canvas, 1, 1, width - 1, 61, 13,
            fill=fill, outline=outline, width=border, tags=("bg",),
        )
        self.canvas.create_text(
            18, 11, text=self._label, anchor="w",
            fill=label_color, font=self._label_font, tags=("bg",),
        )
        self.canvas.tag_lower("bg")

    def get(self) -> str:
        return self.var.get().strip()

    def set(self, value: str) -> None:
        self.var.set(value)

    def focus_entry(self) -> None:
        self.entry.focus_set()
        self.entry.icursor("end")

    def set_invalid(self, invalid: bool = True) -> None:
        self._invalid = invalid
        self._draw()

    def on_return(self, callback: Callable[[], None]) -> None:
        self.canvas.bind("<<EntryReturn>>", lambda _e: callback())


class NavItem(tk.Canvas):
    """Kenar çubuğu gezinme öğesi."""

    def __init__(
        self,
        master: tk.Misc,
        theme: Theme,
        icon: str,
        text: str,
        command: Optional[Callable[[], None]] = None,
        bg: Optional[str] = None,
        height: int = 46,
    ) -> None:
        self.theme = theme
        self._icon = icon
        self._text = text
        self._command = command
        self._bg = bg or theme.c("surface_container_low")
        self._height = height
        self._selected = False
        self._hovered = False
        self._count: Optional[int] = None

        super().__init__(
            master, bg=self._bg, height=height,
            highlightthickness=0, bd=0, takefocus=1,
        )
        self.configure(cursor="hand2")
        self.bind("<Configure>", lambda _e: self._draw())
        self.bind("<Button-1>", lambda _e: self._activate())
        self.bind("<Return>", lambda _e: self._activate())
        self.bind("<space>", lambda _e: self._activate())
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

    def _on_enter(self, _event=None) -> None:
        self._hovered = True
        self._draw()

    def _on_leave(self, _event=None) -> None:
        self._hovered = False
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        width = self.winfo_width()
        if width <= 1:
            width = 220
        height = self._height

        if self._selected:
            fill = self.theme.c("primary_container")
            fg = self.theme.c("on_primary_container")
            icon_color = self.theme.c("on_primary_container")
        else:
            fill = blend(self._bg, self.theme.c("on_surface"), 0.06) if self._hovered else self._bg
            fg = self.theme.c("on_surface_variant")
            icon_color = self.theme.c("on_surface_variant")

        rounded_rect(self, 0, 0, width, height, height / 2, fill=fill, outline="")
        draw_icon(
            self, self._icon, 24, height / 2, 18, icon_color,
            width=1.8, bg=fill,
        )

        count_width = 0
        if self._count:
            count_text = str(self._count)
            count_width = self.theme.font(8, "bold").measure(count_text) + 22
            self.create_text(
                width - 16, height / 2, text=count_text, anchor="e",
                fill=fg, font=self.theme.font(8, "bold"),
            )
        font = self.theme.font(10, "bold" if self._selected else "normal")
        text = ellipsize(self._text, font, max(20, width - 48 - count_width))
        self.create_text(
            44, height / 2, text=text, anchor="w",
            fill=fg, font=font,
        )

    def _activate(self) -> None:
        if self._command:
            self._command()

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self._draw()

    def set_count(self, count: int) -> None:
        new_count = count if count > 0 else None
        if new_count != self._count:
            self._count = new_count
            self._draw()

    def set_text(self, text: str) -> None:
        if text != self._text:
            self._text = text
            self._draw()


class SlimScrollbar(tk.Canvas):
    """İnce, yuvarlatılmış ve sürüklenebilir dikey kaydırma çubuğu."""

    def __init__(self, master: tk.Misc, theme: Theme, target: tk.Canvas,
                 bg: Optional[str] = None) -> None:
        self.theme = theme
        self.target = target
        self._bg = bg or theme.c("surface")
        self._first = 0.0
        self._last = 1.0
        self._drag_offset: Optional[float] = None
        self._thumb: Optional[int] = None

        super().__init__(master, width=8, bg=self._bg, highlightthickness=0, bd=0)
        self.target.configure(yscrollcommand=self._on_scroll)
        self.bind("<Configure>", lambda _e: self.refresh())
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)

    def _on_scroll(self, first: str, last: str) -> None:
        self._first = float(first)
        self._last = float(last)
        self.refresh()

    def refresh(self) -> None:
        self.delete("all")
        height = self.winfo_height()
        width = self.winfo_width()
        if height <= 1:
            return
        span = self._last - self._first
        if span >= 0.999 or span <= 0:
            self._thumb = None
            self.configure(cursor="")
            return
        thumb_height = max(40, int(height * span))
        travel = max(1, height - thumb_height)
        y = int(max(0, min(travel, self._first / max(1e-6, 1 - span) * travel)))
        color = blend(self._bg, self.theme.c("on_surface_variant"), 0.35)
        self._thumb = rounded_rect(
            self, max(0, width / 2 - 3), y, min(width, width / 2 + 3), y + thumb_height,
            3, fill=color, outline="",
        )
        self.configure(cursor="hand2")

    def _on_press(self, event) -> None:
        height = self.winfo_height()
        span = self._last - self._first
        if span >= 0.999:
            return
        thumb_height = max(40, int(height * span))
        travel = max(1, height - thumb_height)
        y = int(max(0, min(travel, self._first / max(1e-6, 1 - span) * travel)))
        if y <= event.y <= y + thumb_height:
            self._drag_offset = event.y - y
        else:
            self._drag_offset = thumb_height / 2
            self._move_to(event.y)
        self._on_drag(event)

    def _on_drag(self, event) -> None:
        if self._drag_offset is None:
            return
        self._move_to(event.y)

    def _move_to(self, y: float) -> None:
        height = self.winfo_height()
        span = self._last - self._first
        thumb_height = max(40, int(height * span))
        travel = max(1, height - thumb_height)
        pos = (y - self._drag_offset) / travel
        self.target.yview_moveto(max(0.0, min(1.0, pos)))
        self.refresh()

    def _on_release(self, _event=None) -> None:
        self._drag_offset = None


class Snackbar(tk.Canvas):
    """Ekranın altında beliren kısa bilgi mesajı."""

    def __init__(self, master: tk.Misc, theme: Theme) -> None:
        self.theme = theme
        self._message = ""
        self._action_text = ""
        self._action: Optional[Callable[[], None]] = None
        self._hide_after: Optional[str] = None
        self._action_box = (0, 0, 0, 0)
        super().__init__(
            master, height=52, width=360, bg=theme.c("surface"),
            highlightthickness=0, bd=0,
        )

    def show(self, message: str, action_text: str = "",
             action: Optional[Callable[[], None]] = None,
             duration: int = 4200) -> None:
        self._cancel_timer()
        self._message = message
        self._action_text = action_text
        self._action = action
        font = self.theme.font(10)
        action_font = self.theme.font(10, "bold")
        text_width = font.measure(message)
        action_width = (action_font.measure(action_text) + 28) if action_text else 0
        width = min(680, max(320, text_width + action_width + 48))
        self.configure(width=width, height=52)
        self.delete("all")
        self.create_rectangle(0, 0, width, 52, fill=self.theme.c("surface"), outline="")
        rounded_rect(
            self, 1, 3, width - 1, 49, 24,
            fill=self.theme.c("inverse_surface"), outline="",
        )
        max_text = width - 44 - action_width
        label = ellipsize(message, font, max_text)
        self.create_text(
            22, 26, text=label, anchor="w",
            fill=self.theme.c("inverse_on_surface"), font=font,
        )
        if action_text:
            action_fill = self.theme.c("inverse_primary")
            x1 = width - 22 - action_font.measure(action_text) - 8
            action_id = self.create_text(
                width - 22, 26, text=action_text, anchor="e",
                fill=action_fill, font=action_font, tags=("snack-action",),
            )
            self._action_box = (x1, 8, width - 16, 44)
            self.tag_bind("snack-action", "<Button-1>", self._run_action)
            self.configure(cursor="")
            self._action_id = action_id
        else:
            self._action_box = (0, 0, 0, 0)
        self.place(relx=0.5, rely=1.0, y=-20, anchor="s")
        self.tk.call("raise", self._w)
        self._hide_after = self.after(duration, self.hide)

    def _run_action(self, _event=None) -> None:
        callback = self._action
        self.hide()
        if callback:
            callback()

    def hide(self) -> None:
        self._cancel_timer()
        self.place_forget()

    def _cancel_timer(self) -> None:
        if self._hide_after:
            try:
                self.after_cancel(self._hide_after)
            except tk.TclError:
                pass
            self._hide_after = None

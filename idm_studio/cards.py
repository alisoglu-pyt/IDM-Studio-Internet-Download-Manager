"""İndirme listesindeki kartların Canvas tabanlı çizimi."""

from __future__ import annotations

import time
import tkinter as tk

from .downloader import DownloadTask
from .draw import draw_icon, rounded_rect
from .i18n import tr
from .theme import Theme, blend
from .utils import (
    ellipsize,
    format_eta,
    format_speed,
    format_size,
    format_when,
    open_path,
    percentage,
)

CARD_HEIGHT = 132


class DownloadCard(tk.Canvas):
    """Tek bir indirmeyi gösteren Material kartı."""

    def __init__(self, master: tk.Misc, app, task: DownloadTask,
                 theme: Theme) -> None:
        self.app = app
        self.task = task
        self.theme = theme
        self._hover_act: str | None = None
        self._action_circles: dict[str, int] = {}
        self._action_handlers: dict[str, object] = {}
        self._action_tips: dict[str, str] = {}
        self._last_width = 0
        self._last_drawn_status: str | None = None
        self._tip_after: str | None = None
        self._tip_window: tk.Toplevel | None = None
        self._card_bg = theme.c("surface_container")

        super().__init__(
            master,
            height=CARD_HEIGHT,
            bg=theme.c("surface"),
            highlightthickness=0,
            bd=0,
        )
        self.bind("<Configure>", self._on_configure)
        self.bind("<Motion>", self._on_motion)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)
        self.bind("<Double-Button-1>", self._on_double_click)
        self.bind("<Button-4>", self.app._on_mousewheel)
        self.bind("<Button-5>", self.app._on_mousewheel)
        self.bind("<MouseWheel>", self.app._on_mousewheel)

    # ------------------------------------------------------------------ olaylar
    def _on_configure(self, event) -> None:
        if abs(event.width - self._last_width) > 1:
            self._last_width = event.width
            self.refresh()

    def _on_motion(self, event) -> None:
        tags = self.gettags("current")
        act = next((tag for tag in tags if tag.startswith("act")), None)
        if act != self._hover_act:
            self._hover_act = act
            self._hide_tip()
            hover_fill = blend(self._card_bg, self.theme.c("on_surface"), 0.09)
            for tag, item in self._action_circles.items():
                self.itemconfigure(
                    item, fill=hover_fill if tag == act else self._card_bg,
                )
            if act and act in self._action_tips and act in self._action_handlers:
                tip = self._action_tips[act]
                self._tip_after = self.after(600, lambda: self._show_tip(tip))
        if act:
            self.configure(cursor="hand2")
        elif self.task.status == "completed":
            self.configure(cursor="hand2")
        else:
            self.configure(cursor="")

    def _on_leave(self, _event=None) -> None:
        self._hover_act = None
        self._hide_tip()
        for item in self._action_circles.values():
            self.itemconfigure(item, fill=self._card_bg)
        self.configure(cursor="")

    def _show_tip(self, text: str) -> None:
        self._tip_after = None
        self._hide_tip()
        window = tk.Toplevel(self)
        window.wm_overrideredirect(True)
        window.configure(bg=self.theme.c("inverse_surface"))
        try:
            window.attributes("-topmost", True)
        except tk.TclError:
            pass
        tk.Label(
            window, text=text, bg=self.theme.c("inverse_surface"),
            fg=self.theme.c("inverse_on_surface"), font=self.theme.font(9),
            padx=10, pady=5,
        ).pack()
        window.update_idletasks()
        x = self.winfo_pointerx() + 12
        y = self.winfo_pointery() + 18
        x = min(x, self.winfo_screenwidth() - window.winfo_width() - 8)
        y = min(y, self.winfo_screenheight() - window.winfo_height() - 8)
        window.wm_geometry(f"+{max(8, x)}+{max(8, y)}")
        self._tip_window = window

    def _hide_tip(self) -> None:
        if self._tip_after:
            try:
                self.after_cancel(self._tip_after)
            except tk.TclError:
                pass
            self._tip_after = None
        if self._tip_window is not None:
            try:
                self._tip_window.destroy()
            except tk.TclError:
                pass
            self._tip_window = None

    def _on_click(self, _event=None) -> str:
        self._hide_tip()
        for tag in self.gettags("current"):
            handler = self._action_handlers.get(tag)
            if handler is not None:
                handler()  # type: ignore[operator]
                return "break"
        return ""

    def _on_double_click(self, _event=None) -> None:
        if self.task.status != "completed":
            return
        if any(tag.startswith("act") for tag in self.gettags("current")):
            return
        open_path(self.task.target_path)

    def _cancel(self) -> None:
        self.app.cancel_task(self.task.id)

    def _remove(self) -> None:
        self.app.remove_task(self.task.id)

    def _open_folder(self) -> None:
        open_path(self.task.directory)

    # ------------------------------------------------------------------ eylemler
    def _actions(self) -> list[tuple[str, str, object]]:
        status = self.task.status
        if status in ("downloading", "connecting"):
            return [
                ("pause", tr("action.pause"), self.task.pause),
                ("trash", tr("action.cancel"), self._cancel),
            ]
        if status == "pausing":
            return [
                ("pause", tr("action.pausing"), None),
                ("trash", tr("action.cancel"), self._cancel),
            ]
        if status == "paused":
            return [
                ("play", tr("action.resume"), self.task.resume),
                ("trash", tr("action.cancel"), self._cancel),
            ]
        if status == "scheduled":
            return [
                ("play", tr("action.start_now"), self.task.start),
                ("trash", tr("action.cancel"), self._cancel),
            ]
        if status == "retrying":
            return [
                ("pause", tr("action.pause"), self.task.pause),
                ("trash", tr("action.cancel"), self._cancel),
            ]
        if status == "error":
            return [
                ("refresh", tr("action.retry"), self.task.resume),
                ("trash", tr("action.remove"), self._remove),
            ]
        if status == "completed":
            return [
                ("folder", tr("action.open_folder"), self._open_folder),
                ("close", tr("action.remove_from_list"), self._remove),
            ]
        if status in ("queued", "merging", "canceling"):
            return [("trash", tr("action.cancel"), self._cancel)]
        return []

    def _status_colors(self) -> tuple[str, str, str]:
        theme = self.theme
        status = self.task.status
        if status == "completed":
            return "check", theme.c("success_container"), theme.c("success")
        if status == "error":
            return "alert", theme.c("error_container"), theme.c("error")
        if status in ("paused", "pausing"):
            return "pause", theme.c("warning_container"), theme.c("warning")
        if status == "scheduled":
            return "clock", theme.c("warning_container"), theme.c("warning")
        if status == "retrying":
            return "refresh", theme.c("warning_container"), theme.c("warning")
        if status == "merging":
            return "download", theme.c("primary_container"), theme.c("primary")
        if status in ("canceling", "canceled"):
            return "close", theme.c("surface_container_high"), theme.c("on_surface_variant")
        return "download", theme.c("primary_container"), theme.c("primary")

    # ------------------------------------------------------------------ çizim
    def refresh(self) -> None:
        self._redraw()

    def _redraw(self) -> None:
        self.delete("all")
        width = self.winfo_width()
        if width <= 1:
            width = 720
        height = CARD_HEIGHT
        task = self.task
        theme = self.theme
        status = task.status
        if status != self._last_drawn_status:
            self._last_drawn_status = status
            self._hide_tip()

        card_bg = self._card_bg
        border = blend(card_bg, theme.c("outline_variant"), 0.42)
        rounded_rect(
            self, 1, 1, width - 1, height - 1, 20,
            fill=card_bg, outline=border, width=1,
        )

        icon_name, circle_color, icon_color = self._status_colors()
        self.create_oval(
            24, 18, 68, 62, fill=circle_color, outline="",
        )
        draw_icon(
            self, icon_name, 46, 40, 26, icon_color,
            width=2.0, bg=circle_color,
        )

        actions = self._actions()
        action_total = len(actions) * 36 + max(0, len(actions) - 1) * 4
        text_right = width - 24 - (action_total + 24 if actions else 12)
        title_font = theme.font(12, "bold")
        url_font = theme.font(9)
        caption_font = theme.font(9)

        filename = task.filename or tr("card.filename_pending")
        self.create_text(
            78, 21, text=ellipsize(filename, title_font, max(40, text_right - 78)),
            anchor="nw", fill=theme.c("on_surface"), font=title_font,
        )
        url = task.resolved_url or task.url
        self.create_text(
            78, 44, text=ellipsize(url, url_font, max(40, text_right - 78)),
            anchor="nw", fill=theme.c("on_surface_variant"), font=url_font,
        )

        # İlerleme çubuğu
        track_x1, track_x2 = 78, width - 24
        track_y, track_h = 77, 8
        track_color = blend(card_bg, theme.c("outline_variant"), 0.55)
        rounded_rect(
            self, track_x1, track_y, track_x2, track_y + track_h, 4,
            fill=track_color, outline="",
        )

        if status == "completed":
            fill_color = theme.c("success")
        elif status == "error":
            fill_color = theme.c("error")
        elif status in ("paused", "pausing"):
            fill_color = theme.c("warning")
        elif status in ("scheduled", "retrying"):
            fill_color = theme.c("warning")
        else:
            fill_color = theme.c("primary")

        track_width = max(1, track_x2 - track_x1)
        progress = task.progress
        if task.total > 0:
            if progress > 0:
                fill_width = max(8.0, track_width * progress)
                rounded_rect(
                    self, track_x1, track_y, track_x1 + min(track_width, fill_width),
                    track_y + track_h, 4, fill=fill_color, outline="",
                )
        elif status in ("downloading", "connecting", "queued", "scheduled", "retrying"):
            # Toplam boyut bilinmiyorsa hareketli bir parça gösterilir.
            phase = (time.monotonic() * 0.48) % 1.35 - 0.18
            segment = track_width * 0.32
            left = max(track_x1, track_x1 + phase * track_width)
            right = min(track_x2, track_x1 + phase * track_width + segment)
            if right - left > 3:
                rounded_rect(
                    self, left, track_y, right, track_y + track_h, 4,
                    fill=fill_color, outline="",
                )
        pct = percentage(task.downloaded, task.total) if task.total else 0
        percent_text = tr("percent", value=pct)
        if status in ("downloading", "connecting"):
            left_text = tr(f"status.{status}")
            if task.downloaded:
                left_text += f" · {format_size(task.downloaded)}"
            if task.total:
                left_text += f" / {format_size(task.total)}"
            right_parts = []
            if task.total:
                right_parts.append(percent_text)
            if task.speed > 0:
                right_parts.append(format_speed(task.speed))
            eta = format_eta(task.eta)
            if eta:
                right_parts.append(f"~{eta}")
            right_text = " · ".join(right_parts)
            left_color = theme.c("on_surface_variant")
        elif status == "paused":
            left_text = tr("status.paused")
            if task.downloaded:
                left_text += f" · {format_size(task.downloaded)}"
            if task.total:
                left_text += f" / {format_size(task.total)}"
            right_text = percent_text if task.total else ""
            left_color = theme.c("warning")
        elif status == "pausing":
            left_text = f"{tr('status.pausing')}…"
            right_text = percent_text if task.total else ""
            left_color = theme.c("warning")
        elif status == "scheduled":
            left_text = tr("status.scheduled")
            right_text = tr("card.scheduled_for", when=format_when(task.scheduled_at))
            left_color = theme.c("warning")
        elif status == "retrying":
            left_text = tr("status.retrying")
            if task.max_retries:
                left_text += " · " + tr(
                    "card.retrying_count",
                    count=task.retry_count,
                    total=task.max_retries,
                )
            right_text = percent_text if task.total else ""
            left_color = theme.c("warning")
        elif status == "completed":
            left_text = f"{tr('status.completed')} · {format_size(task.total or task.downloaded)}"
            right_text = format_when(task.completed_at)
            left_color = theme.c("success")
        elif status == "error":
            left_text = f"{tr('status.error')} · {task.error or tr('card.unknown_error')}"
            right_text = tr("card.retry_hint")
            left_color = theme.c("error")
        elif status == "merging":
            left_text = f"{tr('status.merging')}…"
            right_text = tr("card.almost_done")
            left_color = theme.c("on_surface_variant")
        elif status == "canceling":
            left_text = f"{tr('status.canceling')}…"
            right_text = ""
            left_color = theme.c("on_surface_variant")
        else:
            left_text = tr("status.queued")
            right_text = ""
            left_color = theme.c("on_surface_variant")

        right_width = caption_font.measure(right_text) if right_text else 0
        left_max = max(40, (width - 24 - right_width - 18) - 78)
        self.create_text(
            78, 105, text=ellipsize(left_text, caption_font, left_max),
            anchor="w", fill=left_color, font=caption_font,
        )
        if right_text:
            self.create_text(
                width - 24, 105, text=right_text, anchor="e",
                fill=theme.c("on_surface_variant"), font=caption_font,
            )

        # Sağ üstteki ikon butonları
        self._action_circles = {}
        self._action_handlers = {}
        self._action_tips = {}
        if actions:
            start = width - 24 - action_total
            hover_fill = blend(card_bg, theme.c("on_surface"), 0.09)
            for index, (icon, tip, handler) in enumerate(actions):
                tag = f"act{index}"
                self._action_tips[tag] = tip
                cx = start + 18 + index * 40
                cy = 39
                circle = self.create_oval(
                    cx - 18, cy - 18, cx + 18, cy + 18,
                    fill=hover_fill if tag == self._hover_act else card_bg,
                    outline="", tags=(tag,),
                )
                self._action_circles[tag] = circle
                if handler is not None:
                    self._action_handlers[tag] = handler
                    color = theme.c("on_surface_variant")
                else:
                    color = blend(theme.c("on_surface_variant"), card_bg, 0.55)
                draw_icon(
                    self, icon, cx, cy, 17, color,
                    width=1.8, bg=hover_fill if tag == self._hover_act else card_bg,
                    tags=(tag,),
                )

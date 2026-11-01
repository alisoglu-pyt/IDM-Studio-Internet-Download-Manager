"""IDM Studio — Material 3 esintili Tkinter indirme yöneticisi."""

from __future__ import annotations

import json
import os
import queue
import sys
import tkinter as tk
from pathlib import Path

from .cards import DownloadCard
from .dialogs import AboutDialog, NewDownloadDialog
from .downloader import (
    ACTIVE_STATUSES,
    DEFAULT_CONNECTIONS,
    MAX_CONNECTIONS,
    DownloadTask,
)
from .draw import draw_icon, make_app_icon, rounded_rect
from .i18n import (
    LANGUAGE_NAMES,
    LANGUAGE_ORDER,
    get_language,
    set_language,
    tr,
)
from .theme import Theme
from .utils import default_download_dir, format_speed, open_path
from .widgets import (
    IconButton,
    MaterialButton,
    NavItem,
    SlimScrollbar,
    Snackbar,
)

APP_NAME = "IDM Studio"
APP_VERSION = "1.0.0"
CONFIG_DIR = Path.home() / ".config" / "idm-studio"
STATE_FILE = CONFIG_DIR / "state.json"

FILTER_KEYS = ("all", "active", "completed", "paused")


class IDMApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__(className="idm-studio")
        self.theme = Theme(self)
        self.configure(bg=self.theme.c("surface"))
        self.minsize(980, 640)
        self._center_window(1200, 780)

        self._tasks: dict[str, DownloadTask] = {}
        self._cards: dict[str, DownloadCard] = {}
        self._last_status: dict[str, str] = {}
        self._event_queue: queue.Queue[str] = queue.Queue()
        self._filter = "all"
        self._download_dir = default_download_dir()
        self._connections = DEFAULT_CONNECTIONS
        self._dialog: NewDownloadDialog | None = None
        self._closing = False
        self._poll_after_id: str | None = None
        self._nav_items: dict[str, NavItem] = {}
        self._folder_nav: NavItem | None = None
        self._snackbar: Snackbar | None = None
        self._scrollbar: SlimScrollbar | None = None
        self._icon_photo: tk.PhotoImage | None = None
        self._language_menu: tk.Menu | None = None
        self._language_var: tk.StringVar | None = None

        self._load_state()
        self.title(tr("app.title", app=APP_NAME))
        self._set_window_icon()
        self._build_ui()
        self._update_counts()
        self._update_header()
        self._render_list(reset_scroll=True)

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Control-n>", lambda _e: self.open_new_download())
        self.bind("<Control-l>", lambda _e: self._open_language_menu())
        self.bind("<F1>", lambda _e: self.open_about())
        self._poll_after_id = self.after(140, self._poll_queue)

    # ------------------------------------------------------------------ pencere
    @property
    def download_dir(self) -> str:
        return self._download_dir

    @property
    def default_connections(self) -> int:
        return self._connections

    def _center_window(self, width: int, height: int) -> None:
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        width = min(width, max(900, screen_w - 80))
        height = min(height, max(600, screen_h - 100))
        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 2 - 20)
        self.geometry(f"{width}x{height}+{x}+{y}")

    def _set_window_icon(self) -> None:
        try:
            self._icon_photo = make_app_icon(self.theme)
            self.iconphoto(True, self._icon_photo)
        except tk.TclError:
            pass

    # ------------------------------------------------------------------ durum
    def _load_state(self) -> None:
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if not isinstance(data, dict):
            return
        if isinstance(data.get("language"), str):
            set_language(data["language"])
        if data.get("theme") in ("light", "dark"):
            self.theme.set_mode(data["theme"])
        folder = data.get("download_dir")
        if isinstance(folder, str) and folder.strip():
            self._download_dir = os.path.expanduser(folder)
        try:
            saved_connections = int(data.get("connections") or DEFAULT_CONNECTIONS)
        except (TypeError, ValueError):
            saved_connections = DEFAULT_CONNECTIONS
        self._connections = max(1, min(saved_connections, MAX_CONNECTIONS))
        for entry in data.get("tasks") or []:
            if not isinstance(entry, dict):
                continue
            try:
                task = DownloadTask.from_dict(entry, callback=self._on_task_event)
            except Exception:
                continue
            if task.id in self._tasks:
                continue
            self._tasks[task.id] = task
            self._last_status[task.id] = task.status

    def _save_state(self) -> None:
        payload = {
            "version": 1,
            "theme": self.theme.mode,
            "language": get_language(),
            "download_dir": self._download_dir,
            "connections": self._connections,
            "tasks": [
                task.to_dict()
                for task in self._tasks.values()
                if task.status not in ("canceled", "canceling")
            ],
        }
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            temp_path = STATE_FILE.with_suffix(".json.tmp")
            temp_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(temp_path, STATE_FILE)
        except OSError:
            pass

    # ------------------------------------------------------------------ arayüz
    def _build_ui(self) -> None:
        if self._snackbar is not None:
            self._snackbar.hide()
        for child in list(self.winfo_children()):
            child.destroy()
        self._cards.clear()
        self._nav_items.clear()
        self._folder_nav = None
        self._scrollbar = None
        self._snackbar = None
        self._language_menu = None
        self._language_var = None
        self.configure(bg=self.theme.c("surface"))

        outer = tk.Frame(self, bg=self.theme.c("surface"))
        outer.pack(fill="both", expand=True)

        sidebar = tk.Frame(
            outer, bg=self.theme.c("surface_container_low"), width=264,
        )
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        divider = tk.Frame(
            outer, bg=self.theme.c("outline_variant"), width=1,
        )
        divider.pack(side="left", fill="y")

        content = tk.Frame(outer, bg=self.theme.c("surface"))
        content.pack(side="left", fill="both", expand=True)

        self._build_sidebar(sidebar)
        self._build_content(content)
        self._snackbar = Snackbar(self, self.theme)

    def _build_sidebar(self, parent: tk.Frame) -> None:
        theme = self.theme
        bg = theme.c("surface_container_low")
        pad = tk.Frame(parent, bg=bg)
        pad.pack(fill="both", expand=True, padx=16, pady=20)

        footer = tk.Frame(pad, bg=bg)
        footer.pack(side="bottom", fill="x")
        tk.Frame(footer, bg=theme.c("outline_variant"), height=1).pack(
            fill="x", pady=(0, 14),
        )
        tk.Label(
            footer, text=tr("app.save_folder"), bg=bg,
            fg=theme.c("on_surface_variant"), font=theme.font(8, "bold"),
            anchor="w",
        ).pack(fill="x", pady=(0, 6))
        folder_name = os.path.basename(os.path.normpath(self._download_dir)) or tr("app.downloads_folder")
        self._folder_nav = NavItem(
            footer, theme, "folder", folder_name,
            command=lambda: open_path(self._download_dir),
            bg=bg, height=42,
        )
        self._folder_nav.pack(fill="x")
        tk.Label(
            footer, text=f"{APP_NAME}  ·  v{APP_VERSION}", bg=bg,
            fg=theme.c("on_surface_variant"), font=theme.font(8, "bold"),
            anchor="w",
        ).pack(fill="x", pady=(14, 2))
        tk.Label(
            footer, text="Material 3  ·  Python & Tkinter", bg=bg,
            fg=theme.c("outline"), font=theme.font(7),
            anchor="w",
        ).pack(fill="x")
        NavItem(
            footer, theme, "info", tr("app.about"),
            command=self.open_about, bg=bg, height=36,
        ).pack(fill="x", pady=(10, 0))

        logo_row = tk.Frame(pad, bg=bg)
        logo_row.pack(side="top", fill="x")
        logo = tk.Canvas(
            logo_row, width=44, height=44, bg=bg,
            highlightthickness=0, bd=0,
        )
        rounded_rect(logo, 0, 0, 44, 44, 14, fill=theme.c("primary"), outline="")
        draw_icon(
            logo, "download", 22, 22, 24, theme.c("on_primary"),
            width=2.2, bg=theme.c("primary"),
        )
        logo.pack(side="left")
        brand = tk.Frame(logo_row, bg=bg)
        brand.pack(side="left", padx=(12, 0))
        tk.Label(
            brand, text=APP_NAME, bg=bg, fg=theme.c("on_surface"),
            font=theme.font(15, "bold"), anchor="w",
        ).pack(fill="x")
        tk.Label(
            brand, text="Internet Download Manager", bg=bg,
            fg=theme.c("on_surface_variant"), font=theme.font(8),
            anchor="w",
        ).pack(fill="x")

        tk.Label(
            pad, text=tr("app.library"), bg=bg,
            fg=theme.c("on_surface_variant"), font=theme.font(8, "bold"),
            anchor="w",
        ).pack(fill="x", pady=(28, 8))

        nav_defs = (
            ("all", "grid", tr("filter.all")),
            ("active", "download", tr("filter.active")),
            ("completed", "check", tr("filter.completed")),
            ("paused", "pause", tr("filter.nav_paused")),
        )
        for key, icon, text in nav_defs:
            item = NavItem(
                pad, theme, icon, text,
                command=lambda filter_key=key: self._set_filter(filter_key),
                bg=bg,
            )
            item.pack(fill="x", pady=1)
            item.set_selected(key == self._filter)
            self._nav_items[key] = item

        tk.Frame(pad, bg=bg).pack(fill="both", expand=True)

    def _build_content(self, parent: tk.Frame) -> None:
        theme = self.theme
        surface = theme.c("surface")

        header = tk.Frame(parent, bg=surface)
        header.pack(fill="x", padx=30, pady=(26, 10))

        titles = tk.Frame(header, bg=surface)
        titles.pack(side="left", anchor="w")
        self._title_label = tk.Label(
            titles, text=tr("filter.all"), bg=surface,
            fg=theme.c("on_surface"), font=theme.font(21, "bold"),
            anchor="w",
        )
        self._title_label.pack(fill="x")
        self._subtitle_label = tk.Label(
            titles, text="", bg=surface,
            fg=theme.c("on_surface_variant"), font=theme.font(9),
            anchor="w",
        )
        self._subtitle_label.pack(fill="x", pady=(2, 0))

        actions = tk.Frame(header, bg=surface)
        actions.pack(side="right", anchor="e")
        MaterialButton(
            actions, theme, tr("action.new_download"), icon="plus",
            command=self.open_new_download, bg=surface,
        ).pack(side="right")
        theme_icon = "moon" if theme.mode == "light" else "sun"
        theme_tip = tr("app.theme_dark") if theme.mode == "light" else tr("app.theme_light")
        IconButton(
            actions, theme, theme_icon, command=self._toggle_theme,
            bg=surface, tooltip=theme_tip,
        ).pack(side="right", padx=(0, 10))
        self._language_button = IconButton(
            actions, theme, "globe", command=self._open_language_menu,
            bg=surface, tooltip=tr("app.language"),
        )
        self._language_button.pack(side="right", padx=(0, 4))

        body = tk.Frame(parent, bg=surface)
        body.pack(fill="both", expand=True, padx=(30, 18), pady=(8, 20))

        self._list_canvas = tk.Canvas(
            body, bg=surface, highlightthickness=0, bd=0,
        )
        self._list_canvas.pack(side="left", fill="both", expand=True)
        self._scroll_frame = tk.Frame(self._list_canvas, bg=surface)
        self._list_window = self._list_canvas.create_window(
            (0, 0), window=self._scroll_frame, anchor="nw",
        )
        self._scrollbar = SlimScrollbar(
            body, theme, self._list_canvas, bg=surface,
        )
        self._scrollbar.pack(side="right", fill="y", padx=(10, 0))

        self._scroll_frame.bind("<Configure>", self._on_frame_configure)
        self._list_canvas.bind("<Configure>", self._on_list_configure)
        for sequence in ("<Button-4>", "<Button-5>", "<MouseWheel>"):
            self._list_canvas.bind(sequence, self._on_mousewheel)
            self._scrollbar.bind(sequence, self._on_mousewheel)

    # ------------------------------------------------------------------ liste
    def _on_frame_configure(self, _event=None) -> None:
        if not hasattr(self, "_list_canvas"):
            return
        self._list_canvas.configure(scrollregion=self._list_canvas.bbox("all"))
        if self._scrollbar:
            self._scrollbar.refresh()

    def _on_list_configure(self, event) -> None:
        if not hasattr(self, "_list_canvas"):
            return
        self._list_canvas.itemconfigure(self._list_window, width=event.width)
        self._scroll_frame.update_idletasks()
        self._list_canvas.configure(scrollregion=self._list_canvas.bbox("all"))
        if self._scrollbar:
            self._scrollbar.refresh()

    def _on_mousewheel(self, event) -> str:
        if not hasattr(self, "_list_canvas"):
            return "break"
        if getattr(event, "num", None) == 4:
            steps = -3
        elif getattr(event, "num", None) == 5:
            steps = 3
        else:
            delta = getattr(event, "delta", 0)
            if delta == 0:
                return "break"
            steps = -3 if delta > 0 else 3
            if abs(delta) < 120:
                steps = -1 if delta > 0 else 1
        self._list_canvas.yview_scroll(steps, "units")
        if self._scrollbar:
            self._scrollbar.refresh()
        return "break"

    def _matches_status(self, status: str | None) -> bool:
        if status is None:
            return False
        if self._filter == "all":
            return True
        if self._filter == "active":
            return status in ACTIVE_STATUSES
        if self._filter == "completed":
            return status == "completed"
        if self._filter == "paused":
            return status in ("paused", "error")
        return True

    def _render_list(self, reset_scroll: bool = False) -> None:
        if not hasattr(self, "_scroll_frame"):
            return
        try:
            position = 0.0 if reset_scroll else self._list_canvas.yview()[0]
        except tk.TclError:
            position = 0.0

        for card in self._cards.values():
            card.destroy()
        self._cards.clear()
        for child in list(self._scroll_frame.winfo_children()):
            child.destroy()

        tasks = sorted(
            self._tasks.values(), key=lambda task: task.created_at, reverse=True,
        )
        visible = [task for task in tasks if self._matches_status(task.status)]
        if visible:
            for task in visible:
                card = DownloadCard(self._scroll_frame, self, task, self.theme)
                card.pack(fill="x", pady=(0, 12), padx=(0, 2))
                self._cards[task.id] = card
        else:
            self._build_empty_state()

        self._scroll_frame.update_idletasks()
        self._list_canvas.configure(scrollregion=self._list_canvas.bbox("all"))
        self._list_canvas.yview_moveto(position)
        if self._scrollbar:
            self._scrollbar.refresh()

    def _build_empty_state(self) -> None:
        theme = self.theme
        surface = theme.c("surface")
        wrap = tk.Frame(self._scroll_frame, bg=surface)
        wrap.pack(fill="x", pady=(74, 20))

        icon_canvas = tk.Canvas(
            wrap, width=96, height=96, bg=surface,
            highlightthickness=0, bd=0,
        )
        icon_canvas.pack()
        icon_canvas.create_oval(
            2, 2, 94, 94, fill=theme.c("surface_container"), outline="",
        )
        icon_name = {
            "all": "download", "active": "download",
            "completed": "check", "paused": "pause",
        }.get(self._filter, "download")
        draw_icon(
            icon_canvas, icon_name, 48, 48, 42,
            theme.c("primary"), width=2.2, bg=theme.c("surface_container"),
        )

        messages = {
            "all": (
                tr("empty.all.title"),
                tr("empty.all.caption"),
            ),
            "active": (
                tr("empty.active.title"),
                tr("empty.active.caption"),
            ),
            "completed": (
                tr("empty.completed.title"),
                tr("empty.completed.caption"),
            ),
            "paused": (
                tr("empty.paused.title"),
                tr("empty.paused.caption"),
            ),
        }
        title, caption = messages.get(self._filter, messages["all"])
        tk.Label(
            wrap, text=title, bg=surface, fg=theme.c("on_surface"),
            font=theme.font(14, "bold"),
        ).pack(pady=(18, 4))
        tk.Label(
            wrap, text=caption, bg=surface,
            fg=theme.c("on_surface_variant"), font=theme.font(9),
            wraplength=380, justify="center",
        ).pack()
        if self._filter != "completed":
            MaterialButton(
                wrap, theme, tr("action.new_download"), icon="plus", kind="tonal",
                command=self.open_new_download, bg=surface, height=40,
            ).pack(pady=(18, 0))

        self._bind_wheel_tree(wrap)

    def _bind_wheel_tree(self, widget: tk.Widget) -> None:
        for sequence in ("<Button-4>", "<Button-5>", "<MouseWheel>"):
            widget.bind(sequence, self._on_mousewheel, add="+")
        for child in widget.winfo_children():
            self._bind_wheel_tree(child)

    # ------------------------------------------------------------------ filtre
    def _set_filter(self, key: str) -> None:
        if key not in FILTER_KEYS or key == self._filter:
            return
        self._filter = key
        for nav_key, item in self._nav_items.items():
            item.set_selected(nav_key == key)
        self._update_header()
        self._render_list(reset_scroll=True)

    # ------------------------------------------------------------------ sayaçlar
    def _update_counts(self) -> None:
        all_count = len(self._tasks)
        active = sum(1 for t in self._tasks.values() if t.status in ACTIVE_STATUSES)
        completed = sum(1 for t in self._tasks.values() if t.status == "completed")
        paused = sum(1 for t in self._tasks.values() if t.status in ("paused", "error"))
        counts = {
            "all": all_count, "active": active,
            "completed": completed, "paused": paused,
        }
        for key, item in self._nav_items.items():
            item.set_count(counts.get(key, 0))

    def _update_header(self) -> None:
        if not hasattr(self, "_title_label"):
            return
        self._title_label.configure(
            text=tr(f"filter.{self._filter}") if self._filter in FILTER_KEYS
            else tr("filter.downloads_fallback")
        )
        active = [t for t in self._tasks.values() if t.status in ACTIVE_STATUSES]
        speed = sum(max(0.0, task.speed) for task in active)
        parts: list[str] = []
        if self._filter == "all":
            parts.append(tr("subtitle.downloads", count=len(self._tasks)))
            if active:
                parts.append(tr("subtitle.active", count=len(active)))
        elif self._filter == "active":
            parts.append(tr("subtitle.active_downloads", count=len(active)))
        elif self._filter == "completed":
            count = sum(1 for t in self._tasks.values() if t.status == "completed")
            parts.append(tr("subtitle.completed_files", count=count))
        elif self._filter == "paused":
            count = sum(
                1 for t in self._tasks.values() if t.status in ("paused", "error")
            )
            parts.append(tr("subtitle.pending_downloads", count=count))
        if speed > 0:
            parts.append(tr("subtitle.total_speed", speed=format_speed(speed)))
        if not parts:
            parts.append(tr("subtitle.ready"))
        self._subtitle_label.configure(text="  ·  ".join(parts))

    # ------------------------------------------------------------------ eylemler
    def _toggle_theme(self) -> None:
        self.theme.toggle()
        self._set_window_icon()
        self._save_state()
        self._build_ui()
        self._update_counts()
        self._update_header()
        self._render_list(reset_scroll=True)

    def _set_language(self, code: str) -> None:
        if code not in LANGUAGE_NAMES or code == get_language():
            return
        set_language(code)
        self.title(tr("app.title", app=APP_NAME))
        self._save_state()
        self._build_ui()
        self._update_counts()
        self._update_header()
        self._render_list(reset_scroll=True)

    def _open_language_menu(self) -> None:
        theme = self.theme
        menu = tk.Menu(
            self,
            tearoff=0,
            bg=theme.c("surface_container_low"),
            fg=theme.c("on_surface"),
            activebackground=theme.c("primary_container"),
            activeforeground=theme.c("on_primary_container"),
            bd=0,
            relief="flat",
            font=theme.font(10),
        )
        selected = tk.StringVar(value=get_language())
        self._language_var = selected
        for code in LANGUAGE_ORDER:
            menu.add_radiobutton(
                label=LANGUAGE_NAMES[code],
                value=code,
                variable=selected,
                command=lambda language=code: self._set_language(language),
            )
        self._language_menu = menu
        x = self._language_button.winfo_rootx()
        y = (
            self._language_button.winfo_rooty()
            + self._language_button.winfo_height()
            + 4
        )
        try:
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    def open_new_download(self) -> None:
        if self._dialog is not None:
            try:
                if self._dialog.winfo_exists():
                    self._dialog.lift()
                    self._dialog.focus_force()
                    return
            except tk.TclError:
                pass
            self._dialog = None
        self._dialog = NewDownloadDialog(self)
        self._dialog.bind(
            "<Destroy>", lambda event: self._clear_dialog(event.widget),
        )

    def open_about(self) -> None:
        AboutDialog(self)

    def _clear_dialog(self, widget: tk.Widget) -> None:
        if widget is self._dialog:
            self._dialog = None

    def set_default_connections(self, connections: int) -> None:
        value = max(1, min(int(connections), MAX_CONNECTIONS))
        if value == self._connections:
            return
        self._connections = value
        self._save_state()

    def _filename_in_use(self, directory: str, filename: str, task_id: str) -> bool:
        target = os.path.normcase(os.path.abspath(os.path.join(directory, filename)))
        for other_id, other in list(self._tasks.items()):
            if other_id == task_id or not other.filename:
                continue
            if other.status == "canceled":
                continue
            other_path = os.path.normcase(
                os.path.abspath(os.path.join(other.directory, other.filename))
            )
            if other_path == target:
                return True
        return False

    def add_task(self, task: DownloadTask) -> None:
        task.callback = self._on_task_event
        task.name_in_use = self._filename_in_use
        self._tasks[task.id] = task
        self._last_status[task.id] = "queued"
        self._download_dir = task.directory
        self._connections = task.connections
        if self._folder_nav is not None:
            folder_name = os.path.basename(os.path.normpath(task.directory)) or tr("app.downloads_folder")
            self._folder_nav.set_text(folder_name)
        if self._filter in ("completed", "paused"):
            self._filter = "all"
            for nav_key, item in self._nav_items.items():
                item.set_selected(nav_key == "all")
        self._save_state()
        self._update_counts()
        self._update_header()
        self._render_list(reset_scroll=True)
        if self._snackbar:
            self._snackbar.show(
                tr("snack.started"),
                duration=3000,
            )
        task.start()

    def cancel_task(self, task_id: str) -> None:
        task = self._tasks.get(task_id)
        if task is not None:
            task.cancel()

    def remove_task(self, task_id: str) -> None:
        task = self._tasks.get(task_id)
        if task is None:
            return
        if task.status != "completed":
            task.cancel()
        self._tasks.pop(task_id, None)
        self._last_status.pop(task_id, None)
        self._save_state()
        self._update_counts()
        self._update_header()
        self._render_list()
        if self._snackbar:
            self._snackbar.show(tr("snack.removed"), duration=2600)

    # ------------------------------------------------------------------ olaylar
    def _on_task_event(self, event: dict) -> None:
        if self._closing:
            return
        try:
            self._event_queue.put_nowait(str(event.get("id", "")))
        except Exception:
            pass

    def _poll_queue(self) -> None:
        if self._closing:
            return
        seen: set[str] = set()
        while True:
            try:
                task_id = self._event_queue.get_nowait()
            except queue.Empty:
                break
            if task_id and task_id not in seen:
                seen.add(task_id)
                self._handle_task_event(task_id)
        if seen:
            self._update_counts()
            self._update_header()
        if not self._closing:
            self._poll_after_id = self.after(140, self._poll_queue)

    def _handle_task_event(self, task_id: str) -> None:
        task = self._tasks.get(task_id)
        if task is None:
            return
        previous = self._last_status.get(task_id)
        current = task.status
        card = self._cards.get(task_id)

        if previous == current:
            if card is not None:
                card.refresh()
            return

        self._last_status[task_id] = current
        self._save_state()

        if current == "canceled":
            self._tasks.pop(task_id, None)
            self._last_status.pop(task_id, None)
            self._render_list()
            if self._snackbar:
                self._snackbar.show(tr("snack.canceled"), duration=2800)
            return

        if current == "completed":
            if self._snackbar:
                directory = task.directory
                self._snackbar.show(
                    tr("snack.completed", filename=task.filename),
                    action_text=tr("action.open_folder"),
                    action=lambda: open_path(directory),
                )
        elif current == "error":
            if self._snackbar:
                task_ref = task
                self._snackbar.show(
                    tr("snack.error", error=task.error[:90]),
                    action_text=tr("action.retry"),
                    action=lambda: task_ref.resume(),
                )

        prev_matches = self._matches_status(previous)
        current_matches = self._matches_status(current)
        if prev_matches != current_matches:
            self._render_list()
        elif card is not None:
            card.refresh()

    # ------------------------------------------------------------------ kapanış
    def _on_close(self) -> None:
        if self._closing:
            return
        self._closing = True
        if self._poll_after_id:
            try:
                self.after_cancel(self._poll_after_id)
            except tk.TclError:
                pass
            self._poll_after_id = None
        if self._snackbar is not None:
            self._snackbar.hide()
        self._save_state()
        self.destroy()


def main() -> None:
    if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
        print("Grafik ekranı bulunamadı (DISPLAY değişkeni yok).")
        print("Masaüstü oturumunda veya bir X/Wayland oturumunda çalıştırın.")
        sys.exit(1)
    app = IDMApp()
    app.mainloop()

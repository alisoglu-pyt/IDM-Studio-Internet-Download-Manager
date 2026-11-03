"""Yeni indirme, ayarlar ve hakkında diyalogları."""

from __future__ import annotations

import os
import time
import tkinter as tk
import webbrowser
from tkinter import filedialog
from urllib.parse import urlparse

from . import __version__
from .downloader import KIND_CHOICES, MAX_CONNECTIONS, MAX_RETRIES, DownloadTask
from .draw import draw_icon, rounded_rect
from .i18n import tr
from .theme import Theme
from .utils import parse_schedule
from .widgets import MaterialButton, MaterialEntry, PartPicker


class NewDownloadDialog(tk.Toplevel):
    def __init__(self, app, initial_url: str = "") -> None:
        self.app = app
        self.theme: Theme = app.theme
        super().__init__(app)
        self.title(tr("dialog.new.title"))
        self.configure(bg=self.theme.c("surface"))
        self.resizable(False, False)
        self.transient(app)
        self._connections = app.default_connections
        self._kind_values: dict[str, str] = {}

        self._build()
        if initial_url:
            self.url_entry.set(initial_url)
        self.update_idletasks()
        width = max(580, self.winfo_reqwidth())
        height = self.winfo_reqheight()
        x = app.winfo_rootx() + (app.winfo_width() - width) // 2
        y = app.winfo_rooty() + (app.winfo_height() - height) // 2
        self.geometry(f"{width}x{height}+{max(0, x)}+{max(0, y)}")
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.bind("<Escape>", lambda _e: self.destroy())
        self.grab_set()
        self.url_entry.focus_entry()

    def _build(self) -> None:
        theme = self.theme
        surface = theme.c("surface")
        container = tk.Frame(self, bg=surface, padx=30, pady=22)
        container.pack(fill="both", expand=True)

        tk.Label(
            container, text=tr("dialog.new.heading"), bg=surface,
            fg=theme.c("on_surface"), font=theme.font(19, "bold"),
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            container,
            text=tr("dialog.new.subtitle"),
            bg=surface, fg=theme.c("on_surface_variant"),
            font=theme.font(9), anchor="w",
        ).pack(fill="x", pady=(3, 14))

        self.url_entry = MaterialEntry(
            container, theme, tr("dialog.new.url"), bg=surface, width=520,
        )
        self.url_entry.pack(fill="x")
        self.url_entry.on_return(self._start)

        kind_row = tk.Frame(container, bg=surface)
        kind_row.pack(fill="x", pady=(10, 0))
        tk.Label(
            kind_row, text=tr("dialog.new.kind"), bg=surface,
            fg=theme.c("on_surface_variant"), font=theme.font(9, "bold"),
            anchor="w",
        ).pack(side="left")
        self._kind_values = {
            tr("dialog.new.kind_auto"): "auto",
            tr("dialog.new.kind_http"): "http",
            tr("dialog.new.kind_ftp"): "ftp",
            tr("dialog.new.kind_hls"): "hls",
            tr("dialog.new.kind_torrent"): "torrent",
            tr("dialog.new.kind_video"): "video",
        }
        self._kind_var = tk.StringVar(value=tr("dialog.new.kind_auto"))
        kind_menu = tk.OptionMenu(
            kind_row, self._kind_var, *self._kind_values.keys(),
        )
        kind_menu.configure(
            bg=theme.c("surface_container_high"),
            fg=theme.c("on_surface"),
            activebackground=theme.c("primary_container"),
            activeforeground=theme.c("on_primary_container"),
            relief="flat", bd=0, highlightthickness=0,
            font=theme.font(9), anchor="w", padx=10, width=26,
        )
        kind_menu["menu"].configure(
            bg=theme.c("surface_container_low"),
            fg=theme.c("on_surface"),
            activebackground=theme.c("primary_container"),
            activeforeground=theme.c("on_primary_container"),
            font=theme.font(9), tearoff=0,
        )
        kind_menu.pack(side="right")

        self.name_entry = MaterialEntry(
            container, theme, tr("dialog.new.filename"), bg=surface, width=520,
        )
        self.name_entry.pack(fill="x", pady=(10, 0))
        self.name_entry.on_return(self._start)

        folder_row = tk.Frame(container, bg=surface)
        folder_row.pack(fill="x", pady=(10, 0))
        folder_row.columnconfigure(0, weight=1)
        self.dir_entry = MaterialEntry(
            folder_row, theme, tr("dialog.new.folder"), bg=surface, width=410,
        )
        self.dir_entry.set(self.app.download_dir)
        self.dir_entry.grid(row=0, column=0, sticky="ew")
        browse = MaterialButton(
            folder_row, theme, tr("action.browse"), icon="folder", kind="tonal",
            height=42, command=self._browse, bg=surface,
        )
        browse.grid(row=0, column=1, sticky="s", padx=(10, 0), pady=(20, 0))

        parts_header = tk.Frame(container, bg=surface)
        parts_header.pack(fill="x", pady=(12, 0))
        tk.Label(
            parts_header, text=tr("dialog.new.parts"), bg=surface,
            fg=theme.c("on_surface"), font=theme.font(10, "bold"),
            anchor="w",
        ).pack(side="left")
        self._parts_value = tk.Label(
            parts_header,
            text=f"{self._connections} / {MAX_CONNECTIONS}",
            bg=surface, fg=theme.c("primary"),
            font=theme.font(10, "bold"), anchor="e",
        )
        self._parts_value.pack(side="right")
        tk.Label(
            container,
            text=tr("dialog.new.parts_hint"),
            bg=surface, fg=theme.c("on_surface_variant"),
            font=theme.font(8), anchor="w", justify="left",
            wraplength=520,
        ).pack(fill="x", pady=(2, 0))

        self.parts_picker = PartPicker(
            container, theme, value=self._connections,
            maximum=MAX_CONNECTIONS, command=self._on_parts_change, bg=surface,
        )
        self.parts_picker.pack(fill="x", pady=(8, 0))

        options_row = tk.Frame(container, bg=surface)
        options_row.pack(fill="x", pady=(10, 0))
        options_row.columnconfigure(0, weight=1)
        options_row.columnconfigure(1, weight=1)
        self.retry_entry = MaterialEntry(
            options_row, theme, tr("dialog.new.retries"), bg=surface, width=250,
        )
        self.retry_entry.set(str(self.app.default_retries))
        self.retry_entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.retry_entry.on_return(self._start)
        self.schedule_entry = MaterialEntry(
            options_row, theme, tr("dialog.new.schedule"), bg=surface, width=250,
        )
        self.schedule_entry.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        self.schedule_entry.on_return(self._start)
        tk.Label(
            container,
            text=f"{tr('dialog.new.retries_hint')}  ·  {tr('dialog.new.schedule_hint')}",
            bg=surface, fg=theme.c("on_surface_variant"),
            font=theme.font(8), anchor="w", justify="left", wraplength=520,
        ).pack(fill="x", pady=(2, 0))

        self.error_label = tk.Label(
            container, text="", bg=surface, fg=theme.c("error"),
            font=theme.font(9), anchor="w", justify="left",
            wraplength=520, height=2,
        )
        self.error_label.pack(fill="x", pady=(4, 0))

        actions = tk.Frame(container, bg=surface)
        actions.pack(fill="x", pady=(6, 0))
        MaterialButton(
            actions, theme, tr("action.start_download"), icon="download",
            command=self._start, bg=surface,
        ).pack(side="right")
        MaterialButton(
            actions, theme, tr("action.cancel_changes"), kind="text",
            command=self.destroy, bg=surface,
        ).pack(side="right", padx=(0, 8))

        for entry in (
            self.url_entry, self.name_entry, self.dir_entry,
            self.retry_entry, self.schedule_entry,
        ):
            entry.var.trace_add("write", lambda *_args: self._clear_error())

    def _on_parts_change(self, value: int) -> None:
        self._connections = value
        self._parts_value.configure(text=f"{value} / {MAX_CONNECTIONS}")
        self.app.set_default_connections(value)

    def _browse(self) -> None:
        initial = self.dir_entry.get() or self.app.download_dir
        chosen = filedialog.askdirectory(
            parent=self, title=tr("dialog.new.choose_folder"), initialdir=initial,
        )
        if chosen:
            self.dir_entry.set(chosen)
            self._clear_error()

    def _clear_error(self) -> None:
        self.error_label.configure(text="")
        self.url_entry.set_invalid(False)
        self.dir_entry.set_invalid(False)
        self.retry_entry.set_invalid(False)
        self.schedule_entry.set_invalid(False)

    def _show_error(self, message: str, field: str = "") -> None:
        self.error_label.configure(text=message)
        mapping = {
            "url": self.url_entry,
            "dir": self.dir_entry,
            "retry": self.retry_entry,
            "schedule": self.schedule_entry,
        }
        entry = mapping.get(field)
        if entry is not None:
            entry.set_invalid(True)
            entry.focus_entry()

    def _start(self) -> None:
        raw_url = self.url_entry.get()
        if not raw_url:
            self._show_error(tr("error.url_required"), "url")
            return
        url = raw_url
        if url.lower().startswith("magnet:"):
            self._show_error(tr("error.torrent_magnet"), "url")
            return
        if os.path.isfile(url) and url.lower().endswith(".torrent"):
            url = os.path.abspath(os.path.expanduser(url))
        else:
            if "://" not in url:
                url = "https://" + url
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https", "ftp", "ftps") or not parsed.netloc:
                self._show_error(tr("error.url_invalid"), "url")
                return

        try:
            retries = int(self.retry_entry.get() or "0")
        except ValueError:
            self._show_error(tr("error.retries_invalid"), "retry")
            return
        if retries < 0 or retries > MAX_RETRIES:
            self._show_error(tr("error.retries_invalid"), "retry")
            return

        schedule_text = self.schedule_entry.get()
        scheduled_at = 0.0
        if schedule_text:
            scheduled_at = parse_schedule(schedule_text)
            if scheduled_at <= 0:
                self._show_error(tr("error.schedule_invalid"), "schedule")
                return
            if scheduled_at <= time.time() + 1:
                self._show_error(tr("error.schedule_past"), "schedule")
                return

        directory = os.path.abspath(os.path.expanduser(
            self.dir_entry.get() or self.app.download_dir
        ))
        try:
            os.makedirs(directory, exist_ok=True)
        except OSError as exc:
            self._show_error(tr("error.folder_create", error=exc), "dir")
            return
        if not os.path.isdir(directory):
            self._show_error(tr("error.folder_not_dir"), "dir")
            return

        kind = self._kind_values.get(self._kind_var.get(), "auto")
        if kind not in KIND_CHOICES:
            kind = "auto"

        task = DownloadTask(
            url=url,
            directory=directory,
            filename=self.name_entry.get(),
            connections=self.parts_picker.get(),
            callback=self.app._on_task_event,
            kind=kind,
            scheduled_at=scheduled_at,
            auto_retry=retries > 0,
            max_retries=retries,
        )
        self.app.set_default_retries(retries)
        self.app.add_task(task)
        self.destroy()


class SettingsDialog(tk.Toplevel):
    """Panodan yakalama, tepsi ve otomatik yeniden deneme ayarları."""

    def __init__(self, app) -> None:
        self.app = app
        self.theme: Theme = app.theme
        super().__init__(app)
        self.title(tr("settings.title"))
        self.configure(bg=self.theme.c("surface"))
        self.resizable(False, False)
        self.transient(app)

        self._build()
        self.update_idletasks()
        width = max(520, self.winfo_reqwidth())
        height = self.winfo_reqheight()
        x = app.winfo_rootx() + (app.winfo_width() - width) // 2
        y = app.winfo_rooty() + (app.winfo_height() - height) // 2
        self.geometry(f"{width}x{height}+{max(0, x)}+{max(0, y)}")
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.bind("<Escape>", lambda _e: self.destroy())
        self.grab_set()

    def _build(self) -> None:
        theme = self.theme
        surface = theme.c("surface")
        container = tk.Frame(self, bg=surface, padx=30, pady=24)
        container.pack(fill="both", expand=True)

        tk.Label(
            container, text=tr("settings.heading"), bg=surface,
            fg=theme.c("on_surface"), font=theme.font(19, "bold"), anchor="w",
        ).pack(fill="x", pady=(0, 14))

        self._clipboard_var = tk.BooleanVar(value=self.app.clipboard_watch)
        self._clipboard_check = self._checkbutton(
            container, tr("settings.clipboard"), self._clipboard_var,
        )
        self._clipboard_check.pack(fill="x")
        self._hint(container, tr("settings.clipboard_hint"))

        self._tray_var = tk.BooleanVar(value=self.app.close_to_tray)
        self._tray_check = self._checkbutton(
            container, tr("settings.tray"), self._tray_var,
        )
        self._tray_check.pack(fill="x", pady=(12, 0))
        self._hint(container, tr("settings.tray_hint"))

        tk.Label(
            container, text=tr("settings.retry"), bg=surface,
            fg=theme.c("on_surface"), font=theme.font(10, "bold"), anchor="w",
        ).pack(fill="x", pady=(16, 0))
        self.retry_entry = MaterialEntry(
            container, theme, tr("dialog.new.retries"), bg=surface, width=460,
        )
        self.retry_entry.set(str(self.app.default_retries))
        self.retry_entry.pack(fill="x", pady=(6, 0))
        self._hint(container, tr("settings.retry_hint"))

        actions = tk.Frame(container, bg=surface)
        actions.pack(fill="x", pady=(18, 0))
        MaterialButton(
            actions, theme, tr("action.close"), icon="check",
            command=self._save, bg=surface,
        ).pack(side="right")
        MaterialButton(
            actions, theme, tr("action.cancel_changes"), kind="text",
            command=self.destroy, bg=surface,
        ).pack(side="right", padx=(0, 8))

    def _checkbutton(self, parent, text: str, variable: tk.BooleanVar) -> tk.Checkbutton:
        theme = self.theme
        return tk.Checkbutton(
            parent, text=text, variable=variable, bg=theme.c("surface"),
            fg=theme.c("on_surface"), activebackground=theme.c("surface"),
            activeforeground=theme.c("on_surface"),
            selectcolor=theme.c("surface_container_high"),
            font=theme.font(10), anchor="w", bd=0,
            highlightthickness=0, padx=0, pady=2,
        )

    def _hint(self, parent, text: str) -> None:
        tk.Label(
            parent, text=text, bg=self.theme.c("surface"),
            fg=self.theme.c("on_surface_variant"), font=self.theme.font(8),
            anchor="w", justify="left", wraplength=460,
        ).pack(fill="x", padx=(28, 0))

    def _save(self) -> None:
        try:
            retries = int(self.retry_entry.get() or "0")
        except ValueError:
            retries = self.app.default_retries
        retries = max(0, min(retries, MAX_RETRIES))
        self.app.apply_settings(
            clipboard=self._clipboard_var.get(),
            close_to_tray=self._tray_var.get(),
            retries=retries,
        )
        self.destroy()


class AboutDialog(tk.Toplevel):
    """Uygulama, sürüm ve geliştirici bilgilerini gösteren pencere."""

    PROGRAMMER = "Bekir Alişoğlu"
    EMAIL = "alisoglu@yahoo.com"

    def __init__(self, app) -> None:
        self.app = app
        self.theme: Theme = app.theme
        super().__init__(app)
        self.title(tr("about.title"))
        self.configure(bg=self.theme.c("surface"))
        self.resizable(False, False)
        self.transient(app)

        self._build()
        self.update_idletasks()
        width = max(460, self.winfo_reqwidth())
        height = self.winfo_reqheight()
        x = app.winfo_rootx() + (app.winfo_width() - width) // 2
        y = app.winfo_rooty() + (app.winfo_height() - height) // 2
        self.geometry(f"{width}x{height}+{max(0, x)}+{max(0, y)}")
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.bind("<Escape>", lambda _e: self.destroy())
        self.grab_set()
        self.focus_set()

    def _build(self) -> None:
        theme = self.theme
        surface = theme.c("surface")
        container = tk.Frame(self, bg=surface, padx=32, pady=28)
        container.pack(fill="both", expand=True)

        header = tk.Frame(container, bg=surface)
        header.pack(fill="x")
        logo = tk.Canvas(
            header, width=64, height=64, bg=surface,
            highlightthickness=0, bd=0,
        )
        rounded_rect(
            logo, 0, 0, 64, 64, 20,
            fill=theme.c("primary"), outline="",
        )
        draw_icon(
            logo, "download", 32, 32, 34, theme.c("on_primary"),
            width=2.6, bg=theme.c("primary"),
        )
        logo.pack(side="left")

        titles = tk.Frame(header, bg=surface)
        titles.pack(side="left", padx=(18, 0))
        tk.Label(
            titles, text="IDM Studio", bg=surface,
            fg=theme.c("on_surface"), font=theme.font(21, "bold"),
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            titles,
            text=f"Internet Download Manager  ·  v{__version__}",
            bg=surface, fg=theme.c("on_surface_variant"),
            font=theme.font(9), anchor="w",
        ).pack(fill="x", pady=(2, 0))

        tk.Frame(
            container, bg=theme.c("outline_variant"), height=1,
        ).pack(fill="x", pady=(22, 18))

        tk.Label(
            container,
            text=tr("about.description"),
            bg=surface, fg=theme.c("on_surface_variant"),
            font=theme.font(9), anchor="w", justify="left",
            wraplength=400,
        ).pack(fill="x")

        card_bg = theme.c("surface_container_low")
        card = tk.Frame(container, bg=card_bg, padx=18, pady=14)
        card.pack(fill="x", pady=(18, 0))
        tk.Label(
            card, text=tr("about.programmer"), bg=card_bg,
            fg=theme.c("on_surface_variant"), font=theme.font(8, "bold"),
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            card, text=self.PROGRAMMER, bg=card_bg,
            fg=theme.c("on_surface"), font=theme.font(12, "bold"),
            anchor="w",
        ).pack(fill="x", pady=(4, 0))
        email = tk.Label(
            card, text=self.EMAIL, bg=card_bg,
            fg=theme.c("primary"), font=theme.font(9),
            anchor="w", cursor="hand2",
        )
        email.pack(fill="x", pady=(2, 0))
        email.bind("<Button-1>", lambda _e: self._open_email())

        meta = tk.Frame(container, bg=surface)
        meta.pack(fill="x", pady=(16, 0))
        tk.Label(
            meta, text=tr("about.license"), bg=surface,
            fg=theme.c("on_surface_variant"), font=theme.font(8),
        ).pack(side="left")
        tk.Label(
            meta, text=tr("about.tech"), bg=surface,
            fg=theme.c("on_surface_variant"), font=theme.font(8),
        ).pack(side="right")

        actions = tk.Frame(container, bg=surface)
        actions.pack(fill="x", pady=(22, 0))
        MaterialButton(
            actions, theme, tr("action.close"), kind="tonal",
            command=self.destroy, bg=surface,
        ).pack(side="right")

    def _open_email(self) -> None:
        try:
            webbrowser.open(f"mailto:{self.EMAIL}")
        except Exception:
            pass

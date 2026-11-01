"""Yeni indirme ve hakkında diyalogları."""

from __future__ import annotations

import os
import tkinter as tk
import webbrowser
from tkinter import filedialog
from urllib.parse import urlparse

from . import __version__
from .downloader import MAX_CONNECTIONS, DownloadTask
from .draw import draw_icon, rounded_rect
from .i18n import tr
from .theme import Theme
from .widgets import MaterialButton, MaterialEntry, PartPicker


class NewDownloadDialog(tk.Toplevel):
    def __init__(self, app) -> None:
        self.app = app
        self.theme: Theme = app.theme
        super().__init__(app)
        self.title(tr("dialog.new.title"))
        self.configure(bg=self.theme.c("surface"))
        self.resizable(False, False)
        self.transient(app)
        self._connections = app.default_connections

        self._build()
        self.update_idletasks()
        width = max(560, self.winfo_reqwidth())
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
        container = tk.Frame(self, bg=surface, padx=30, pady=26)
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
        ).pack(fill="x", pady=(3, 18))

        self.url_entry = MaterialEntry(
            container, theme, tr("dialog.new.url"), bg=surface, width=500,
        )
        self.url_entry.pack(fill="x")
        self.url_entry.on_return(self._start)

        self.name_entry = MaterialEntry(
            container, theme, tr("dialog.new.filename"), bg=surface, width=500,
        )
        self.name_entry.pack(fill="x", pady=(14, 0))
        self.name_entry.on_return(self._start)

        folder_row = tk.Frame(container, bg=surface)
        folder_row.pack(fill="x", pady=(14, 0))
        folder_row.columnconfigure(0, weight=1)
        self.dir_entry = MaterialEntry(
            folder_row, theme, tr("dialog.new.folder"), bg=surface, width=390,
        )
        self.dir_entry.set(self.app.download_dir)
        self.dir_entry.grid(row=0, column=0, sticky="ew")
        browse = MaterialButton(
            folder_row, theme, tr("action.browse"), icon="folder", kind="tonal",
            height=42, command=self._browse, bg=surface,
        )
        browse.grid(row=0, column=1, sticky="s", padx=(10, 0), pady=(20, 0))

        parts_header = tk.Frame(container, bg=surface)
        parts_header.pack(fill="x", pady=(18, 0))
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
            wraplength=500,
        ).pack(fill="x", pady=(2, 0))

        self.parts_picker = PartPicker(
            container, theme, value=self._connections,
            maximum=MAX_CONNECTIONS, command=self._on_parts_change, bg=surface,
        )
        self.parts_picker.pack(fill="x", pady=(10, 0))

        self.error_label = tk.Label(
            container, text="", bg=surface, fg=theme.c("error"),
            font=theme.font(9), anchor="w", justify="left",
            wraplength=500, height=2,
        )
        self.error_label.pack(fill="x", pady=(8, 0))

        actions = tk.Frame(container, bg=surface)
        actions.pack(fill="x", pady=(10, 0))
        MaterialButton(
            actions, theme, tr("action.start_download"), icon="download",
            command=self._start, bg=surface,
        ).pack(side="right")
        MaterialButton(
            actions, theme, tr("action.cancel_changes"), kind="text",
            command=self.destroy, bg=surface,
        ).pack(side="right", padx=(0, 8))

        for entry in (self.url_entry, self.name_entry, self.dir_entry):
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

    def _show_error(self, message: str, field: str = "") -> None:
        self.error_label.configure(text=message)
        if field == "url":
            self.url_entry.set_invalid(True)
            self.url_entry.focus_entry()
        elif field == "dir":
            self.dir_entry.set_invalid(True)
            self.dir_entry.focus_entry()

    def _start(self) -> None:
        raw_url = self.url_entry.get()
        if not raw_url:
            self._show_error(tr("error.url_required"), "url")
            return
        url = raw_url
        if "://" not in url:
            url = "https://" + url
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            self._show_error(tr("error.url_invalid"), "url")
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

        task = DownloadTask(
            url=url,
            directory=directory,
            filename=self.name_entry.get(),
            connections=self.parts_picker.get(),
            callback=self.app._on_task_event,
        )
        self.app.add_task(task)
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

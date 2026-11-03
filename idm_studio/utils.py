"""Projede paylaşılan küçük yardımcı fonksiyonlar."""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

from .i18n import month_names, tr


def format_size(size: float | int | None) -> str:
    if not size or size < 0:
        return "0 B"
    size = float(size)
    units = ("B", "KB", "MB", "GB", "TB")
    index = 0
    while size >= 1024 and index < len(units) - 1:
        size /= 1024
        index += 1
    if index == 0:
        return f"{int(size)} B"
    text = f"{size:.1f}".replace(".", tr("number.decimal"))
    return f"{text} {units[index]}"


def format_speed(size: float | None) -> str:
    if not size or size <= 0:
        return tr("speed.per_second", size="0 B")
    return tr("speed.per_second", size=format_size(size))


def format_eta(seconds: float | None) -> str:
    if seconds is None or seconds <= 0 or seconds > 7 * 24 * 3600:
        return ""
    seconds = int(seconds)
    if seconds < 60:
        return tr("time.second", n=max(1, seconds))
    minutes = seconds // 60
    if minutes < 60:
        return tr("time.minute", n=minutes)
    hours = minutes // 60
    minutes %= 60
    if hours < 24:
        if minutes:
            return tr("time.hours_minutes", h=hours, m=minutes)
        return tr("time.hours", n=hours)
    days = hours // 24
    return tr("time.day", n=days)


def percentage(part: float, total: float) -> int:
    if not total:
        return 0
    return max(0, min(100, int(part * 100 / total)))


def format_when(timestamp: float | None) -> str:
    if not timestamp:
        return ""
    moment = datetime.fromtimestamp(timestamp)
    now = datetime.now()
    if moment.date() == now.date():
        return moment.strftime("%H:%M")
    months = month_names()
    month = months[moment.month - 1]
    if moment.year == now.year:
        return tr(
            "date.same_year",
            day=moment.day,
            month=month,
            time=moment.strftime("%H:%M"),
        )
    return tr(
        "date.other_year",
        day=moment.day,
        month=month,
        year=moment.year,
    )


def ellipsize(text: str, font, max_width: int) -> str:
    if max_width <= 0:
        return ""
    if font.measure(text) <= max_width:
        return text
    ellipsis = "…"
    cut = text
    while cut and font.measure(cut + ellipsis) > max_width:
        cut = cut[:-1]
    return cut.rstrip() + ellipsis if cut else ellipsis


def default_download_dir() -> str:
    """XDG ayarlarını, ardından yaygın klasör adlarını dener."""
    config = Path.home() / ".config" / "user-dirs.dirs"
    try:
        for line in config.read_text(encoding="utf-8").splitlines():
            if line.startswith("XDG_DOWNLOAD_DIR="):
                raw = line.split("=", 1)[1].strip().strip('"')
                raw = raw.replace("$HOME", str(Path.home()))
                candidate = Path(os.path.expandvars(raw)).expanduser()
                if candidate.is_dir():
                    return str(candidate)
    except OSError:
        pass

    for name in ("Downloads", "İndirilenler", "Indirilenler"):
        candidate = Path.home() / name
        if candidate.is_dir():
            return str(candidate)

    fallback = Path.home() / "Downloads"
    try:
        fallback.mkdir(parents=True, exist_ok=True)
    except OSError:
        fallback = Path.home()
    return str(fallback)


def open_path(path: str) -> None:
    """Bir dosya veya klasörü işletim sisteminin varsayılan uygulamasıyla açar."""
    if not path or not os.path.exists(path):
        return
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(
                ["xdg-open", path],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
    except (OSError, AttributeError):
        pass


def shorten_path(path: str, max_length: int = 42) -> str:
    if len(path) <= max_length:
        return path
    home = str(Path.home())
    if path.startswith(home):
        path = "~" + path[len(home):]
    if len(path) <= max_length:
        return path
    head = max_length // 2 - 1
    tail = max_length - head - 1
    return f"{path[:head]}…{path[-tail:]}"


def parse_schedule(text: str) -> float:
    """Kullanıcının girdiği zamanı epoch saniyesine çevirir.

    Desteklenen biçimler: ``YYYY-AA-GG SS:DD``, ``GG.AA.YYYY SS:DD``,
    ``GG/AA/YYYY SS:DD`` ve yalnızca ``SS:DD`` (bugün veya yarın).
    Geçersiz girdide ``0.0`` döner.
    """
    text = (text or "").strip()
    if not text:
        return 0.0
    now = datetime.now()
    for pattern in (
        "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S",
        "%d.%m.%Y %H:%M", "%d.%m.%Y %H:%M:%S",
        "%d/%m/%Y %H:%M", "%d/%m/%Y %H:%M:%S",
    ):
        try:
            return datetime.strptime(text, pattern).timestamp()
        except ValueError:
            continue
    try:
        clock = datetime.strptime(text, "%H:%M")
    except ValueError:
        return 0.0
    candidate = now.replace(
        hour=clock.hour, minute=clock.minute, second=0, microsecond=0,
    )
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate.timestamp()


def format_schedule(timestamp: float) -> str:
    if not timestamp:
        return ""
    try:
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")
    except (OSError, OverflowError, ValueError):
        return ""


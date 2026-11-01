"""Çok bağlantılı, duraklatılabilir indirme motoru.

Harici paket gerektirmez; yalnızca Python standart kütüphanesini kullanır.
İndirmeler parçalara (segmentlere) ayrılır, her parça ayrı bir iş parçacığında
indirilir ve tamamlandığında tek bir dosyada birleştirilir.
"""

from __future__ import annotations

import glob
import http.client
import mimetypes
import os
import re
import shutil
import threading
import time
import uuid
from email.message import Message
from typing import Callable, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

from .i18n import tr

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 IDMStudio/1.0"
)
CHUNK_SIZE = 256 * 1024
MIN_MULTI_PART_SIZE = 1024 * 1024
DEFAULT_CONNECTIONS = 4
MAX_CONNECTIONS = 10

ACTIVE_STATUSES = frozenset({
    "queued", "connecting", "downloading", "pausing", "merging", "canceling",
})
PAUSABLE_STATUSES = frozenset({"connecting", "downloading"})
FINISHED_STATUSES = frozenset({"completed", "canceled"})

_BAD_FILENAME = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')
_CONTENT_RANGE = re.compile(r"bytes\s+(\d+)-(\d+)/(\d+|\*)")
_FILENAME_LOCK = threading.Lock()


class DownloadError(Exception):
    """Kullanıcıya gösterilebilecek indirme hatası."""


class _MergeCancelled(Exception):
    pass


def _to_int(value: Optional[str]) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _friendly_error(exc: BaseException) -> str:
    if isinstance(exc, HTTPError):
        return tr("error.server_response", code=exc.code)
    if isinstance(exc, URLError):
        reason = getattr(exc, "reason", exc)
        return tr("error.connection_failed", reason=reason)
    if isinstance(exc, TimeoutError):
        return tr("error.timeout")
    if isinstance(exc, OSError):
        return tr("error.file_operation", error=exc.strerror or exc)
    return tr("error.unexpected", error=exc)


def sanitize_filename(name: str, fallback: str | None = None) -> str:
    fallback = fallback or tr("file.default_name")
    name = unquote(name or "").replace("\r", " ").replace("\n", " ").strip()
    name = _BAD_FILENAME.sub("_", name).strip(" .")
    if not name:
        name = fallback
    if len(name) > 180:
        root, ext = os.path.splitext(name)
        name = root[: max(1, 180 - len(ext))] + ext
    return name


def filename_from_disposition(value: Optional[str]) -> str:
    if not value:
        return ""
    try:
        message = Message()
        message["content-disposition"] = value
        return (message.get_filename() or "").strip()
    except (ValueError, TypeError):
        return ""


def filename_from_url(url: str) -> str:
    path = unquote(urlparse(url).path or "")
    path = path.rstrip("/")
    if not path:
        return ""
    name = os.path.basename(path)
    return sanitize_filename(name) if name else ""


def _compute_ranges(total: int, connections: int) -> list[tuple[int, Optional[int]]]:
    if total <= 0:
        return [(0, None)]
    if total >= MIN_MULTI_PART_SIZE and connections > 1:
        parts = min(connections, max(1, total // (512 * 1024)), MAX_CONNECTIONS)
        if parts > 1:
            chunk = total // parts
            ranges: list[tuple[int, Optional[int]]] = []
            start = 0
            for index in range(parts):
                end = total - 1 if index == parts - 1 else start + chunk - 1
                ranges.append((start, end))
                start = end + 1
            return ranges
    return [(0, total - 1)]


class DownloadTask:
    """Tek bir indirmeyi temsil eder; UI'dan bağımsızdır."""

    def __init__(
        self,
        url: str,
        directory: str,
        filename: str = "",
        connections: int = DEFAULT_CONNECTIONS,
        callback: Optional[Callable[[dict], None]] = None,
        task_id: Optional[str] = None,
    ) -> None:
        self.id = task_id or uuid.uuid4().hex[:12]
        self.url = url.strip()
        self.directory = os.path.abspath(os.path.expanduser(directory))
        self.requested_filename = (filename or "").strip()
        self.connections = max(
            1, min(int(connections or DEFAULT_CONNECTIONS), MAX_CONNECTIONS),
        )
        self.callback = callback
        self.created_at = time.time()
        self.completed_at = 0.0

        self.status = "queued"
        self.filename = ""
        self.total = 0
        self.error = ""
        self.speed = 0.0
        self.segment_ranges: list[tuple[int, Optional[int]]] = []
        self.segment_downloaded: list[int] = []
        self.segment_errors: list[str] = []
        self.resolved_url = self.url
        self.content_type = ""
        self.name_in_use: Optional[Callable[[str, str, str], bool]] = None

        self._prepared = False
        self._name_finalized = False
        self._cancel = threading.Event()
        self._pause = threading.Event()
        self._threads: list[threading.Thread] = []
        self._controller: Optional[threading.Thread] = None
        self._lock = threading.RLock()
        self._last_emit = 0.0
        self._last_speed_time = 0.0
        self._last_speed_bytes = 0
        if self.requested_filename:
            self.filename = sanitize_filename(self.requested_filename)

    # ------------------------------------------------------------------ durum
    @property
    def target_path(self) -> str:
        return os.path.join(self.directory, self.filename) if self.filename else ""

    @property
    def downloaded(self) -> int:
        if self.status == "completed":
            return self.total
        with self._lock:
            return sum(self.segment_downloaded)

    @property
    def progress(self) -> float:
        if self.total <= 0:
            return 0.0
        return max(0.0, min(1.0, self.downloaded / self.total))

    @property
    def eta(self) -> Optional[float]:
        if self.status != "downloading" or self.total <= 0 or self.speed <= 1:
            return None
        return max(0.0, (self.total - self.downloaded) / self.speed)

    @property
    def is_busy(self) -> bool:
        if self._controller and self._controller.is_alive():
            return True
        return any(thread.is_alive() for thread in self._threads)

    # ------------------------------------------------------------------ kayıt
    def to_dict(self) -> dict:
        status = self.status
        if status in ACTIVE_STATUSES or status == "canceled":
            status = "paused" if status != "canceled" else "canceled"
        return {
            "id": self.id,
            "url": self.url,
            "directory": self.directory,
            "filename": self.filename,
            "requested_filename": self.requested_filename,
            "connections": self.connections,
            "total": self.total,
            "ranges": [[start, end] for start, end in self.segment_ranges],
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "status": status,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict,
                  callback: Optional[Callable[[dict], None]] = None) -> "DownloadTask":
        task = cls(
            url=str(data.get("url", "")),
            directory=str(data.get("directory") or os.path.expanduser("~")),
            filename=str(data.get("filename") or data.get("requested_filename") or ""),
            connections=int(data.get("connections") or DEFAULT_CONNECTIONS),
            callback=callback,
            task_id=str(data.get("id") or uuid.uuid4().hex[:12]),
        )
        task.requested_filename = str(data.get("requested_filename") or task.requested_filename)
        task.filename = sanitize_filename(
            str(data.get("filename") or task.requested_filename or ""),
        ) if (data.get("filename") or task.requested_filename) else ""
        task._name_finalized = bool(task.filename)
        task.total = _to_int(str(data.get("total") or 0))
        task.created_at = float(data.get("created_at") or time.time())
        task.completed_at = float(data.get("completed_at") or 0)
        task.error = str(data.get("error") or "")

        ranges: list[tuple[int, Optional[int]]] = []
        for entry in data.get("ranges") or []:
            try:
                start = int(entry[0])
                end = None if entry[1] is None else int(entry[1])
                ranges.append((start, end))
            except (TypeError, ValueError, IndexError):
                continue
        task.segment_ranges = ranges
        task.segment_errors = [""] * len(ranges)
        task._refresh_segment_progress()

        saved_status = str(data.get("status") or "paused")
        if saved_status == "completed" and task.target_path and os.path.exists(task.target_path):
            size = os.path.getsize(task.target_path)
            if task.total <= 0 or size == task.total:
                task.status = "completed"
                task.completed_at = task.completed_at or os.path.getmtime(task.target_path)
                task._prepared = True
                task._cleanup_parts()
                return task
        if saved_status == "completed":
            saved_status = "paused"

        # Tamamlanmış ama durumu kaydedilememiş indirmeleri kurtar.
        if (saved_status != "completed" and task.target_path and task.total > 0
                and os.path.exists(task.target_path)
                and os.path.getsize(task.target_path) == task.total):
            task.status = "completed"
            task.completed_at = task.completed_at or os.path.getmtime(task.target_path)
            task._prepared = True
            task._cleanup_parts()
            return task

        task.status = "error" if saved_status == "error" else "paused"
        task._prepared = False
        if task.status != "error":
            task.error = ""
        return task

    # ------------------------------------------------------------------ genel
    def _emit(self, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_emit < 0.18:
            return
        self._last_emit = now
        if self.callback:
            try:
                self.callback({"type": "task", "id": self.id})
            except Exception:
                pass

    def _set_status(self, status: str, force: bool = True) -> None:
        with self._lock:
            self.status = status
        self._emit(force)

    def _part_path(self, index: int) -> str:
        return os.path.join(self.directory, f".idm-{self.id}.part{index}")

    def _cleanup_parts(self) -> None:
        patterns = (
            os.path.join(self.directory, f".idm-{self.id}.part*"),
            os.path.join(self.directory, f".idm-{self.id}.merged"),
        )
        for pattern in patterns:
            for path in glob.glob(pattern):
                try:
                    os.remove(path)
                except OSError:
                    pass

    def _refresh_segment_progress(self) -> None:
        values: list[int] = []
        for index, (start, end) in enumerate(self.segment_ranges):
            path = self._part_path(index)
            try:
                size = os.path.getsize(path) if os.path.exists(path) else 0
            except OSError:
                size = 0
            if end is not None:
                size = min(size, max(0, end - start + 1))
            values.append(size)
        with self._lock:
            self.segment_downloaded = values

    def _unique_filename(self, name: str) -> str:
        name = sanitize_filename(name)
        candidate = name
        root, ext = os.path.splitext(name)
        counter = 1
        while self._is_name_taken(candidate):
            candidate = f"{root} ({counter}){ext}"
            counter += 1
        return candidate

    def _is_name_taken(self, name: str) -> bool:
        if os.path.exists(os.path.join(self.directory, name)):
            return True
        if self.name_in_use is not None:
            try:
                return bool(self.name_in_use(self.directory, name, self.id))
            except Exception:
                return False
        return False

    # --------------------------------------------------------------- başlatma
    def start(self) -> None:
        with self._lock:
            if self.status in ("downloading", "connecting", "pausing",
                               "merging", "canceling", "completed", "canceled"):
                return
            if self._controller and self._controller.is_alive():
                return
            self._pause.clear()
            self._cancel.clear()
            self.error = ""
            self.speed = 0.0
            self.segment_errors = [""] * len(self.segment_ranges)
            self.status = "downloading" if self._prepared else "connecting"
            self._last_speed_time = 0.0
            self._last_speed_bytes = self.downloaded
        self._emit(True)
        self._controller = threading.Thread(
            target=self._run, name=f"idm-{self.id}", daemon=True,
        )
        self._controller.start()

    def resume(self) -> None:
        with self._lock:
            status = self.status
        # Duraklatma tamamlanmadan devam ettirmek yarış koşullarına yol açar;
        # kısa bir an sonra "paused" durumuna geçilecektir.
        if status not in ("paused", "error"):
            return
        self.start()

    def pause(self) -> None:
        with self._lock:
            if self.status not in PAUSABLE_STATUSES:
                return
            self._pause.set()
            self.status = "pausing"
        self._emit(True)

    def cancel(self) -> None:
        with self._lock:
            if self.status in ("completed", "canceled"):
                return
            self._cancel.set()
            self._pause.clear()
            busy = self.is_busy
            if not busy:
                self.status = "canceled"
                self.speed = 0.0
            else:
                self.status = "canceling"
        if not busy:
            self._cleanup_parts()
        self._emit(True)

    # ------------------------------------------------------------------ motor
    def _run(self) -> None:
        try:
            if not self._prepared:
                self._prepare()
            if self._cancel.is_set():
                self._cleanup_parts()
                self._set_status("canceled")
                return
            if self._pause.is_set():
                self.speed = 0.0
                self._set_status("paused")
                return
            with self._lock:
                self.status = "downloading"
            self._emit(True)
            self._spawn_segments()
            self._monitor()
        except DownloadError as exc:
            if self._cancel.is_set():
                self._cleanup_parts()
                self._set_status("canceled")
                return
            with self._lock:
                self.error = str(exc)
                self.speed = 0.0
            self._set_status("error")
        except Exception as exc:  # motor asla sessizce ölmemeli
            if self._cancel.is_set():
                self._cleanup_parts()
                self._set_status("canceled")
                return
            with self._lock:
                self.error = _friendly_error(exc)
                self.speed = 0.0
            self._set_status("error")

    def _prepare(self) -> None:
        try:
            os.makedirs(self.directory, exist_ok=True)
        except OSError as exc:
            raise DownloadError(tr("error.folder_create", error=exc)) from exc

        info = self._probe()
        total = info["total"]
        range_supported = info["ranges"]
        self.resolved_url = info["url"]
        self.content_type = info["content_type"]

        if not self._name_finalized:
            suggested = self.requested_filename or info["filename"] or tr("file.default_name")
            suggested = sanitize_filename(suggested)
            if (not self.requested_filename
                    and not os.path.splitext(suggested)[1]
                    and info["content_type"]):
                extension = mimetypes.guess_extension(info["content_type"])
                if extension:
                    suggested += extension
            with _FILENAME_LOCK:
                self.filename = self._unique_filename(suggested)
            self._name_finalized = True

        old_total = self.total
        old_ranges = list(self.segment_ranges)
        self.total = total

        reuse = bool(old_ranges)
        if reuse and old_total and total and old_total != total:
            reuse = False
        if reuse and len(old_ranges) > MAX_CONNECTIONS:
            # Eski sürümlerden kalan 10'dan fazla parçayı yeniden böl.
            reuse = False
        if reuse and len(old_ranges) > 1 and not range_supported and total:
            reuse = False

        if reuse:
            self.segment_ranges = old_ranges
        else:
            if old_ranges:
                self._cleanup_parts()
            self.segment_ranges = _compute_ranges(
                total, self.connections if range_supported else 1,
            )

        self.segment_errors = [""] * len(self.segment_ranges)
        self._refresh_segment_progress()
        self._prepared = True

    def _probe(self) -> dict:
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "*/*",
            "Accept-Encoding": "identity",
        }
        total = 0
        range_supported = False
        suggested = ""
        content_type = ""
        final_url = self.url
        head_ok = False

        try:
            request = Request(self.url, method="HEAD", headers=headers)
            with urlopen(request, timeout=25) as response:
                head_ok = True
                final_url = response.geturl()
                total = _to_int(response.headers.get("Content-Length"))
                suggested = filename_from_disposition(
                    response.headers.get("Content-Disposition")
                )
                content_type = (
                    (response.headers.get("Content-Type") or "")
                    .split(";")[0].strip().lower()
                )
        except HTTPError as exc:
            if exc.code not in (400, 403, 405, 406, 501):
                raise DownloadError(
                    tr("error.server_response", code=exc.code)
                ) from exc
        except (URLError, TimeoutError, OSError, http.client.HTTPException) as exc:
            raise DownloadError(_friendly_error(exc)) from exc

        # Accept-Ranges başlığına güvenmek yerine sunucunun gerçekten
        # 206 Partial Content döndürdüğünü 1 baytlık bir istekle doğrula.
        range_supported = False
        try:
            range_headers = dict(headers)
            range_headers["Range"] = "bytes=0-0"
            request = Request(self.url, headers=range_headers)
            with urlopen(request, timeout=25) as response:
                final_url = response.geturl()
                status = getattr(response, "status", None) or response.getcode()
                content_range = response.headers.get("Content-Range") or ""
                match = _CONTENT_RANGE.match(content_range)
                if status == 206 and match:
                    range_supported = True
                    range_total = _to_int(match.group(3))
                    if range_total:
                        total = range_total
                if not total:
                    total = _to_int(response.headers.get("Content-Length"))
                suggested = suggested or filename_from_disposition(
                    response.headers.get("Content-Disposition")
                )
                content_type = content_type or (
                    response.headers.get("Content-Type") or ""
                ).split(";")[0].strip().lower()
        except HTTPError as exc:
            if not head_ok and exc.code != 416:
                raise DownloadError(
                    tr("error.server_response", code=exc.code)
                ) from exc
        except (URLError, TimeoutError, OSError, http.client.HTTPException) as exc:
            if not head_ok:
                raise DownloadError(_friendly_error(exc)) from exc

        suggested = sanitize_filename(
            suggested or filename_from_url(final_url),
        )
        return {
            "total": max(0, total),
            "ranges": bool(range_supported and total > 0),
            "filename": suggested,
            "url": final_url,
            "content_type": content_type,
        }

    def _spawn_segments(self) -> None:
        self._threads = []
        self.segment_errors = [""] * len(self.segment_ranges)
        for index in range(len(self.segment_ranges)):
            thread = threading.Thread(
                target=self._segment_worker,
                args=(index,),
                name=f"idm-{self.id}-{index}",
                daemon=True,
            )
            self._threads.append(thread)
            thread.start()

    def _segment_worker(self, index: int) -> None:
        try:
            self._download_segment(index)
        except DownloadError as exc:
            with self._lock:
                self.segment_errors[index] = str(exc)
        except Exception as exc:
            with self._lock:
                self.segment_errors[index] = _friendly_error(exc)

    def _download_segment(self, index: int) -> None:
        start, end = self.segment_ranges[index]
        expected = None if end is None else end - start + 1
        part_path = self._part_path(index)

        existing = 0
        try:
            if os.path.exists(part_path):
                existing = os.path.getsize(part_path)
        except OSError:
            existing = 0
        if expected is not None and existing > expected:
            existing = 0
            try:
                open(part_path, "wb").close()
            except OSError as exc:
                raise DownloadError(tr("error.temp_open", error=exc)) from exc

        with self._lock:
            self.segment_downloaded[index] = existing

        if expected is not None and existing >= expected:
            return

        position = start + existing
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "*/*",
            "Accept-Encoding": "identity",
        }
        if end is not None:
            headers["Range"] = f"bytes={position}-{end}"
        elif position > 0:
            headers["Range"] = f"bytes={position}-"

        request = Request(self.resolved_url, headers=headers)
        try:
            with urlopen(request, timeout=30) as response:
                status = getattr(response, "status", None) or response.getcode()
                if status == 200 and len(self.segment_ranges) > 1:
                    raise DownloadError(tr("error.range_unsupported"))
                if status == 200 and existing > 0:
                    # Sunucu Range başlığını yok saydı; parçayı baştan al.
                    existing = 0
                    position = start
                    with self._lock:
                        self.segment_downloaded[index] = 0
                if status == 206:
                    content_range = response.headers.get("Content-Range") or ""
                    match = _CONTENT_RANGE.match(content_range)
                    if match and int(match.group(1)) != position:
                        raise DownloadError(tr("error.unexpected_range"))

                mode = "ab" if existing > 0 else "wb"
                try:
                    handle = open(part_path, mode)
                except OSError as exc:
                    raise DownloadError(tr("error.temp_open", error=exc)) from exc

                with handle:
                    while True:
                        if self._cancel.is_set() or self._pause.is_set():
                            return
                        remaining = None if expected is None else expected - existing
                        if remaining is not None and remaining <= 0:
                            break
                        try:
                            chunk = response.read(
                                CHUNK_SIZE if remaining is None else min(CHUNK_SIZE, remaining)
                            )
                        except (OSError, http.client.HTTPException) as exc:
                            raise DownloadError(_friendly_error(exc)) from exc
                        if not chunk:
                            break
                        try:
                            handle.write(chunk)
                        except OSError as exc:
                            raise DownloadError(tr("error.write", error=exc)) from exc
                        existing += len(chunk)
                        with self._lock:
                            self.segment_downloaded[index] = existing
        except DownloadError:
            raise
        except (URLError, TimeoutError, OSError, http.client.HTTPException) as exc:
            raise DownloadError(_friendly_error(exc)) from exc

        if (expected is not None and existing < expected
                and not self._pause.is_set() and not self._cancel.is_set()):
            raise DownloadError(tr("error.early_close"))

    def _monitor(self) -> None:
        self._last_speed_time = 0.0
        self._last_speed_bytes = self.downloaded
        while True:
            alive = [thread for thread in self._threads if thread.is_alive()]
            self._tick_speed()
            if not alive:
                break
            time.sleep(0.15)
        self._tick_speed()

        if self._cancel.is_set():
            self._cleanup_parts()
            with self._lock:
                self.speed = 0.0
            self._set_status("canceled")
            return

        if self._pause.is_set():
            with self._lock:
                self.speed = 0.0
            self._set_status("paused")
            return

        errors = [error for error in self.segment_errors if error]
        if errors:
            with self._lock:
                self.error = errors[0]
                self.speed = 0.0
            self._set_status("error")
            return

        if self.total > 0 and self.downloaded < self.total:
            with self._lock:
                self.error = tr("error.incomplete")
                self.speed = 0.0
            self._set_status("error")
            return

        with self._lock:
            self.speed = 0.0
        self._set_status("merging")

        try:
            self._merge()
        except _MergeCancelled:
            self._cleanup_parts()
            self._set_status("canceled")
            return
        except OSError as exc:
            with self._lock:
                self.error = tr("error.save_failed", error=exc)
            self._set_status("error")
            return

        with self._lock:
            self.completed_at = time.time()
            self.speed = 0.0
        if self.total <= 0:
            try:
                self.total = os.path.getsize(self.target_path)
            except OSError:
                pass
        self._set_status("completed")

    def _tick_speed(self) -> None:
        now = time.monotonic()
        current = self.downloaded
        if not self._last_speed_time:
            self._last_speed_time = now
            self._last_speed_bytes = current
            self._emit()
            return
        elapsed = now - self._last_speed_time
        if elapsed < 0.35:
            return
        delta = current - self._last_speed_bytes
        instant = max(0.0, delta / elapsed)
        with self._lock:
            self.speed = instant if self.speed <= 0 else self.speed * 0.68 + instant * 0.32
        self._last_speed_time = now
        self._last_speed_bytes = current
        self._emit()

    def _merge(self) -> None:
        merged_path = os.path.join(self.directory, f".idm-{self.id}.merged")
        total_parts = len(self.segment_ranges)
        try:
            with open(merged_path, "wb") as output:
                for index in range(total_parts):
                    if self._cancel.is_set():
                        raise _MergeCancelled()
                    part_path = self._part_path(index)
                    try:
                        with open(part_path, "rb") as source:
                            while True:
                                if self._cancel.is_set():
                                    raise _MergeCancelled()
                                chunk = source.read(1024 * 1024)
                                if not chunk:
                                    break
                                output.write(chunk)
                    except FileNotFoundError as exc:
                        raise OSError(tr("error.part_missing")) from exc
            if self._cancel.is_set():
                raise _MergeCancelled()
            os.replace(merged_path, self.target_path)
        finally:
            if os.path.exists(merged_path):
                try:
                    os.remove(merged_path)
                except OSError:
                    pass
        self._cleanup_parts()

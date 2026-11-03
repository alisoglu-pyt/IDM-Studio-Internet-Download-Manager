"""Çok bağlantılı, duraklatılabilir indirme motoru.

HTTP/HTTPS, FTP/FTPS, HLS (.m3u8) ve BitTorrent (.torrent) kaynaklarını
destekler. Video platformları için isteğe bağlı ``yt-dlp`` entegrasyonu vardır.
İndirmeler parçalara ayrılır, her parça ayrı bir iş parçacığında indirilir ve
tamamlandığında tek bir dosyada birleştirilir.
"""

from __future__ import annotations

import base64
import ftplib
import glob
import http.client
import mimetypes
import os
import posixpath
import re
import threading
import time
import uuid
from collections import deque
from email.message import Message
from typing import Callable, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urljoin, urlparse
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
DEFAULT_RETRIES = 3
MAX_RETRIES = 10

ACTIVE_STATUSES = frozenset({
    "queued", "connecting", "downloading", "pausing", "merging", "canceling",
    "retrying",
})
PAUSABLE_STATUSES = frozenset({"connecting", "downloading", "retrying"})
FINISHED_STATUSES = frozenset({"completed", "canceled"})
SCHEDULED_STATUSES = frozenset({"scheduled"})
PENDING_STATUSES = frozenset({"paused", "error", "scheduled"})

KIND_HTTP = "http"
KIND_FTP = "ftp"
KIND_HLS = "hls"
KIND_TORRENT = "torrent"
KIND_VIDEO = "video"
KIND_CHOICES = ("auto", KIND_HTTP, KIND_FTP, KIND_HLS, KIND_TORRENT, KIND_VIDEO)

VIDEO_HOSTS = frozenset({
    "youtube.com", "youtu.be", "m.youtube.com", "music.youtube.com",
    "vimeo.com", "player.vimeo.com", "dailymotion.com", "dai.ly",
    "twitch.tv", "clips.twitch.tv", "soundcloud.com", "facebook.com",
    "fb.watch", "instagram.com", "tiktok.com", "twitter.com", "x.com",
    "reddit.com", "v.redd.it", "bilibili.com", "vk.com", "ok.ru",
    "rumble.com", "bitchute.com", "odysee.com", "streamable.com",
})

_BAD_FILENAME = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')
_CONTENT_RANGE = re.compile(r"bytes\s+(\d+)-(\d+)/(\d+|\*)")
_UNSATISFIED_RANGE = re.compile(r"bytes\s+\*/(\d+)", re.IGNORECASE)
_FILENAME_LOCK = threading.Lock()
_HLS_KEY = re.compile(
    r'#EXT-X-(?:SESSION-)?KEY:.*METHOD=([^,\s]+)', re.IGNORECASE,
)
_HLS_MAP = re.compile(r'#EXT-X-MAP:.*URI="([^"]+)"', re.IGNORECASE)
_HLS_STREAM = re.compile(r"#EXT-X-STREAM-INF:(.*)", re.IGNORECASE)


class DownloadError(Exception):
    """Kullanıcıya gösterilebilecek indirme hatası."""


class _MergeCancelled(Exception):
    pass


class _TransferAborted(Exception):
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


def is_video_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == item or host.endswith("." + item) for item in VIDEO_HOSTS)


def detect_kind(url: str, kind: str = "auto") -> str:
    """Kaynak türünü URL'den veya kullanıcı seçiminden belirler."""
    if kind in KIND_CHOICES and kind != "auto":
        return kind
    raw = (url or "").strip()
    lower = raw.lower()
    if lower.startswith("magnet:"):
        return KIND_TORRENT
    if os.path.isfile(raw) and lower.endswith(".torrent"):
        return KIND_TORRENT
    parsed = urlparse(raw)
    path = unquote(parsed.path or "").lower()
    if path.endswith(".torrent"):
        return KIND_TORRENT
    if path.endswith(".m3u8"):
        return KIND_HLS
    if parsed.scheme in ("ftp", "ftps"):
        return KIND_FTP
    if parsed.scheme in ("http", "https") and is_video_url(raw):
        return KIND_VIDEO
    return KIND_HTTP


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


def _fetch_text(url: str, limit: int = 5 * 1024 * 1024) -> str:
    request = Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "*/*",
        "Accept-Encoding": "identity",
    })
    with urlopen(request, timeout=25) as response:
        payload = response.read(limit + 1)
    if len(payload) > limit:
        raise DownloadError(tr("error.playlist_too_large"))
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    return payload.decode("utf-8", "replace")


def _parse_hls_playlist(text: str, base_url: str, depth: int = 0
                        ) -> tuple[str, list[str], float]:
    """Master/medya HLS listesini çözer; (init_url, segment_urls, süre) döner."""
    if depth > 3:
        raise DownloadError(tr("error.hls_nested"))
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines:
        upper = line.upper()
        if upper.startswith(("#EXT-X-KEY", "#EXT-X-SESSION-KEY")):
            match = _HLS_KEY.match(line)
            if match and match.group(1).upper() != "NONE":
                raise DownloadError(tr("error.hls_encrypted"))
        if upper.startswith("#EXT-X-BYTERANGE") or (
                upper.startswith("#EXT-X-MAP") and "BYTERANGE=" in upper):
            raise DownloadError(tr("error.hls_byterange"))

    variants: list[tuple[int, str]] = []
    for index, line in enumerate(lines):
        match = _HLS_STREAM.match(line)
        if not match or index + 1 >= len(lines):
            continue
        attrs = match.group(1)
        bandwidth = 0
        for item in attrs.split(","):
            if "=" not in item:
                continue
            key, value = item.split("=", 1)
            if key.strip().upper() == "BANDWIDTH":
                try:
                    bandwidth = int(value.strip().strip('"'))
                except ValueError:
                    bandwidth = 0
        variant_url = urljoin(base_url, lines[index + 1])
        if not variant_url.startswith("#"):
            variants.append((bandwidth, variant_url))
    if variants:
        variants.sort(key=lambda item: item[0], reverse=True)
        chosen = variants[0][1]
        return _parse_hls_playlist(_fetch_text(chosen), chosen, depth + 1)

    init_url = ""
    duration = 0.0
    segments: list[str] = []
    for line in lines:
        if line.upper().startswith("#EXT-X-MAP"):
            match = _HLS_MAP.match(line)
            if match:
                init_url = urljoin(base_url, match.group(1))
            continue
        if line.startswith("#EXTINF:"):
            try:
                duration += float(line.split(":", 1)[1].split(",", 1)[0])
            except ValueError:
                pass
            continue
        if line.startswith("#"):
            continue
        segments.append(urljoin(base_url, line))
    if not segments:
        raise DownloadError(tr("error.hls_empty"))
    if init_url:
        segments.insert(0, init_url)
    return init_url, segments, duration


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
        kind: str = "auto",
        scheduled_at: float = 0.0,
        auto_retry: bool = False,
        max_retries: int = DEFAULT_RETRIES,
        torrent_data: bytes = b"",
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
        self.kind = detect_kind(self.url, kind)
        self.scheduled_at = max(0.0, float(scheduled_at or 0.0))
        self.auto_retry = bool(auto_retry)
        self.max_retries = max(0, min(int(max_retries or 0), MAX_RETRIES))
        self.retry_count = 0
        self.torrent_data = torrent_data

        self.status = "scheduled" if self.scheduled_at > time.time() else "queued"
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
        self._ftp_info: dict = {}
        self._hls_urls: list[str] = []
        self._torrent_meta = None
        self._video_info: dict = {}
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

    @property
    def is_scheduled(self) -> bool:
        return self.status == "scheduled"

    # ------------------------------------------------------------------ kayıt
    def to_dict(self) -> dict:
        status = self.status
        if status in ACTIVE_STATUSES or status in ("retrying", "canceled"):
            status = "canceled" if status == "canceled" else "paused"
        torrent = ""
        if self.torrent_data:
            torrent = base64.b64encode(self.torrent_data).decode("ascii")
        return {
            "id": self.id,
            "url": self.url,
            "directory": self.directory,
            "filename": self.filename,
            "requested_filename": self.requested_filename,
            "connections": self.connections,
            "kind": self.kind,
            "total": self.total,
            "ranges": [[start, end] for start, end in self.segment_ranges],
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "scheduled_at": self.scheduled_at,
            "auto_retry": self.auto_retry,
            "max_retries": self.max_retries,
            "retry_count": self.retry_count,
            "torrent": torrent,
            "status": status,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict,
                  callback: Optional[Callable[[dict], None]] = None) -> "DownloadTask":
        torrent_data = b""
        encoded = data.get("torrent")
        if isinstance(encoded, str) and encoded:
            try:
                torrent_data = base64.b64decode(encoded.encode("ascii"))
            except (ValueError, TypeError):
                torrent_data = b""
        task = cls(
            url=str(data.get("url", "")),
            directory=str(data.get("directory") or os.path.expanduser("~")),
            filename=str(data.get("filename") or data.get("requested_filename") or ""),
            connections=int(data.get("connections") or DEFAULT_CONNECTIONS),
            callback=callback,
            task_id=str(data.get("id") or uuid.uuid4().hex[:12]),
            kind=str(data.get("kind") or "auto"),
            scheduled_at=float(data.get("scheduled_at") or 0.0),
            auto_retry=bool(data.get("auto_retry")),
            max_retries=int(data.get("max_retries") or 0),
            torrent_data=torrent_data,
        )
        task.requested_filename = str(data.get("requested_filename") or task.requested_filename)
        task.filename = sanitize_filename(
            str(data.get("filename") or task.requested_filename or ""),
        ) if (data.get("filename") or task.requested_filename) else ""
        task._name_finalized = bool(task.filename)
        task.total = _to_int(str(data.get("total") or 0))
        task.created_at = float(data.get("created_at") or time.time())
        task.completed_at = float(data.get("completed_at") or 0)
        task.retry_count = _to_int(str(data.get("retry_count") or 0))
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
            size = os.path.getsize(task.target_path) if os.path.isfile(task.target_path) else 0
            if task.total <= 0 or size == task.total or os.path.isdir(task.target_path):
                task.status = "completed"
                task.completed_at = task.completed_at or os.path.getmtime(task.target_path)
                task._prepared = True
                task._cleanup_parts()
                return task
        if saved_status == "completed":
            saved_status = "paused"

        # Tamamlanmış ama durumu kaydedilememiş indirmeleri kurtar.
        if (saved_status != "completed" and task.target_path and task.total > 0
                and os.path.isfile(task.target_path)
                and os.path.getsize(task.target_path) == task.total):
            task.status = "completed"
            task.completed_at = task.completed_at or os.path.getmtime(task.target_path)
            task._prepared = True
            task._cleanup_parts()
            return task

        if task.scheduled_at > 0 and saved_status not in ("completed", "error"):
            task.status = "scheduled"
        else:
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
            os.path.join(self.directory, f".idm-{self.id}.torrent.part"),
            os.path.join(self.directory, f".idm-{self.id}.torrent.state"),
            os.path.join(self.directory, f".idm-{self.id}.torrent.state.tmp"),
            os.path.join(self.directory, f".idm-{self.id}.video.*"),
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
        # Durum "paused" olsa bile eski kontrol iş parçacığı birkaç milisaniye
        # daha çalışıyor olabilir; yeni bir denetleyici başlatmadan önce bekle.
        if self._controller and self._controller.is_alive():
            if self.status in ("paused", "error", "scheduled"):
                self._controller.join(timeout=1.0)
            if self._controller.is_alive():
                return
        with self._lock:
            if self.status in ("downloading", "connecting", "pausing",
                               "merging", "canceling", "completed", "canceled",
                               "retrying"):
                return
            if self._controller and self._controller.is_alive():
                return
            self._pause.clear()
            self._cancel.clear()
            self.error = ""
            self.speed = 0.0
            self.retry_count = 0
            self.scheduled_at = 0.0
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
        if status not in ("paused", "error", "scheduled"):
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
        cleanup_now = False
        with self._lock:
            if self.status in ("completed", "canceled"):
                return
            self._cancel.set()
            self._pause.clear()
            # Hata/duraklatma durumunda denetleyici çoğu zaman bitmek üzeredir.
            # Bu durumlarda doğrudan iptal etmek, "canceling" durumunda kalmayı önler.
            immediate = self.status in ("error", "paused", "scheduled", "queued")
            busy = self.is_busy
            if immediate or not busy:
                self.status = "canceled"
                self.speed = 0.0
                cleanup_now = True
            else:
                self.status = "canceling"
        if cleanup_now:
            self._cleanup_parts()
        self._emit(True)

    # ------------------------------------------------------------------ motor
    def _run(self) -> None:
        attempt = 0
        while True:
            try:
                self._execute()
            except DownloadError as exc:
                if self._cancel.is_set():
                    self._cleanup_parts()
                    self._set_status("canceled")
                    return
                if self._pause.is_set():
                    with self._lock:
                        self.speed = 0.0
                    self._set_status("paused")
                    return
                with self._lock:
                    self.error = str(exc)
                    self.speed = 0.0
                if self._schedule_retry(attempt, str(exc)):
                    attempt += 1
                    continue
                if self._cancel.is_set():
                    self._cleanup_parts()
                    self._set_status("canceled")
                    return
                if self._pause.is_set():
                    with self._lock:
                        self.speed = 0.0
                    self._set_status("paused")
                    return
                self._set_status("error")
                return
            except Exception as exc:  # motor asla sessizce ölmemeli
                if self._cancel.is_set():
                    self._cleanup_parts()
                    self._set_status("canceled")
                    return
                if self._pause.is_set():
                    with self._lock:
                        self.speed = 0.0
                    self._set_status("paused")
                    return
                message = _friendly_error(exc)
                with self._lock:
                    self.error = message
                    self.speed = 0.0
                if self._schedule_retry(attempt, message):
                    attempt += 1
                    continue
                if self._cancel.is_set():
                    self._cleanup_parts()
                    self._set_status("canceled")
                    return
                if self._pause.is_set():
                    with self._lock:
                        self.speed = 0.0
                    self._set_status("paused")
                    return
                self._set_status("error")
                return

            if self.status == "error" and not self._cancel.is_set():
                if self._schedule_retry(attempt, self.error):
                    attempt += 1
                    continue
                if self._pause.is_set():
                    with self._lock:
                        self.speed = 0.0
                    self._set_status("paused")
                    return
            return

    def _execute(self) -> None:
        if self.kind == KIND_FTP:
            self._run_ftp()
            return
        if self.kind == KIND_TORRENT:
            self._run_torrent()
            return
        if self.kind == KIND_HLS:
            self._run_hls()
            return
        if self.kind == KIND_VIDEO:
            self._run_video()
            return
        self._run_http()

    def _schedule_retry(self, attempt: int, message: str) -> bool:
        if not self.auto_retry or self.max_retries <= 0:
            return False
        if attempt >= self.max_retries:
            return False
        if self._cancel.is_set() or self._pause.is_set():
            return False
        delay = min(15.0, float(2 ** attempt))
        self.retry_count = attempt + 1
        with self._lock:
            self.error = message
            self.speed = 0.0
            self.status = "retrying"
        self._emit(True)
        deadline = time.monotonic() + delay
        while time.monotonic() < deadline:
            if self._cancel.is_set() or self._pause.is_set():
                break
            time.sleep(0.15)
        if self._cancel.is_set():
            self._cleanup_parts()
            self._set_status("canceled")
            return False
        if self._pause.is_set():
            with self._lock:
                self.speed = 0.0
            self._set_status("paused")
            return False
        with self._lock:
            self.error = ""
        return True

    # ------------------------------------------------------------------ HTTP
    def _run_http(self) -> None:
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
        if self.kind == KIND_FTP:
            self._download_ftp_segment(index)
            return
        if self.kind == KIND_HLS:
            self._download_hls_segment(index)
            return
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

        if (self.kind in (KIND_HTTP, KIND_FTP)
                and self.total > 0 and self.downloaded < self.total):
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
        if self.total <= 0 or self.kind == KIND_HLS:
            try:
                self.total = os.path.getsize(self.target_path)
            except OSError:
                pass
        self._set_status("completed")

    # ------------------------------------------------------------------ FTP
    def _ftp_connect(self) -> tuple[ftplib.FTP, str]:
        parsed = urlparse(self.url)
        host = parsed.hostname
        if not host:
            raise DownloadError(tr("error.url_invalid"))
        port = parsed.port or 21
        if parsed.scheme == "ftps" and port == 990:
            raise DownloadError(tr("error.ftp_implicit"))
        user = unquote(parsed.username or "anonymous")
        password = unquote(parsed.password or "anonymous@")
        path = unquote(parsed.path or "/")
        # Tarayıcıların ürettiği FTP URL'lerinde görülen ";type=i" ekini at.
        path = re.sub(r";type=[aid]$", "", path, flags=re.IGNORECASE) or "/"
        try:
            if parsed.scheme == "ftps":
                ftp: ftplib.FTP = ftplib.FTP_TLS(timeout=30)
            else:
                ftp = ftplib.FTP(timeout=30)
            ftp.connect(host, port)
            ftp.login(user, password)
            if isinstance(ftp, ftplib.FTP_TLS):
                ftp.prot_p()
            ftp.set_pasv(True)
            return ftp, path
        except (OSError, EOFError, ftplib.Error) as exc:
            raise DownloadError(tr("error.ftp_failed", error=exc)) from exc

    def _prepare_ftp(self) -> None:
        try:
            os.makedirs(self.directory, exist_ok=True)
        except OSError as exc:
            raise DownloadError(tr("error.folder_create", error=exc)) from exc
        ftp, path = self._ftp_connect()
        try:
            name = posixpath.basename(path.rstrip("/"))
            if not name:
                raise DownloadError(tr("error.ftp_no_file"))
            size: Optional[int] = None
            try:
                size = ftp.size(path)
            except ftplib.Error:
                size = None
            rest_supported = False
            if size:
                try:
                    ftp.sendcmd("REST 0")
                    rest_supported = True
                except ftplib.Error:
                    rest_supported = False
            if not self._name_finalized:
                suggested = self.requested_filename or name or tr("file.default_name")
                with _FILENAME_LOCK:
                    self.filename = self._unique_filename(sanitize_filename(suggested))
                self._name_finalized = True
            self._ftp_info = {
                "path": path, "size": size, "rest": rest_supported,
            }
            self.resolved_url = self.url
            old_total = self.total
            old_ranges = list(self.segment_ranges)
            self.total = max(0, int(size or 0))
            reuse = bool(old_ranges)
            if reuse and old_total and self.total and old_total != self.total:
                reuse = False
            if reuse and len(old_ranges) > 1 and not rest_supported:
                reuse = False
            if reuse:
                self.segment_ranges = old_ranges
            else:
                if old_ranges:
                    self._cleanup_parts()
                workers = self.connections if (self.total > 0 and rest_supported) else 1
                self.segment_ranges = _compute_ranges(self.total, workers)
            self.segment_errors = [""] * len(self.segment_ranges)
            self._refresh_segment_progress()
            self._prepared = True
        finally:
            try:
                ftp.quit()
            except (OSError, EOFError, ftplib.Error):
                try:
                    ftp.close()
                except OSError:
                    pass

    def _run_ftp(self) -> None:
        if not self._prepared:
            self._prepare_ftp()
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

    def _download_ftp_segment(self, index: int) -> None:
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
        if expected is not None and existing >= expected:
            with self._lock:
                self.segment_downloaded[index] = existing
            return

        ftp, _ = self._ftp_connect()
        path = str(self._ftp_info.get("path") or "")
        position = start + existing
        handle = None
        skip = 0
        try:
            try:
                handle = open(part_path, "ab" if existing > 0 else "wb")
            except OSError as exc:
                raise DownloadError(tr("error.temp_open", error=exc)) from exc

            def callback(chunk: bytes) -> None:
                nonlocal existing, skip
                if self._cancel.is_set() or self._pause.is_set():
                    raise _TransferAborted()
                if skip:
                    if len(chunk) <= skip:
                        skip -= len(chunk)
                        return
                    chunk = chunk[skip:]
                    skip = 0
                if expected is not None and existing >= expected:
                    return
                if expected is not None:
                    chunk = chunk[: max(0, expected - existing)]
                if not chunk:
                    return
                try:
                    handle.write(chunk)  # type: ignore[union-attr]
                except OSError as exc:
                    raise DownloadError(tr("error.write", error=exc)) from exc
                existing += len(chunk)
                with self._lock:
                    self.segment_downloaded[index] = existing
                self._tick_speed()

            try:
                ftp.retrbinary(
                    f"RETR {path}", callback, blocksize=CHUNK_SIZE,
                    rest=position if position > 0 else 0,
                )
            except _TransferAborted:
                return
            except ftplib.error_perm as exc:
                if position > 0:
                    # Sunucu REST'i desteklemiyorsa dosyayı baştan indirip
                    # hedef aralığa kadar olan baytları atla.
                    existing = 0
                    position = start
                    skip = start
                    with self._lock:
                        self.segment_downloaded[index] = 0
                    if handle is not None:
                        handle.close()
                    handle = open(part_path, "wb")
                    try:
                        ftp.retrbinary(
                            f"RETR {path}", callback, blocksize=CHUNK_SIZE,
                        )
                    except _TransferAborted:
                        return
                else:
                    raise DownloadError(tr("error.ftp_failed", error=exc)) from exc
        except DownloadError:
            raise
        except (OSError, EOFError, ftplib.Error) as exc:
            raise DownloadError(tr("error.ftp_failed", error=exc)) from exc
        finally:
            if handle is not None:
                try:
                    handle.close()
                except OSError:
                    pass
            try:
                ftp.quit()
            except (OSError, EOFError, ftplib.Error):
                try:
                    ftp.close()
                except OSError:
                    pass

        if (expected is not None and existing < expected
                and not self._pause.is_set() and not self._cancel.is_set()):
            raise DownloadError(tr("error.early_close"))

    # ------------------------------------------------------------------ HLS
    def _prepare_hls(self) -> None:
        try:
            os.makedirs(self.directory, exist_ok=True)
        except OSError as exc:
            raise DownloadError(tr("error.folder_create", error=exc)) from exc
        text = _fetch_text(self.url)
        _, segments, duration = _parse_hls_playlist(text, self.url)
        self._hls_urls = segments
        if not self._name_finalized:
            stem = filename_from_url(self.url)
            if stem.lower().endswith(".m3u8"):
                stem = stem[:-5]
            if not stem:
                stem = "video"
            extension = ".mp4" if any(
                urlparse(url).path.lower().endswith((".mp4", ".m4s"))
                for url in segments
            ) else ".ts"
            suggested = self.requested_filename or (stem + extension)
            with _FILENAME_LOCK:
                self.filename = self._unique_filename(sanitize_filename(suggested))
            self._name_finalized = True
        self.total = 0
        self.segment_ranges = [(0, None)] * len(segments)
        self.segment_errors = [""] * len(self.segment_ranges)
        self._refresh_segment_progress()
        # Süre biliniyorsa boyut tahmini yalnızca ilerleme çubuğu içindir.
        if duration > 0:
            self.total = int(duration * 500 * 1024 / 8)
        self._prepared = True

    def _run_hls(self) -> None:
        if not self._prepared:
            self._prepare_hls()
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
        self._spawn_hls_segments()
        self._monitor()

    def _spawn_hls_segments(self) -> None:
        """HLS listelerinde binlerce parça olabileceği için sınırlı havuz."""
        self._threads = []
        self.segment_errors = [""] * len(self.segment_ranges)
        pending = deque(range(len(self.segment_ranges)))
        lock = threading.Lock()

        def worker() -> None:
            while True:
                if self._cancel.is_set() or self._pause.is_set():
                    return
                with lock:
                    if not pending:
                        return
                    index = pending.popleft()
                try:
                    self._download_segment(index)
                except DownloadError as exc:
                    with self._lock:
                        self.segment_errors[index] = str(exc)
                except Exception as exc:
                    with self._lock:
                        self.segment_errors[index] = _friendly_error(exc)

        count = min(self.connections, max(1, len(self.segment_ranges)))
        for index in range(count):
            thread = threading.Thread(
                target=worker, name=f"idm-{self.id}-hls-{index}", daemon=True,
            )
            self._threads.append(thread)
            thread.start()

    def _download_hls_segment(self, index: int) -> None:
        url = self._hls_urls[index]
        part_path = self._part_path(index)
        existing = 0
        try:
            if os.path.exists(part_path):
                existing = os.path.getsize(part_path)
        except OSError:
            existing = 0
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "*/*",
            "Accept-Encoding": "identity",
        }
        if existing:
            headers["Range"] = f"bytes={existing}-"
        request = Request(url, headers=headers)
        try:
            with urlopen(request, timeout=30) as response:
                status = getattr(response, "status", None) or response.getcode()
                if status != 206:
                    existing = 0
                    with self._lock:
                        self.segment_downloaded[index] = 0
                else:
                    content_range = response.headers.get("Content-Range") or ""
                    match = _CONTENT_RANGE.match(content_range)
                    if match and int(match.group(1)) != existing:
                        raise DownloadError(tr("error.unexpected_range"))
                content_length = _to_int(response.headers.get("Content-Length"))
                expected_total = None
                if content_length:
                    expected_total = (
                        existing + content_length if status == 206 else content_length
                    )
                mode = "ab" if existing > 0 else "wb"
                try:
                    handle = open(part_path, mode)
                except OSError as exc:
                    raise DownloadError(tr("error.temp_open", error=exc)) from exc
                with handle:
                    while True:
                        if self._cancel.is_set() or self._pause.is_set():
                            return
                        try:
                            chunk = response.read(CHUNK_SIZE)
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
                    if (expected_total is not None and existing < expected_total
                            and not self._pause.is_set() and not self._cancel.is_set()):
                        raise DownloadError(tr("error.early_close"))
        except DownloadError:
            raise
        except HTTPError as exc:
            # Duraklatılmış HLS indirmesinde tamamlanmış parça için Range
            # isteği 416 döndürebilir; bu parçayı tamamlanmış say.
            if exc.code == 416 and existing > 0:
                match = _UNSATISFIED_RANGE.match(
                    (exc.headers.get("Content-Range") if exc.headers else "") or "",
                )
                if match:
                    total = _to_int(match.group(1))
                    if total and existing > total:
                        try:
                            os.truncate(part_path, total)
                        except OSError:
                            pass
                        else:
                            existing = total
                            with self._lock:
                                self.segment_downloaded[index] = existing
                return
            raise DownloadError(_friendly_error(exc)) from exc
        except (URLError, TimeoutError, OSError, http.client.HTTPException) as exc:
            raise DownloadError(_friendly_error(exc)) from exc

    # -------------------------------------------------------------- torrent
    def _prepare_torrent(self) -> None:
        try:
            os.makedirs(self.directory, exist_ok=True)
        except OSError as exc:
            raise DownloadError(tr("error.folder_create", error=exc)) from exc
        from .torrent import TorrentError, TorrentMeta

        raw = self.torrent_data
        if not raw:
            lower = self.url.lower()
            if lower.startswith("magnet:"):
                raise DownloadError(tr("error.torrent_magnet"))
            try:
                if os.path.isfile(self.url):
                    with open(self.url, "rb") as handle:
                        raw = handle.read(32 * 1024 * 1024)
                else:
                    parsed = urlparse(self.url)
                    if parsed.scheme not in ("http", "https"):
                        raise DownloadError(tr("error.torrent_source"))
                    request = Request(self.url, headers={"User-Agent": USER_AGENT})
                    with urlopen(request, timeout=30) as response:
                        raw = response.read(32 * 1024 * 1024)
            except DownloadError:
                raise
            except (OSError, URLError, TimeoutError) as exc:
                raise DownloadError(tr("error.torrent_failed", error=exc)) from exc
            self.torrent_data = raw
        try:
            meta = TorrentMeta.from_bytes(raw)
        except TorrentError as exc:
            raise DownloadError(tr("error.torrent_failed", error=exc)) from exc
        self._torrent_meta = meta
        self.resolved_url = self.url
        if not self._name_finalized:
            suggested = self.requested_filename or meta.safe_name()
            with _FILENAME_LOCK:
                self.filename = self._unique_filename(sanitize_filename(suggested))
            self._name_finalized = True
        self.total = meta.total
        self.segment_ranges = [(0, max(0, meta.total - 1))]
        self.segment_errors = [""]
        self.segment_downloaded = [0]
        self._prepared = True

    def _run_torrent(self) -> None:
        if not self._prepared:
            self._prepare_torrent()
        if self._cancel.is_set():
            self._cleanup_parts()
            self._set_status("canceled")
            return
        if self._pause.is_set():
            self.speed = 0.0
            self._set_status("paused")
            return
        meta = self._torrent_meta
        if meta is None:
            raise DownloadError(tr("error.torrent_failed", error="meta verisi yok"))
        with self._lock:
            self.status = "downloading"
        self._emit(True)

        from .torrent import TorrentDownloader, TorrentError, finalize_torrent

        part_path = os.path.join(self.directory, f".idm-{self.id}.torrent.part")
        state_path = os.path.join(self.directory, f".idm-{self.id}.torrent.state")

        def stop_reason() -> Optional[str]:
            if self._cancel.is_set():
                return "cancel"
            if self._pause.is_set():
                return "pause"
            return None

        def on_progress(downloaded: int, total: int, speed: float) -> None:
            with self._lock:
                self.segment_downloaded = [max(0, downloaded)]
                self.total = max(0, total)
                self.speed = max(0.0, speed)
            self._emit()

        downloader = TorrentDownloader(
            meta, part_path, state_path, self.connections, on_progress, stop_reason,
        )
        try:
            result = downloader.run()
        except TorrentError as exc:
            raise DownloadError(tr("error.torrent_failed", error=exc)) from exc
        except OSError as exc:
            raise DownloadError(tr("error.file_operation", error=exc)) from exc

        if result == "paused":
            with self._lock:
                self.speed = 0.0
            self._set_status("paused")
            return
        if result == "canceled":
            self._cleanup_parts()
            self._set_status("canceled")
            return

        self._set_status("merging")
        try:
            target = finalize_torrent(
                meta, part_path, self.directory, self.filename,
            )
        except OSError as exc:
            raise DownloadError(tr("error.save_failed", error=exc)) from exc
        try:
            os.remove(state_path)
        except OSError:
            pass
        self.filename = os.path.basename(target)
        if os.path.isfile(target):
            self.total = os.path.getsize(target)
        with self._lock:
            self.completed_at = time.time()
            self.speed = 0.0
            self.segment_downloaded = [self.total]
        self._set_status("completed")

    # --------------------------------------------------------------- video
    def _prepare_video(self) -> None:
        try:
            import yt_dlp  # type: ignore[import-not-found]
        except ImportError as exc:
            raise DownloadError(tr("error.ytdlp_missing")) from exc
        try:
            options = {
                "quiet": True,
                "no_warnings": True,
                "noplaylist": True,
                "skip_download": True,
            }
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(self.url, download=False)
        except Exception as exc:
            raise DownloadError(tr("error.media_failed", error=exc)) from exc
        if isinstance(info, dict) and info.get("entries"):
            entries = list(info.get("entries") or [])
            info = entries[0] if entries else info
        if not isinstance(info, dict):
            raise DownloadError(tr("error.media_failed", error="bilgi alınamadı"))
        title = str(info.get("title") or "video")
        extension = str(info.get("ext") or "mp4")
        if not self._name_finalized:
            suggested = self.requested_filename or f"{title}.{extension}"
            if self.requested_filename and not os.path.splitext(suggested)[1]:
                suggested += f".{extension}"
            with _FILENAME_LOCK:
                self.filename = self._unique_filename(sanitize_filename(suggested))
            self._name_finalized = True
        self._video_info = info
        self.total = _to_int(
            info.get("filesize") or info.get("filesize_approx") or 0
        )
        self.segment_ranges = [(0, self.total - 1 if self.total else None)]
        self.segment_errors = [""]
        self.segment_downloaded = [0]
        self._prepared = True

    def _run_video(self) -> None:
        if not self._prepared:
            self._prepare_video()
        if self._cancel.is_set():
            self._cleanup_parts()
            self._set_status("canceled")
            return
        if self._pause.is_set():
            self.speed = 0.0
            self._set_status("paused")
            return
        try:
            import yt_dlp  # type: ignore[import-not-found]
        except ImportError as exc:
            raise DownloadError(tr("error.ytdlp_missing")) from exc
        with self._lock:
            self.status = "downloading"
        self._emit(True)

        # yt-dlp'nin başlık temizleme ve birleştirme davranışına güvenmek yerine
        # görev kimliğine bağlı sabit bir geçici ad kullan; sonuç dosyasını
        # indirme sonunda hedef ada taşı.
        work_prefix = os.path.join(self.directory, f".idm-{self.id}.video")
        outtmpl = work_prefix + ".%(ext)s"

        def hook(data: dict) -> None:
            if self._cancel.is_set() or self._pause.is_set():
                raise _TransferAborted()
            status = data.get("status")
            if status == "downloading":
                total = _to_int(
                    data.get("total_bytes") or data.get("total_bytes_estimate") or 0
                )
                downloaded = _to_int(data.get("downloaded_bytes") or 0)
                with self._lock:
                    if total:
                        self.total = total
                    self.segment_downloaded = [downloaded]
                self._tick_speed()
            elif status == "finished":
                downloaded = _to_int(
                    data.get("total_bytes") or data.get("downloaded_bytes") or 0
                )
                with self._lock:
                    self.segment_downloaded = [downloaded or self.total]
                self._tick_speed()

        options = {
            "outtmpl": outtmpl,
            "progress_hooks": [hook],
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "continuedl": True,
            "noplaylist": True,
            "overwrites": False,
            "retries": 3,
            "fragment_retries": 3,
        }
        final_path = ""
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(self.url, download=True)
                if isinstance(info, dict):
                    requested = info.get("requested_downloads") or []
                    if requested and isinstance(requested[0], dict):
                        final_path = str(requested[0].get("filepath") or "")
                    if not final_path:
                        try:
                            final_path = ydl.prepare_filename(info)
                        except Exception:
                            final_path = ""
        except _TransferAborted:
            if self._cancel.is_set():
                self._cleanup_parts()
                self._set_status("canceled")
            else:
                with self._lock:
                    self.speed = 0.0
                self._set_status("paused")
            return
        except Exception as exc:
            if self._cancel.is_set():
                self._cleanup_parts()
                self._set_status("canceled")
                return
            if self._pause.is_set():
                with self._lock:
                    self.speed = 0.0
                self._set_status("paused")
                return
            raise DownloadError(tr("error.media_failed", error=exc)) from exc

        if self._pause.is_set():
            with self._lock:
                self.speed = 0.0
            self._set_status("paused")
            return
        if self._cancel.is_set():
            self._cleanup_parts()
            self._set_status("canceled")
            return

        candidates = [
            path for path in glob.glob(work_prefix + ".*")
            if os.path.isfile(path)
            and not path.endswith((".part", ".ytdl", ".temp"))
        ]
        if candidates:
            candidate = max(candidates, key=os.path.getsize)
        elif final_path and os.path.exists(final_path):
            candidate = final_path
        else:
            raise DownloadError(tr("error.media_failed", error="çıktı dosyası bulunamadı"))

        target = self.target_path
        actual_ext = os.path.splitext(candidate)[1]
        target_root, target_ext = os.path.splitext(target)
        if actual_ext and target_ext.lower() != actual_ext.lower():
            target = target_root + actual_ext
        if os.path.exists(target):
            target = os.path.join(
                self.directory,
                self._unique_filename(os.path.basename(target)),
            )
        try:
            if os.path.abspath(candidate) != os.path.abspath(target):
                os.replace(candidate, target)
        except OSError as exc:
            raise DownloadError(tr("error.save_failed", error=exc)) from exc

        for leftover in glob.glob(work_prefix + ".*"):
            if os.path.abspath(leftover) == os.path.abspath(target):
                continue
            try:
                os.remove(leftover)
            except OSError:
                pass

        self.filename = os.path.basename(target)
        self.total = os.path.getsize(target)
        with self._lock:
            self.completed_at = time.time()
            self.speed = 0.0
            self.segment_downloaded = [self.total]
        self._set_status("completed")

    # ------------------------------------------------------------- ilerleme
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

"""Küçük, bağımlılıksız BitTorrent istemcisi.

Yalnızca BEP 3 (BitTorrent protokolü) ve HTTP/HTTPS tracker'ları destekler.
Manyetik bağlantılar için meta veri alışverişi (BEP 9) uygulanmadığından bir
``.torrent`` dosyası gerekir. İstemci; parçaları doğrular, kaldığı yerden devam
eder ve çok dosyalı torrent'leri tek bir geçici dosyada birleştirip açar.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import random
import socket
import struct
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Optional
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

BLOCK_SIZE = 16 * 1024
DEFAULT_PORT = 6881
MAX_PEERS_PER_ANNOUNCE = 80
NO_PROGRESS_TIMEOUT = 120.0


class TorrentError(Exception):
    """Kullanıcıya gösterilebilecek BitTorrent hatası."""


# --------------------------------------------------------------------- bencode
class BencodeError(ValueError):
    pass


def _decode(data: bytes, index: int = 0):
    if index >= len(data):
        raise BencodeError("Beklenmeyen dosya sonu")
    marker = data[index:index + 1]
    if marker == b"i":
        end = data.index(b"e", index + 1)
        try:
            return int(data[index + 1:end]), end + 1
        except ValueError as exc:
            raise BencodeError("Geçersiz tam sayı") from exc
    if marker == b"l":
        index += 1
        values = []
        while data[index:index + 1] != b"e":
            value, index = _decode(data, index)
            values.append(value)
        return values, index + 1
    if marker == b"d":
        index += 1
        values = {}
        while data[index:index + 1] != b"e":
            key, index = _decode(data, index)
            if not isinstance(key, bytes):
                raise BencodeError("Sözlük anahtarı bayt dizisi olmalı")
            value, index = _decode(data, index)
            values[key] = value
        return values, index + 1
    if marker.isdigit():
        colon = data.index(b":", index)
        length = int(data[index:colon])
        start = colon + 1
        end = start + length
        if end > len(data):
            raise BencodeError("Eksik bayt dizisi")
        return data[start:end], end
    raise BencodeError("Geçersiz bencode işareti")


def bdecode(data: bytes):
    value, index = _decode(data, 0)
    if index != len(data):
        raise BencodeError("Sonda fazladan veri var")
    return value


def _info_span(data: bytes) -> tuple[int, int]:
    """Üst düzey sözlükteki ``info`` değerinin ham bayt aralığını bulur."""
    if data[:1] != b"d":
        raise BencodeError("Torrent bir sözlük değil")
    index = 1
    while index < len(data) and data[index:index + 1] != b"e":
        key, index = _decode(data, index)
        start = index
        _, index = _decode(data, index)
        if key == b"info":
            return start, index
    raise BencodeError("Torrent içinde info bölümü yok")


# ------------------------------------------------------------------------ meta
@dataclass
class TorrentFile:
    path: str
    length: int
    offset: int


@dataclass
class TorrentMeta:
    info_hash: bytes
    name: str
    piece_length: int
    pieces: bytes
    total: int
    files: list[TorrentFile]
    trackers: list[str]
    raw: bytes = b""

    @property
    def piece_count(self) -> int:
        return len(self.pieces) // 20

    def piece_size(self, index: int) -> int:
        if index < 0 or index >= self.piece_count:
            return 0
        if index == self.piece_count - 1:
            return self.total - index * self.piece_length
        return self.piece_length

    def piece_hash(self, index: int) -> bytes:
        return self.pieces[index * 20:(index + 1) * 20]

    def safe_name(self) -> str:
        name = (self.name or "torrent").replace("\\", "/").strip("/")
        parts = [part for part in name.split("/") if part not in ("", ".", "..")]
        return parts[-1] if parts else "torrent"

    @classmethod
    def from_bytes(cls, data: bytes) -> "TorrentMeta":
        try:
            root = bdecode(data)
            start, end = _info_span(data)
        except (BencodeError, ValueError) as exc:
            raise TorrentError(f"Torrent dosyası okunamadı: {exc}") from exc
        if not isinstance(root, dict) or not isinstance(root.get(b"info"), dict):
            raise TorrentError("Geçersiz torrent dosyası")
        info = root[b"info"]
        name = info.get(b"name")
        piece_length = info.get(b"piece length")
        pieces = info.get(b"pieces")
        if not isinstance(name, bytes) or not isinstance(piece_length, int) \
                or not isinstance(pieces, bytes):
            raise TorrentError("Torrent meta verisi eksik")
        if piece_length <= 0 or not pieces or len(pieces) % 20:
            raise TorrentError("Torrent parça bilgisi geçersiz")
        info_hash = hashlib.sha1(data[start:end]).digest()

        files: list[TorrentFile] = []
        offset = 0
        raw_files = info.get(b"files")
        if isinstance(raw_files, list):
            for entry in raw_files:
                if not isinstance(entry, dict):
                    continue
                length = entry.get(b"length")
                path_parts = entry.get(b"path")
                if not isinstance(length, int) or not isinstance(path_parts, list):
                    continue
                parts = [
                    part.decode("utf-8", "replace")
                    for part in path_parts
                    if isinstance(part, bytes) and part not in (b"", b".", b"..")
                ]
                if not parts:
                    continue
                files.append(TorrentFile("/".join(parts), length, offset))
                offset += length
        else:
            length = info.get(b"length")
            if not isinstance(length, int):
                raise TorrentError("Torrent dosya boyutu eksik")
            files.append(TorrentFile(name.decode("utf-8", "replace"), length, 0))
            offset = length

        trackers: list[str] = []
        announce = root.get(b"announce")
        if isinstance(announce, bytes):
            trackers.append(announce.decode("utf-8", "replace"))
        announce_list = root.get(b"announce-list")
        if isinstance(announce_list, list):
            for tier in announce_list:
                if not isinstance(tier, list):
                    continue
                for item in tier:
                    if isinstance(item, bytes):
                        value = item.decode("utf-8", "replace")
                        if value not in trackers:
                            trackers.append(value)
        trackers = [url for url in trackers if urlparse(url).scheme in ("http", "https")]

        if not files:
            raise TorrentError("Torrent içinde indirilebilir dosya yok")
        if offset <= 0:
            raise TorrentError("Torrent dosya boyutu geçersiz")
        expected_pieces = (offset + piece_length - 1) // piece_length
        if expected_pieces != len(pieces) // 20:
            raise TorrentError("Torrent parça sayısı dosya boyutuyla uyuşmuyor")
        return cls(
            info_hash=info_hash,
            name=name.decode("utf-8", "replace"),
            piece_length=piece_length,
            pieces=pieces,
            total=offset,
            files=files,
            trackers=trackers,
            raw=data,
        )


# --------------------------------------------------------------------- tracker
def _tracker_request(url: str, meta: TorrentMeta, peer_id: bytes,
                     left: int, event: str) -> list[tuple[str, int]]:
    params = [
        ("info_hash", meta.info_hash),
        ("peer_id", peer_id),
        ("port", str(DEFAULT_PORT)),
        ("uploaded", "0"),
        ("downloaded", str(max(0, meta.total - left))),
        ("left", str(max(0, left))),
        ("compact", "1"),
        ("event", event),
    ]
    separator = "&" if "?" in url else "?"
    request = Request(
        url + separator + urlencode(params),
        headers={"User-Agent": "IDMStudio/1.0", "Accept-Encoding": "identity"},
    )
    with urlopen(request, timeout=20) as response:
        payload = response.read(4 * 1024 * 1024)
    try:
        result = bdecode(payload)
    except BencodeError as exc:
        raise TorrentError("Tracker yanıtı okunamadı") from exc
    if not isinstance(result, dict):
        raise TorrentError("Tracker geçersiz yanıt verdi")
    if b"failure reason" in result:
        reason = result[b"failure reason"]
        if isinstance(reason, bytes):
            reason = reason.decode("utf-8", "replace")
        raise TorrentError(f"Tracker: {reason}")
    peers = result.get(b"peers")
    found: list[tuple[str, int]] = []
    if isinstance(peers, bytes):
        for index in range(0, len(peers) - 5, 6):
            ip = ".".join(str(byte) for byte in peers[index:index + 4])
            port = struct.unpack(">H", peers[index + 4:index + 6])[0]
            if port:
                found.append((ip, port))
    elif isinstance(peers, list):
        for entry in peers:
            if not isinstance(entry, dict):
                continue
            ip = entry.get(b"ip")
            port = entry.get(b"port")
            if isinstance(ip, bytes):
                ip = ip.decode("utf-8", "replace")
            if isinstance(ip, str) and isinstance(port, int):
                found.append((ip, port))
    return found[:MAX_PEERS_PER_ANNOUNCE]


def gather_peers(meta: TorrentMeta, peer_id: bytes, left: int) -> list[tuple[str, int]]:
    peers: list[tuple[str, int]] = []
    for tracker in meta.trackers:
        try:
            peers.extend(_tracker_request(tracker, meta, peer_id, left, "started"))
        except Exception:
            continue
        if len(peers) >= MAX_PEERS_PER_ANNOUNCE:
            break
    # Aynı eşi bir kez kullan.
    seen: set[tuple[str, int]] = set()
    unique: list[tuple[str, int]] = []
    for peer in peers:
        if peer not in seen:
            seen.add(peer)
            unique.append(peer)
    return unique


# ------------------------------------------------------------------------ peer
def _recv_exact(sock: socket.socket, length: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < length:
        chunk = sock.recv(length - len(chunks))
        if not chunk:
            raise TorrentError("Eş bağlantıyı kapattı")
        chunks.extend(chunk)
    return bytes(chunks)


class _PeerConnection:
    def __init__(self, address: tuple[str, int], info_hash: bytes, peer_id: bytes):
        self.address = address
        self.info_hash = info_hash
        self.peer_id = peer_id
        self.sock: Optional[socket.socket] = None
        self.unchoked = False
        self.has_piece: Optional[set[int]] = None

    def connect(self) -> None:
        self.sock = socket.create_connection(self.address, timeout=10)
        self.sock.settimeout(8)
        handshake = (
            b"\x13BitTorrent protocol"
            + b"\x00" * 8
            + self.info_hash
            + self.peer_id
        )
        self.sock.sendall(handshake)
        response = _recv_exact(self.sock, 68)
        if response[1:20] != b"BitTorrent protocol":
            raise TorrentError("Eş protokolü tanınmadı")
        if response[28:48] != self.info_hash:
            raise TorrentError("Eş farklı bir torrent sunuyor")
        self.sock.sendall(struct.pack(">IB", 1, 2))  # interested

    def close(self) -> None:
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None

    def _send(self, message_id: int, payload: bytes = b"") -> None:
        if self.sock is None:
            raise TorrentError("Eş bağlantısı yok")
        self.sock.sendall(struct.pack(">IB", len(payload) + 1, message_id) + payload)

    def _read_message(self, timeout: float = 8.0) -> Optional[tuple[int, bytes]]:
        if self.sock is None:
            raise TorrentError("Eş bağlantısı yok")
        self.sock.settimeout(timeout)
        length = struct.unpack(">I", _recv_exact(self.sock, 4))[0]
        if length == 0:
            return None
        if length > 2 * 1024 * 1024:
            raise TorrentError("Eş çok büyük bir mesaj gönderdi")
        message = _recv_exact(self.sock, length)
        return message[0], message[1:]

    def _parse_bitfield(self, payload: bytes) -> None:
        pieces: set[int] = set()
        for byte_index, byte in enumerate(payload):
            for bit in range(8):
                if byte & (0x80 >> bit):
                    pieces.add(byte_index * 8 + bit)
        self.has_piece = pieces

    def wait_unchoke(self, timeout: float = 12.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.unchoked:
                return
            try:
                message = self._read_message(min(4.0, max(0.5, deadline - time.monotonic())))
            except socket.timeout:
                continue
            if message is None:
                continue
            message_id, payload = message
            if message_id == 0:
                self.unchoked = False
            elif message_id == 1:
                self.unchoked = True
            elif message_id == 5:
                self._parse_bitfield(payload)
            elif message_id == 4 and len(payload) >= 4:
                index = struct.unpack(">I", payload[:4])[0]
                if self.has_piece is not None:
                    self.has_piece.add(index)
        raise TorrentError("Eş bizi unchoke etmedi")

    def download_piece(self, index: int, length: int) -> bytes:
        blocks = [
            (offset, min(BLOCK_SIZE, length - offset))
            for offset in range(0, length, BLOCK_SIZE)
        ]
        pending = deque(blocks)
        outstanding: dict[int, int] = {}
        received: dict[int, bytes] = {}
        last_data = time.monotonic()
        while len(received) < len(blocks):
            while pending and len(outstanding) < 5:
                begin, size = pending.popleft()
                self._send(
                    6,
                    struct.pack(">III", index, begin, size),
                )
                outstanding[begin] = size
            try:
                message = self._read_message(8.0)
            except socket.timeout:
                if time.monotonic() - last_data > 25:
                    raise TorrentError("Eş yanıt vermiyor")
                continue
            if message is None:
                continue
            message_id, payload = message
            if message_id == 0:
                raise TorrentError("Eş bizi choked durumuna aldı")
            if message_id == 1:
                self.unchoked = True
                continue
            if message_id != 7 or len(payload) < 8:
                continue
            piece_index, begin = struct.unpack(">II", payload[:8])
            if piece_index != index or begin not in outstanding:
                continue
            size = outstanding.pop(begin)
            received[begin] = payload[8:8 + size]
            last_data = time.monotonic()
        return b"".join(received[begin] for begin, _ in blocks)

    def download_piece_checked(self, index: int, length: int, expected: bytes) -> bytes:
        data = self.download_piece(index, length)
        if hashlib.sha1(data).digest() != expected:
            raise TorrentError("Parça doğrulanamadı")
        return data


# ---------------------------------------------------------------------- client
class TorrentDownloader:
    """Parçaları eşlerden indirir; doğrulanmış parçaları diske yazar."""

    def __init__(
        self,
        meta: TorrentMeta,
        part_path: str,
        state_path: str,
        connections: int,
        on_progress: Callable[[int, int, float], None],
        stop_reason: Callable[[], Optional[str]],
    ) -> None:
        self.meta = meta
        self.part_path = part_path
        self.state_path = state_path
        self.connections = max(1, min(int(connections or 4), 10))
        self.on_progress = on_progress
        self.stop_reason = stop_reason
        self.peer_id = b"-ID0001-" + bytes(
            random.randint(33, 126) for _ in range(12)
        )
        self._done_pieces: set[int] = set()
        self._done_bytes = 0
        self._lock = threading.RLock()
        self._file = None
        self._pool: deque[int] = deque()
        self._peers: list[tuple[str, int]] = []
        self._peer_lock = threading.Lock()
        self._last_report = 0.0
        self._last_report_time = 0.0
        self._last_report_bytes = 0
        self._speed = 0.0
        self._last_progress_time = time.monotonic()
        self._state_dirty = False
        self._last_state_save = 0.0
        self._error: Optional[BaseException] = None

    # ------------------------------------------------------------- durum
    def _load_state(self) -> None:
        try:
            with open(self.state_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if int(data.get("pieces") or 0) != self.meta.piece_count:
                return
            encoded = data.get("bitfield") or ""
            raw = base64.b64decode(encoded)
            done: set[int] = set()
            for index in range(self.meta.piece_count):
                byte = raw[index // 8] if index // 8 < len(raw) else 0
                if byte & (0x80 >> (index % 8)):
                    done.add(index)
            self._done_pieces = done
            self._done_bytes = sum(self.meta.piece_size(i) for i in done)
        except (OSError, ValueError, TypeError, KeyError):
            self._done_pieces = set()
            self._done_bytes = 0

    def _save_state(self, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_state_save < 1.5:
            return
        self._last_state_save = now
        raw = bytearray((self.meta.piece_count + 7) // 8)
        with self._lock:
            for index in self._done_pieces:
                raw[index // 8] |= 0x80 >> (index % 8)
        payload = {
            "pieces": self.meta.piece_count,
            "bitfield": base64.b64encode(bytes(raw)).decode("ascii"),
        }
        try:
            temp = self.state_path + ".tmp"
            with open(temp, "w", encoding="utf-8") as handle:
                json.dump(payload, handle)
            os.replace(temp, self.state_path)
        except OSError:
            pass

    def _report(self, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_report < 0.35:
            return
        self._last_report = now
        with self._lock:
            downloaded = self._done_bytes
        if self._last_report_time:
            elapsed = now - self._last_report_time
            if elapsed >= 0.5:
                instant = max(0.0, (downloaded - self._last_report_bytes) / elapsed)
                self._speed = instant if self._speed <= 0 else self._speed * 0.7 + instant * 0.3
                self._last_report_time = now
                self._last_report_bytes = downloaded
        else:
            self._last_report_time = now
            self._last_report_bytes = downloaded
        try:
            self.on_progress(downloaded, self.meta.total, self._speed)
        except Exception:
            pass

    def _stopped(self) -> Optional[str]:
        try:
            return self.stop_reason()
        except Exception:
            return "cancel"

    # ------------------------------------------------------------- eşler
    def _refresh_peers(self) -> None:
        left = max(0, self.meta.total - self._done_bytes)
        peers = gather_peers(self.meta, self.peer_id, left)
        if peers:
            with self._peer_lock:
                self._peers = peers

    def _peer_snapshot(self) -> list[tuple[str, int]]:
        with self._peer_lock:
            return list(self._peers)

    # ------------------------------------------------------------- parçalar
    def _claim_piece(self) -> Optional[int]:
        with self._lock:
            return self._pool.popleft() if self._pool else None

    def _release_piece(self, index: int) -> None:
        with self._lock:
            self._pool.appendleft(index)

    def _store_piece(self, index: int, data: bytes) -> None:
        offset = index * self.meta.piece_length
        with self._lock:
            if self._file is None:
                raise TorrentError("Geçici dosya kapalı")
            self._file.seek(offset)
            self._file.write(data)
            self._file.flush()
            self._done_pieces.add(index)
            self._done_bytes += len(data)
            self._state_dirty = True
            self._last_progress_time = time.monotonic()
        self._save_state()
        self._report()

    def _download_one(self, piece_index: int, peers: list[tuple[str, int]],
                      start: int) -> bool:
        length = self.meta.piece_size(piece_index)
        expected = self.meta.piece_hash(piece_index)
        attempts = 0
        count = len(peers)
        if count == 0:
            return False
        while attempts < count * 2:
            if self._stopped():
                return False
            address = peers[(start + attempts) % count]
            connection = _PeerConnection(address, self.meta.info_hash, self.peer_id)
            try:
                connection.connect()
                connection.wait_unchoke()
                if connection.has_piece is not None and piece_index not in connection.has_piece:
                    raise TorrentError("Eşte bu parça yok")
                data = connection.download_piece_checked(piece_index, length, expected)
                self._store_piece(piece_index, data)
                return True
            except (OSError, TorrentError, ValueError):
                attempts += 1
                time.sleep(0.15)
            finally:
                connection.close()
        return False

    def _worker(self, worker_index: int) -> None:
        peers = self._peer_snapshot()
        rotation = worker_index
        failures = 0
        while True:
            reason = self._stopped()
            if reason:
                return
            piece = self._claim_piece()
            if piece is None:
                return
            peers = self._peer_snapshot() or peers
            if self._download_one(piece, peers, rotation):
                failures = 0
                rotation += 1
                continue
            self._release_piece(piece)
            failures += 1
            if self._stopped():
                return
            if failures >= 12:
                with self._lock:
                    if self._error is None:
                        self._error = TorrentError("Eşlerden veri alınamadı")
                return
            time.sleep(min(5.0, 0.5 * failures))
            if failures % 4 == 0:
                try:
                    self._refresh_peers()
                except Exception:
                    pass

    # ------------------------------------------------------------- genel
    def run(self) -> str:
        os.makedirs(os.path.dirname(self.part_path) or ".", exist_ok=True)
        if not os.path.exists(self.part_path):
            # Parça dosyası yoksa eski durum bilgisi güvenilir değildir.
            try:
                os.remove(self.state_path)
            except OSError:
                pass
        self._load_state()
        try:
            mode = "r+b" if os.path.exists(self.part_path) else "w+b"
            self._file = open(self.part_path, mode)
            size = os.path.getsize(self.part_path)
            if size != self.meta.total:
                self._file.truncate(self.meta.total)
        except OSError as exc:
            raise TorrentError(f"Geçici dosya açılamadı: {exc}") from exc

        with self._lock:
            missing = [
                index for index in range(self.meta.piece_count)
                if index not in self._done_pieces
            ]
        # Sıralı indirme, video/ISO gibi dosyalarda önizlemeyi hızlandırır.
        self._pool = deque(missing)

        if missing:
            try:
                self._refresh_peers()
            except Exception as exc:
                raise TorrentError(f"Tracker'a bağlanılamadı: {exc}") from exc
            if not self._peer_snapshot():
                raise TorrentError("Tracker hiç eş döndürmedi")

        self._report(force=True)
        if not missing:
            self._file.close()
            self._file = None
            return "completed"

        threads = [
            threading.Thread(
                target=self._worker,
                args=(index,),
                name=f"idm-torrent-{index}",
                daemon=True,
            )
            for index in range(min(self.connections, len(missing)))
        ]
        for thread in threads:
            thread.start()

        try:
            while any(thread.is_alive() for thread in threads):
                reason = self._stopped()
                if reason:
                    break
                if self._error is not None:
                    break
                if (time.monotonic() - self._last_progress_time > NO_PROGRESS_TIMEOUT
                        and len(self._done_pieces) < self.meta.piece_count):
                    self._error = TorrentError(
                        "Uzun süre ilerleme olmadı; eşler yanıt vermiyor."
                    )
                    break
                self._report()
                time.sleep(0.25)
            self._save_state(force=True)
        finally:
            reason = self._stopped()
            for thread in threads:
                thread.join(timeout=8)
            if self._file is not None:
                try:
                    self._file.close()
                except OSError:
                    pass
                self._file = None

        if self._error is not None:
            raise self._error
        reason = self._stopped()
        if reason == "cancel":
            return "canceled"
        if reason == "pause":
            return "paused"
        with self._lock:
            complete = len(self._done_pieces) == self.meta.piece_count
        if not complete:
            raise TorrentError("Torrent tamamlanamadı; eksik parçalar var.")
        return "completed"


# -------------------------------------------------------------------- finalize
def _safe_relative(path: str) -> str:
    parts = [
        part for part in path.replace("\\", "/").split("/")
        if part not in ("", ".", "..")
    ]
    return os.path.join(*parts) if parts else "dosya"


def finalize_torrent(meta: TorrentMeta, part_path: str, directory: str,
                     target_name: str = "") -> str:
    """Parça dosyasını tek dosyaya taşır veya çok dosyalı yapıyı açar."""
    root = os.path.join(directory, target_name or meta.safe_name())
    if len(meta.files) == 1:
        target = os.path.join(directory, target_name or _safe_relative(meta.files[0].path))
        parent = os.path.dirname(target)
        if parent:
            os.makedirs(parent, exist_ok=True)
        os.replace(part_path, target)
        return target

    os.makedirs(root, exist_ok=True)
    with open(part_path, "rb") as source:
        for entry in meta.files:
            target = os.path.join(root, _safe_relative(entry.path))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            source.seek(entry.offset)
            remaining = entry.length
            with open(target, "wb") as output:
                while remaining > 0:
                    chunk = source.read(min(1024 * 1024, remaining))
                    if not chunk:
                        break
                    output.write(chunk)
                    remaining -= len(chunk)
    try:
        os.remove(part_path)
    except OSError:
        pass
    return root

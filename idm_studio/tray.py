"""Sistem tepsisi entegrasyonu.

Windows'ta ek bağımlılık olmadan Win32 ``Shell_NotifyIcon`` API'si kullanılır.
Diğer platformlarda, kuruluysa ``pystray`` + ``Pillow`` ile çalışır. Tepsi
işlemleri Tkinter iş parçacığına doğrudan dokunmaz; uygulamaya bir eylem adı
gönderir.
"""

from __future__ import annotations

import os
import struct
import sys
import threading
from typing import Callable, Optional

from .i18n import tr


def _ico_bytes(size: int, primary: tuple[int, int, int],
               foreground: tuple[int, int, int]) -> bytes:
    """Basit bir indirme oku simgesini ICO dosyası olarak üretir."""
    pixels = bytearray()
    for y in range(size - 1, -1, -1):
        for x in range(size):
            # Yuvarlatılmış kare arka plan.
            radius = size * 0.26
            inside = True
            for cx, cy in ((radius, radius), (size - 1 - radius, radius),
                           (radius, size - 1 - radius),
                           (size - 1 - radius, size - 1 - radius)):
                if ((x < radius and y < radius) or (x > size - 1 - radius and y < radius)
                        or (x < radius and y > size - 1 - radius)
                        or (x > size - 1 - radius and y > size - 1 - radius)):
                    if (x - cx) ** 2 + (y - cy) ** 2 > radius ** 2:
                        inside = False
            color = primary if inside else (0, 0, 0)
            alpha = 255 if inside else 0
            # Ok gövdesi ve başlığı.
            cx = size / 2
            if inside:
                shaft = abs(x - cx) <= size * 0.07 and size * 0.24 <= y <= size * 0.58
                head = (size * 0.30 <= y <= size * 0.56
                        and abs(x - cx) <= (y - size * 0.30) * 0.85)
                base = size * 0.68 <= y <= size * 0.76 and size * 0.28 <= x <= size * 0.72
                side_l = size * 0.54 <= y <= size * 0.76 and size * 0.26 <= x <= size * 0.32
                side_r = size * 0.54 <= y <= size * 0.76 and size * 0.68 <= x <= size * 0.74
                if shaft or head or base or side_l or side_r:
                    color = foreground
            pixels.extend((color[2], color[1], color[0], alpha))
    mask_row = ((size + 31) // 32) * 4
    mask = bytes(mask_row * size)
    header = struct.pack(
        "<IIIHHIIIIII", 40, size, size * 2, 1, 32, 0,
        len(pixels), 0, 0, 0, 0,
    )
    image = header + bytes(pixels) + mask
    icon_header = struct.pack("<HHH", 0, 1, 1)
    entry = struct.pack(
        "<BBBBHHII", size if size < 256 else 0, size if size < 256 else 0,
        0, 0, 1, 32, len(image), 6 + 16,
    )
    return icon_header + entry + image


class TrayIcon:
    """Platforma göre Win32 veya pystray tabanlı tepsi simgesi."""

    def __init__(self, action: Callable[[str], None],
                 primary: str = "#6750A4", foreground: str = "#FFFFFF") -> None:
        self.action = action
        self.primary = primary
        self.foreground = foreground
        self.available = sys.platform.startswith("win") or self._pystray_available()
        self._thread: Optional[threading.Thread] = None
        self._icon = None
        self._nid = None
        self._hwnd = None
        self._hicon = None
        self._ico_path = ""
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._pystray_icon = None

    @staticmethod
    def _pystray_available() -> bool:
        try:
            import pystray  # noqa: F401
            from PIL import Image  # noqa: F401
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------ genel
    def start(self) -> bool:
        if not self.available:
            return False
        if sys.platform.startswith("win"):
            self._ready.clear()
            self._thread = threading.Thread(
                target=self._run_windows, name="idm-tray", daemon=True,
            )
            self._thread.start()
            return self._ready.wait(timeout=3)
        return self._run_pystray()

    def stop(self) -> None:
        self._stop.set()
        if sys.platform.startswith("win"):
            if self._hwnd:
                try:
                    import ctypes
                    ctypes.windll.user32.PostMessageW(self._hwnd, 0x0010, 0, 0)
                except Exception:
                    pass
            if self._thread:
                self._thread.join(timeout=3)
        elif self._pystray_icon is not None:
            try:
                self._pystray_icon.stop()
            except Exception:
                pass
            self._pystray_icon = None

    def notify(self, title: str, message: str) -> None:
        if sys.platform.startswith("win") and self._nid is not None:
            self._win_notify(title, message)
        elif self._pystray_icon is not None:
            try:
                self._pystray_icon.notify(message, title)
            except Exception:
                pass

    def refresh_text(self) -> None:
        """Dil değiştiğinde tepsi ipucunu günceller."""
        if sys.platform.startswith("win") and self._nid is not None:
            try:
                import ctypes

                self._nid.szTip = tr("tray.tooltip")
                self._nid.uFlags = 0x4  # NIF_TIP
                ctypes.windll.shell32.Shell_NotifyIconW(
                    1, ctypes.byref(self._nid),
                )
            except Exception:
                pass
        elif self._pystray_icon is not None:
            try:
                self._pystray_icon.title = tr("tray.tooltip")
            except Exception:
                pass

    def set_theme(self, primary: str, foreground: str) -> None:
        self.primary = primary
        self.foreground = foreground
        if sys.platform.startswith("win") and self._hwnd:
            self._win_set_icon()
        elif self._pystray_icon is not None:
            try:
                self._pystray_icon.icon = self._pystray_image()
            except Exception:
                pass

    # ---------------------------------------------------------------- Windows
    def _write_ico(self) -> str:
        from pathlib import Path

        path = str(Path.home() / ".config" / "idm-studio" / "tray.ico")
        os.makedirs(os.path.dirname(path), exist_ok=True)

        def rgb(value: str) -> tuple[int, int, int]:
            value = value.lstrip("#")
            return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)

        with open(path, "wb") as handle:
            handle.write(_ico_bytes(32, rgb(self.primary), rgb(self.foreground)))
        return path

    def _win_set_icon(self) -> None:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        user32.LoadImageW.restype = wintypes.HANDLE
        user32.LoadImageW.argtypes = [
            wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
            ctypes.c_int, ctypes.c_int, wintypes.UINT,
        ]
        user32.LoadIconW.restype = wintypes.HICON
        user32.DestroyIcon.argtypes = [wintypes.HICON]
        try:
            if self._hicon:
                user32.DestroyIcon(self._hicon)
            self._ico_path = self._write_ico()
            self._hicon = user32.LoadImageW(
                0, self._ico_path, 1, 32, 32, 0x10,
            )
            if not self._hicon:
                self._hicon = user32.LoadIconW(
                    0, ctypes.cast(32512, wintypes.LPCWSTR),
                )
        except Exception:
            self._hicon = None
        if self._nid is not None and self._hicon:
            self._nid.hIcon = self._hicon
            self._nid.uFlags = 0x1 | 0x2 | 0x4
            ctypes.windll.shell32.Shell_NotifyIconW(1, ctypes.byref(self._nid))

    def _win_notify(self, title: str, message: str) -> None:
        import ctypes

        nid = self._nid
        if nid is None:
            return
        nid.uFlags = 0x1 | 0x2 | 0x4 | 0x10
        nid.szInfoTitle = title[:63]
        nid.szInfo = message[:255]
        nid.dwInfoFlags = 0x1
        try:
            ctypes.windll.shell32.Shell_NotifyIconW(1, ctypes.byref(nid))
        except Exception:
            pass

    def _win_menu(self) -> None:
        import ctypes
        from ctypes import wintypes

        if not self._hwnd:
            return
        user32 = ctypes.windll.user32
        user32.CreatePopupMenu.restype = wintypes.HMENU
        user32.AppendMenuW.argtypes = [
            wintypes.HMENU, wintypes.UINT, wintypes.UINT, wintypes.LPCWSTR,
        ]
        user32.TrackPopupMenu.restype = ctypes.c_int
        user32.TrackPopupMenu.argtypes = [
            wintypes.HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int,
            ctypes.c_int, wintypes.HWND, ctypes.c_void_p,
        ]
        user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
        user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        user32.PostMessageW.argtypes = [
            wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
        ]
        user32.DestroyMenu.argtypes = [wintypes.HMENU]
        menu = user32.CreatePopupMenu()
        items = (
            (1001, tr("tray.show")),
            (1002, tr("tray.new_download")),
            (0, "-"),
            (1003, tr("tray.pause_all")),
            (1004, tr("tray.resume_all")),
            (0, "-"),
            (1005, tr("tray.exit")),
        )
        for item_id, label in items:
            if item_id == 0:
                user32.AppendMenuW(menu, 0x00000800, 0, "-")
            else:
                user32.AppendMenuW(menu, 0x00000000, item_id, label)
        point = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(point))
        user32.SetForegroundWindow(self._hwnd)
        command = user32.TrackPopupMenu(
            menu, 0x0100 | 0x0002, point.x, point.y, 0, self._hwnd, None,
        )
        user32.PostMessageW(self._hwnd, 0x0000, 0, 0)
        user32.DestroyMenu(menu)
        mapping = {
            1001: "toggle", 1002: "new", 1003: "pause_all",
            1004: "resume_all", 1005: "quit",
        }
        if command in mapping:
            try:
                self.action(mapping[command])
            except Exception:
                pass

    def _run_windows(self) -> None:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        shell32 = ctypes.windll.shell32
        kernel32 = ctypes.windll.kernel32
        WM_TRAY = 0x8000 + 1
        self._stop.clear()

        WNDPROC = ctypes.WINFUNCTYPE(
            ctypes.c_longlong, wintypes.HWND, wintypes.UINT,
            wintypes.WPARAM, wintypes.LPARAM,
        )

        class WNDCLASSW(ctypes.Structure):
            _fields_ = [
                ("style", wintypes.UINT),
                ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HINSTANCE),
                ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HANDLE),
                ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR),
            ]

        class NOTIFYICONDATAW(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("hWnd", wintypes.HWND),
                ("uID", wintypes.UINT),
                ("uFlags", wintypes.UINT),
                ("uCallbackMessage", wintypes.UINT),
                ("hIcon", wintypes.HICON),
                ("szTip", wintypes.WCHAR * 128),
                ("dwState", wintypes.DWORD),
                ("dwStateMask", wintypes.DWORD),
                ("szInfo", wintypes.WCHAR * 256),
                ("uTimeoutOrVersion", wintypes.UINT),
                ("szInfoTitle", wintypes.WCHAR * 64),
                ("dwInfoFlags", wintypes.DWORD),
                ("guidItem", ctypes.c_byte * 16),
                ("hBalloonIcon", wintypes.HICON),
            ]

        class MSG(ctypes.Structure):
            _fields_ = [
                ("hwnd", wintypes.HWND),
                ("message", wintypes.UINT),
                ("wParam", wintypes.WPARAM),
                ("lParam", wintypes.LPARAM),
                ("time", wintypes.DWORD),
                ("pt", wintypes.POINT),
                ("lPrivate", wintypes.DWORD),
            ]

        instance = kernel32.GetModuleHandleW(None)
        class_name = "IDMStudioTrayWindow"

        kernel32.GetModuleHandleW.restype = wintypes.HMODULE
        user32.CreateWindowExW.restype = wintypes.HWND
        user32.CreateWindowExW.argtypes = [
            wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
        ]
        user32.DefWindowProcW.restype = ctypes.c_ssize_t
        user32.DefWindowProcW.argtypes = [
            wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
        ]
        user32.GetMessageW.restype = ctypes.c_int
        user32.GetMessageW.argtypes = [
            ctypes.POINTER(MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT,
        ]
        user32.TranslateMessage.argtypes = [ctypes.POINTER(MSG)]
        user32.DispatchMessageW.restype = ctypes.c_ssize_t
        user32.DispatchMessageW.argtypes = [ctypes.POINTER(MSG)]
        user32.DestroyWindow.argtypes = [wintypes.HWND]
        user32.PostQuitMessage.argtypes = [ctypes.c_int]
        shell32.Shell_NotifyIconW.restype = wintypes.BOOL
        shell32.Shell_NotifyIconW.argtypes = [
            wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW),
        ]

        def window_proc(hwnd, message, wparam, lparam):
            if message == WM_TRAY:
                event = int(lparam) & 0xFFFF
                if event in (0x0202, 0x0203):  # sol tık / çift tık
                    try:
                        self.action("toggle")
                    except Exception:
                        pass
                elif event in (0x0205, 0x007B):  # sağ tık
                    self._win_menu()
                return 0
            if message == 0x0010:  # WM_CLOSE
                user32.DestroyWindow(hwnd)
                return 0
            if message == 0x0002:  # WM_DESTROY
                user32.PostQuitMessage(0)
                return 0
            return user32.DefWindowProcW(hwnd, message, wparam, lparam)

        proc = WNDPROC(window_proc)
        wc = WNDCLASSW()
        wc.lpfnWndProc = proc
        wc.hInstance = instance
        wc.lpszClassName = class_name
        try:
            user32.RegisterClassW(ctypes.byref(wc))
        except Exception:
            pass
        hwnd = user32.CreateWindowExW(
            0, class_name, "IDM Studio", 0, 0, 0, 0, 0, 0, 0, instance, 0,
        )
        if not hwnd:
            return
        self._hwnd = hwnd
        self._win_set_icon()
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = hwnd
        nid.uID = 1
        nid.uFlags = 0x1 | 0x2 | 0x4
        nid.uCallbackMessage = WM_TRAY
        nid.hIcon = self._hicon
        nid.szTip = tr("tray.tooltip")
        self._nid = nid
        if not shell32.Shell_NotifyIconW(0, ctypes.byref(nid)):
            self._nid = None
            user32.DestroyWindow(hwnd)
            return
        self._ready.set()

        msg = MSG()
        while not self._stop.is_set():
            result = user32.GetMessageW(ctypes.byref(msg), 0, 0, 0)
            if result <= 0:
                break
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        try:
            shell32.Shell_NotifyIconW(2, ctypes.byref(nid))
        except Exception:
            pass
        if self._hicon:
            try:
                user32.DestroyIcon(self._hicon)
            except Exception:
                pass
        self._nid = None
        self._hwnd = None

    # --------------------------------------------------------------- pystray
    def _pystray_image(self):
        from PIL import Image, ImageDraw

        def rgb(value: str) -> tuple[int, int, int, int]:
            value = value.lstrip("#")
            return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16), 255

        image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((0, 0, 63, 63), radius=17, fill=rgb(self.primary))
        fg = rgb(self.foreground)
        draw.rectangle((28, 14, 36, 34), fill=fg)
        draw.polygon([(20, 32), (44, 32), (32, 46)], fill=fg)
        draw.rectangle((18, 48, 46, 52), fill=fg)
        draw.rectangle((18, 42, 22, 52), fill=fg)
        draw.rectangle((42, 42, 46, 52), fill=fg)
        return image

    def _run_pystray(self) -> bool:
        try:
            import pystray
        except Exception:
            return False
        image = self._pystray_image()
        menu = pystray.Menu(
            pystray.MenuItem(tr("tray.show"), lambda: self.action("toggle")),
            pystray.MenuItem(tr("tray.new_download"), lambda: self.action("new")),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(tr("tray.pause_all"), lambda: self.action("pause_all")),
            pystray.MenuItem(tr("tray.resume_all"), lambda: self.action("resume_all")),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(tr("tray.exit"), lambda: self.action("quit")),
        )
        try:
            self._pystray_icon = pystray.Icon(
                "idm-studio", image, tr("tray.tooltip"), menu,
            )
            if hasattr(self._pystray_icon, "run_detached"):
                self._pystray_icon.run_detached()
            else:
                threading.Thread(
                    target=self._pystray_icon.run, name="idm-tray", daemon=True,
                ).start()
            return True
        except Exception:
            self._pystray_icon = None
            return False

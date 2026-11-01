#!/usr/bin/env python3
"""IDM Studio'yu başlatan giriş noktası."""

import sys


def _tkinter_available() -> bool:
    try:
        import tkinter  # noqa: F401
    except ModuleNotFoundError:
        print("Tkinter bulunamadı. IDM Studio arayüzü için Tkinter gerekir.")
        print("Debian / Ubuntu / Linux Mint:  sudo apt install python3-tk")
        print("Fedora:                         sudo dnf install python3-tkinter")
        print("Arch / Manjaro:                 sudo pacman -S tk")
        return False
    return True


if __name__ == "__main__":
    if not _tkinter_available():
        sys.exit(1)
    from idm_studio.app import main

    main()

<p align="center">
  <img src="packaging/idm-studio.svg" width="88" alt="IDM Studio icon">
</p>

<h1 align="center">IDM Studio</h1>

<p align="center">
  <a href="README.md">Türkçe</a> · <b>English</b>
</p>

<p align="center">
  <b>A Material 3-inspired, multi-connection desktop download manager</b><br>
  Python 3.10+ · Tkinter · Zero third-party dependencies · 16 languages
</p>

<p align="center">
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white" alt="Python 3.10+"></a>
  <img src="https://img.shields.io/badge/Tkinter-Material%203-FF6F00?logo=python&logoColor=white" alt="Tkinter and Material 3">
  <img src="https://img.shields.io/badge/dependencies-zero-2E7D32" alt="Zero third-party dependencies">
  <img src="https://img.shields.io/badge/languages-16-6750A4" alt="16 languages">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-8A2BE2" alt="MIT License"></a>
</p>

<p align="center">
  IDM Studio downloads large files over multiple connections, lets you pause and resume downloads exactly where
  they left off, and shows the whole process through live statistics.<br>
  Its interface is inspired by the Material Design 3 palette; the download engine uses only the Python standard library.
</p>

> **In short:** 1–10 concurrent segments, safe pause/resume, automatic recovery, light/dark themes,
> a 16-language interface, and ready-to-use Linux packages.

## Contents

- [Screenshots](#screenshots)
- [Highlights](#highlights)
- [Quick start](#quick-start)
- [Installation](#installation)
- [Usage](#usage)
- [Keyboard shortcuts](#keyboard-shortcuts)
- [Project structure](#project-structure)
- [How it works](#how-it-works)
- [Building packages](#building-packages)
- [Troubleshooting](#troubleshooting)
- [Known limitations](#known-limitations)
- [Contributing](#contributing)
- [License](#license)

## Screenshots

### Live download statistics

<p align="center">
  <img src="docs/screenshots/en/download-progress.png" width="900" alt="An active download in IDM Studio with progress bar, speed, size, and time remaining">
  <br>
  <sub>The active download card updates speed, percentage, downloaded/total size, and estimated time remaining in real time.</sub>
</p>

### Light and dark themes

<table align="center">
  <tr>
    <td align="center" width="50%">
      <img src="docs/screenshots/en/main-light.png" width="440" alt="IDM Studio main window in the light theme">
      <br>
      <sub><b>Light theme</b></sub>
    </td>
    <td align="center" width="50%">
      <img src="docs/screenshots/en/main-dark.png" width="440" alt="IDM Studio main window in the dark theme">
      <br>
      <sub><b>Dark theme</b></sub>
    </td>
  </tr>
</table>

<p align="center">
  <sub>Switch themes with a single click on the sun/moon icon in the top bar; your choice is restored on the next launch.</sub>
</p>

### New download dialog

<p align="center">
  <img src="docs/screenshots/en/new-download.png" width="620" alt="IDM Studio new download dialog with URL, filename, save folder, and segment count">
  <br>
  <sub>Enter a link, an optional filename, a save folder, and a segment count from 1 to 10 — all in one dialog.</sub>
</p>

## Highlights

### Fast and resilient download engine

- **Multi-part downloads:** Large files are split into 1–10 concurrent segments. The default is 4 connections, and the last selection is remembered.
- **Server capability check:** Before starting, a `HEAD` request and a 1-byte `Range` probe verify whether the server really supports ranged downloads.
- **Pause / resume:** Partial data is kept in `.idm-*.part` files; resuming requests only the missing byte range.
- **Automatic recovery:** If the app closes, unfinished downloads return in a paused state on the next launch.
- **Safe merging:** Segments are merged into a temporary file first and then moved into place with `os.replace`, so an interrupted merge cannot corrupt an existing file.
- **Single-stream fallback:** If the server does not support `Range` or the file is too small to split, the download completes over a single connection.
- **Clear errors:** HTTP errors, timeouts, connection drops, and disk errors are shown as plain-language messages; failed downloads can be retried from the card.

### Material 3 interface

- **Light and dark themes:** Switch between Material 3 color palettes with a single click.
- **Live statistics:** Speed, percentage, size, time remaining, and status update continuously on each card.
- **Library filters:** Sidebar views for all downloads, active downloads, completed downloads, and pending downloads.
- **Modern components:** Rounded cards, Canvas-drawn vector icons, snackbar notifications, custom text fields, and a slim scrollbar.
- **Card actions:** Pause, resume, cancel, open the folder, remove from the list, or double-click a completed file to open it.
- **About dialog:** Version, developer, and contact information; press `F1` to open it.

### Language, persistence, and everyday use

- **16-language interface:** Turkish, English, German, French, Italian, Portuguese, Spanish, Azerbaijani, Turkmen, Russian, Ukrainian, Finnish, Swedish, Japanese, Korean, and Chinese. Switch languages from the globe icon in the top bar or with `Ctrl+L`.
- **System language detection:** If no preference has been saved yet, a supported language is selected from the system locale.
- **Remembered preferences:** Theme, language, last save folder, and segment count are stored in `~/.config/idm-studio/state.json`.
- **Offline translations:** All interface strings are embedded in the application, so the UI is complete even when the system does not have the matching locale installed.

## Quick start

The only requirements are **Python 3.10+** and **Tkinter**. No third-party Python packages are needed.

```bash
cd internet-download-manager
./run.sh
```

Or launch it directly with Python:

```bash
python3 main.py
```

If `run.sh` is not executable:

```bash
chmod +x run.sh
./run.sh
```

> On Linux, Tkinter may be a separate package. See the [Installation](#installation) section for one-line
> install commands. The application requires a graphical desktop session; when running over SSH, use
> X11 forwarding or a virtual display.

## Installation

### Requirements

| Component | Requirement |
| --- | --- |
| Python | 3.10 or newer |
| GUI toolkit | Tkinter (bundled with official Windows/macOS Python installers) |
| Operating system | Linux, Windows, or macOS |
| Third-party Python packages | None |

### Tkinter on Linux

Debian / Ubuntu / Linux Mint:

```bash
sudo apt install python3-tk
```

Fedora:

```bash
sudo dnf install python3-tkinter
```

Arch / Manjaro:

```bash
sudo pacman -S tk
```

### Run from source

Clone the repository or download it as a ZIP, then from the project folder:

```bash
./run.sh
```

or:

```bash
python3 main.py
```

### Ready-made Linux packages

Prebuilt packages are available in the `dist/` directory.

| Package | File | Notes |
| --- | --- | --- |
| Debian / Ubuntu | `dist/idm-studio_1.0.0_all.deb` | Installs the `python3-tk` and `xdg-utils` dependencies automatically and adds a desktop menu entry. |
| AppImage | `dist/IDM-Studio-1.0.0-x86_64.AppImage` | Bundles the Python and Tkinter runtime; no installation required. |

#### Debian / Ubuntu (.deb)

```bash
sudo apt install ./dist/idm-studio_1.0.0_all.deb
idm-studio
```

After installation, the application also appears in the desktop menu as **IDM Studio**.

#### AppImage

```bash
chmod +x dist/IDM-Studio-1.0.0-x86_64.AppImage
./dist/IDM-Studio-1.0.0-x86_64.AppImage
```

If FUSE is not available:

```bash
APPIMAGE_EXTRACT_AND_RUN=1 ./dist/IDM-Studio-1.0.0-x86_64.AppImage
```

#### Verify package integrity

```bash
cd dist
sha256sum -c SHA256SUMS
```

## Usage

### Your first download

1. Click **New Download** in the top-right corner (or press `Ctrl+N`).
2. Paste an `http://` or `https://` link. If the scheme is missing, `https://` is added automatically.
3. Optionally change the filename and save folder.
4. Choose the number of segments (1–10; the last selection is remembered).
5. Click **Start Download**.

### Download card

Use the buttons on a download card to pause, resume, cancel, open the folder of a completed file,
or remove the entry from the list. Double-clicking a completed card opens the file with the default application.

When a download fails, a **Retry** button appears on the card. Canceling a download removes its temporary
part files; pausing a download keeps them for later.

### Language and theme

- The globe icon in the top bar (or `Ctrl+L`) opens the 16-language menu.
- The sun/moon icon switches between the light and dark themes.
- Changes apply instantly: all windows, card states, units, and dates adapt to the new language.

### About

The **About** item in the bottom-left corner (or `F1`) opens a window with version, developer,
and contact information.

## Keyboard shortcuts

| Shortcut | Action |
| --- | --- |
| `Ctrl+N` | New download dialog |
| `Ctrl+L` | Language menu |
| `Esc` | Close the new download dialog |
| `Enter` | Start the download while the URL field is focused |
| `F1` | About dialog |

## Project structure

```text
internet-download-manager/
├── main.py                  # Entry point and Tkinter check
├── idm_studio/
│   ├── app.py               # Main window, theme, filters, state management
│   ├── downloader.py        # Multi-part download engine (threads + Range)
│   ├── cards.py             # Canvas-rendered download cards
│   ├── dialogs.py           # New download and about dialogs
│   ├── i18n.py              # Interface strings for 16 languages and language selection
│   ├── widgets.py           # Material buttons, entries, snackbar, scrollbar…
│   ├── draw.py              # Rounded shapes and vector icons
│   ├── theme.py             # Material 3 color palette and fonts
│   ├── utils.py             # Formatting and file helpers
│   └── __init__.py          # Version information
├── packaging/
│   ├── build_deb.sh         # Debian package build
│   ├── build_appimage.sh    # PyInstaller + AppImage build
│   ├── build_all.sh         # Builds both packages
│   ├── idm-studio.desktop   # Desktop shortcut
│   ├── idm-studio.svg       # Vector application icon
│   └── idm-studio-256.png   # PNG application icon
├── docs/
│   └── screenshots/         # README screenshots (Turkish and English)
├── dist/                    # Generated .deb, AppImage, and SHA256SUMS
├── requirements.txt         # No third-party dependencies
├── run.sh                   # Quick launch script
├── LICENSE                  # MIT license
├── README.md                # Turkish README
└── README.en.md             # English README
```

## How it works

### 1. Server discovery

The engine first sends a `HEAD` request to learn the file size, filename (`Content-Disposition`),
content type, and final redirected URL. It then sends a `Range: bytes=0-0` request to verify that the
server really returns `206 Partial Content`. This avoids trusting the `Accept-Ranges` header blindly.

### 2. Splitting and downloading

If the server supports ranged downloads and the file is large enough, the content is split into at most
10 segments based on the selected connection count. Each segment is downloaded in its own thread with a
`Range` header and written to disk in 256 KB chunks. Files under 1 MB, or servers without `Range` support,
use a single stream.

### 3. Pausing and recovery

Each segment is stored in the download folder as `.idm-<task-id>.part<N>`. Pausing preserves these files;
resuming reads the current size and continues with `Range: bytes=current-...`. If the app closes, the task
list is restored from `state.json` and unfinished downloads come back paused.

### 4. Merging

Completed segments are merged into a temporary file named `.idm-<task-id>.merged`. When merging succeeds,
the file is moved to its destination with `os.replace`. If the app closes or the download is canceled during
merging, the destination file is left untouched.

### 5. Interface and persistence

All network operations run on background threads. Task updates reach the main Tkinter thread through a
`queue`, so the interface never freezes. The download list, theme, language, last folder, and segment count
are written atomically to `~/.config/idm-studio/state.json`.

### 6. Dependency-free design

The project uses no third-party Python packages. Downloads use `urllib`, `http.client`, and `threading`;
the interface uses only Tkinter and the standard library. `requirements.txt` is therefore informational only.

## Building packages

To build both packages on a Debian/Ubuntu build host:

```bash
./packaging/build_all.sh
```

To build only one package:

```bash
./packaging/build_deb.sh
./packaging/build_appimage.sh
```

- The `.deb` package is produced with `dpkg-deb` only and does not require root privileges.
- The AppImage bundles the Python/Tkinter runtime using PyInstaller.
- If Tkinter or PyInstaller is missing on the build host, `build_appimage.sh` downloads the required packages
  into `.build/` and sets up a local toolchain on Debian/Ubuntu; no `sudo` is required. An internet connection
  is needed, or you can install the system packages with `sudo apt install python3-tk pyinstaller`.
- Outputs and SHA256 checksums are created under `dist/`.

## Troubleshooting

| Problem | Solution |
| --- | --- |
| `ModuleNotFoundError: No module named 'tkinter'` | Install the Tkinter package for your distribution: `sudo apt install python3-tk`, `sudo dnf install python3-tkinter`, or `sudo pacman -S tk`. |
| `Grafik ekranı bulunamadı (DISPLAY değişkeni yok)` | Run the app in a graphical desktop session; when using SSH, try `ssh -X` or `xvfb-run`. |
| AppImage will not start | Make the file executable: `chmod +x dist/IDM-Studio-1.0.0-x86_64.AppImage`. On FUSE errors, launch it with `APPIMAGE_EXTRACT_AND_RUN=1`. |
| "The server does not support ranged downloads" | Set the segment count to 1 and download over a single connection. The server may not support the `Range` header. |
| Download stays at 0 B/s | The server may have closed the connection or the network may be down. Use the **Retry** button on the card. |
| Settings are corrupted / old downloads are missing | Back up and delete `~/.config/idm-studio/state.json`; the app will start with a clean state. |

## Known limitations

- Only HTTP and HTTPS are supported; there is no FTP, BitTorrent, or video-platform integration.
- There is no browser extension, clipboard link capture, or scheduled download feature.
- Downloads are not retried automatically; failed downloads can be resumed with **Retry** on the card.
- The ready-made `.deb` and AppImage packages target Linux. The application can run from source on Windows
  and macOS, but no prebuilt packages are provided for those platforms.
- The interface is built with Tkinter, so small visual differences may appear across platforms.

## Contributing

Contributions are welcome.

1. Fork the repository and create a new branch.
2. Make your change in the existing code style.
3. If you add interface text, add the corresponding translations to the language dictionaries in `idm_studio/i18n.py`.
4. Test the interface manually, then open a pull request with a clear commit message.

Quick syntax check:

```bash
python3 -m compileall idm_studio main.py
```

## License

This project is released under the MIT License; see the [`LICENSE`](LICENSE) file for details.

You are responsible for respecting the copyrights of the content you download and the terms of service
of the target server.

---

<p align="center">
  <sub>Developer: <b>Bekir Alişoğlu</b> · <a href="mailto:alisoglu@yahoo.com">alisoglu@yahoo.com</a></sub>
</p>

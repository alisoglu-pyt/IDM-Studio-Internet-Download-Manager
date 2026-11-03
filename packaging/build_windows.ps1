#requires -Version 5.1
# Builds a single-file Windows executable with PyInstaller.
# Requirements: Python 3.10+ and PyInstaller. The application icon is included.
# Optional: yt-dlp is bundled automatically when installed.

$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root

$VersionMatch = Select-String -Path "idm_studio\__init__.py" `
    -Pattern '^__version__ = "([^"]+)"' | Select-Object -First 1
if (-not $VersionMatch) {
    throw "Could not read the application version from idm_studio\__init__.py."
}
$Version = $VersionMatch.Matches[0].Groups[1].Value

$Python = if ($env:PYTHON) { $env:PYTHON } else { "python" }
& $Python -c "import tkinter, PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "Tkinter and PyInstaller must be available in the selected Python environment."
}

$Icon = Join-Path $PSScriptRoot "idm-studio.ico"
if (-not (Test-Path $Icon)) {
    throw "Missing packaging\idm-studio.ico."
}

$Dist = Join-Path $Root "dist"
$Build = Join-Path $Root ".build\windows"
$Spec = Join-Path $Build "spec"
$Work = Join-Path $Build "work"
New-Item -ItemType Directory -Force -Path $Dist, $Spec, $Work | Out-Null

$Name = "IDM-Studio-$Version-windows-x86_64"
$PyiArgs = @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--clean",
    "--windowed",
    "--onefile",
    "--name", $Name,
    "--distpath", $Dist,
    "--workpath", $Work,
    "--specpath", $Spec,
    "--paths", $Root,
    "--icon", $Icon,
    "--collect-submodules", "idm_studio",
    "--exclude-module", "pystray",
    "--exclude-module", "PIL"
)

& $Python -c "import yt_dlp" 2>$null
if ($LASTEXITCODE -eq 0) {
    $PyiArgs += @("--collect-all", "yt_dlp")
    Write-Output "yt-dlp found; video platform support will be bundled."
} else {
    Write-Output "yt-dlp not installed; the executable will show the optional-package error for video platforms."
}

$PyiArgs += (Join-Path $Root "main.py")

& $Python @PyiArgs
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE."
}

$Output = Join-Path $Dist "$Name.exe"
if (-not (Test-Path $Output)) {
    throw "Expected executable was not created: $Output"
}

$Hash = (Get-FileHash -Algorithm SHA256 $Output).Hash.ToLowerInvariant()
$Size = (Get-Item $Output).Length

$ChecksumPath = Join-Path $Dist "SHA256SUMS"
$ChecksumLines = @()
if (Test-Path $ChecksumPath) {
    $ChecksumLines = Get-Content $ChecksumPath | Where-Object {
        $_ -and ($_ -notmatch ([regex]::Escape("$Name.exe") + '$'))
    }
}
$ChecksumLines += "$Hash  $Name.exe"
[System.IO.File]::WriteAllText(
    $ChecksumPath,
    (($ChecksumLines -join "`n") + "`n"),
    [System.Text.Encoding]::ASCII
)

Write-Output "Created: $Output"
Write-Output "Size: $Size bytes"
Write-Output "SHA256: $Hash"
Write-Output "Checksums updated: $ChecksumPath"

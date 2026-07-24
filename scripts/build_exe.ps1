# Build KeyWish.exe with PyInstaller (Windows / conda)
# Usage:
#   conda activate base
#   powershell -ExecutionPolicy Bypass -File scripts\build_exe.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

Write-Host "==> Installing PyInstaller (if needed)..."
python -m pip install -q "pyinstaller>=6.0"

Write-Host "==> Cleaning old build..."
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue dist\KeyWish
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue build\KeyWish
Remove-Item -Force -ErrorAction SilentlyContinue dist\KeyWish.exe

Write-Host "==> Building..."
python -m PyInstaller --noconfirm keywish.spec

if (-not (Test-Path "dist\KeyWish.exe")) {
    Write-Error "Build failed: dist\KeyWish.exe not found"
    exit 1
}

Write-Host ""
Write-Host "OK: dist\KeyWish.exe"
Write-Host "Send that file to others. On first run it creates config\mappings.json next to the exe."
Write-Host "Tip: if the global hook fails, right-click -> Run as administrator."

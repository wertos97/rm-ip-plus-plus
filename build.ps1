# Build RM IP++ for Windows with the project virtual environment.
# Output: dist/RMIPpp_<ver>_win64.exe

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Missing .venv. Create it with: python -m venv .venv"
}

$ver = (Select-String -Path "src\version.py" -Pattern '__version__\s*=\s*"([^"]+)"').Matches[0].Groups[1].Value
$exe = "RMIPpp_${ver}_win64"

Write-Host "== dependencies =="
& $python -m pip install --disable-pip-version-check -r requirements-dev.txt

Write-Host "== checks =="
& $python -m ruff check .
& $python -m ruff format --check .
& $python -m pytest

Write-Host "== assets =="
& $python tools/make_ico.py
& $python tools/make_version_info.py

if (Test-Path "dist\$exe.exe") {
    try {
        Remove-Item "dist\$exe.exe" -Force
    } catch {
        throw "Close the running $exe.exe first, then build again."
    }
}

Write-Host "== PyInstaller (onefile) =="
& $python -m PyInstaller --noconfirm --clean --onefile --windowed --name $exe `
    --paths "src" `
    --icon "assets/icon.ico" `
    --add-data "assets/icon.ico;assets" `
    --add-data "assets/icon.svg;assets" `
    --version-file "build/version_info.txt" `
    --distpath "dist" `
    main.py

if (Test-Path "dist\RMIPpp") {
    Remove-Item "dist\RMIPpp" -Recurse -Force
}

Write-Host ""
Write-Host "Done: $PSScriptRoot\dist\$exe.exe"
Write-Host "The single-file exe unpacks itself to %TEMP% on start."
Write-Host ""
Write-Host "Optional firewall rule if discovery replies are blocked:"
Write-Host 'New-NetFirewallRule -DisplayName "RM IP++ UDP 52380" -Direction Inbound -LocalPort 52380 -Protocol UDP -Action Allow'

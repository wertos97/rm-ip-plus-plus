# Build RM IP++ for Windows (PowerShell; admin not required).
# Output: dist/RMIPpp_<ver>_win64.exe - single-file exe (no Python needed).

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$ver = (Select-String -Path "src\version.py" -Pattern '__version__\s*=\s*"([^"]+)"').Matches[0].Groups[1].Value
$exe = "RMIPpp_${ver}_win64"

Write-Host "== deps =="
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller

Write-Host "== tests =="
python tests/test_basic.py

Write-Host "== assets =="
python tools/make_ico.py
python tools/make_version_info.py

if (Test-Path "dist\$exe.exe") {
  try {
    Remove-Item "dist\$exe.exe" -Force
  } catch {
    throw "Close the running $exe.exe first, then build again."
  }
}

Write-Host "== pyinstaller (onefile) =="
pyinstaller --noconfirm --clean --onefile --windowed --name $exe `
  --paths "src" `
  --icon "assets/icon.ico" `
  --add-data "assets;assets" `
  --version-file "build/version_info.txt" `
  --distpath "dist" `
  main.py

if (Test-Path "dist\RMIPpp") { Remove-Item "dist\RMIPpp" -Recurse -Force }

Write-Host ""
Write-Host "Done: $PSScriptRoot\dist\$exe.exe"
Write-Host "The single-file exe unpacks itself to %TEMP% on start (a few seconds)."
Write-Host ""
Write-Host "Optional firewall rules (run once as admin) if discovery replies are blocked:"
Write-Host '  New-NetFirewallRule -DisplayName "RM IP++ UDP 52380" -Direction Inbound -LocalPort 52380 -Protocol UDP -Action Allow'

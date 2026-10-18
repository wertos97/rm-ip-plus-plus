# Build RM IP++ for Windows (PowerShell; admin not required).
# Output: dist/RMIPpp/RMIPpp.exe (onedir folder, no Python needed on target PC).

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "== deps =="
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller

Write-Host "== tests =="
python tests/test_basic.py

Write-Host "== assets =="
python tools/make_ico.py
python tools/make_version_info.py

Write-Host "== pyinstaller =="
pyinstaller --noconfirm --clean --windowed --name "RMIPpp" `
  --paths "src" `
  --icon "assets/icon.ico" `
  --add-data "assets;assets" `
  --version-file "build/version_info.txt" `
  main.py

Write-Host ""
Write-Host "Done: $PSScriptRoot\dist\RMIPpp\RMIPpp.exe"
Write-Host "Copy the whole dist\RMIPpp folder to the target machine."
Write-Host ""
Write-Host "Optional firewall rules (run once as admin) if discovery replies are blocked:"
Write-Host '  New-NetFirewallRule -DisplayName "RM IP++ UDP 52380" -Direction Inbound -LocalPort 52380 -Protocol UDP -Action Allow'

# Build RM IP++ for Windows (PowerShell; admin not required).
# Outputs:
#   dist/RMIPpp/RMIPpp.exe                 - onedir folder (fast start)
#   dist/RMIPpp_<ver>_win64.exe            - single-file exe (self-extracting)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$ver = (Select-String -Path "src\version.py" -Pattern '__version__\s*=\s*"([^"]+)"').Matches[0].Groups[1].Value

Write-Host "== deps =="
python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller

Write-Host "== tests =="
python tests/test_basic.py

Write-Host "== assets =="
python tools/make_ico.py
python tools/make_version_info.py

Write-Host "== pyinstaller (onedir) =="
pyinstaller --noconfirm --clean --windowed --name "RMIPpp" `
  --paths "src" `
  --icon "assets/icon.ico" `
  --add-data "assets;assets" `
  --version-file "build/version_info.txt" `
  main.py

Write-Host "== pyinstaller (onefile) =="
pyinstaller --noconfirm --clean --onefile --windowed --name "RMIPpp" `
  --paths "src" `
  --icon "assets/icon.ico" `
  --add-data "assets;assets" `
  --version-file "build/version_info.txt" `
  --distpath "dist\onefile" `
  main.py

Copy-Item "dist\onefile\RMIPpp.exe" "dist\RMIPpp_${ver}_win64.exe" -Force
Remove-Item "dist\onefile" -Recurse -Force

Write-Host ""
Write-Host "Done:"
Write-Host "  $PSScriptRoot\dist\RMIPpp\RMIPpp.exe        (folder - copy the whole folder)"
Write-Host "  $PSScriptRoot\dist\RMIPpp_${ver}_win64.exe (single file)"
Write-Host ""
Write-Host "Note: the single-file exe unpacks itself to %TEMP% on start (a few seconds)."
Write-Host ""
Write-Host "Optional firewall rules (run once as admin) if discovery replies are blocked:"
Write-Host '  New-NetFirewallRule -DisplayName "RM IP++ UDP 52380" -Direction Inbound -LocalPort 52380 -Protocol UDP -Action Allow'

# Budowanie RM IP++ na Windows (uruchom w PowerShell jako Administrator)
pip install -r requirements.txt
# szybki test bez kamery:
python tests/test_basic.py
# exe (duze przez WebEngine ~150-250 MB):
pyinstaller --noconfirm --windowed --name "RMIPpp" `
  --add-data "README.md;." `
  --collect-all PySide6 `
  main.py
# Wynik: dist/RMIPpp/RMIPpp.exe
# Regula firewall dla VISCA (raz, jako admin):
# New-NetFirewallRule -DisplayName "RM IP++ VISCA 52381" -Direction Inbound -LocalPort 52381 -Protocol TCP -Action Allow
# New-NetFirewallRule -DisplayName "RM IP++ VISCA 52381 UDP" -Direction Inbound -LocalPort 52381 -Protocol UDP -Action Allow

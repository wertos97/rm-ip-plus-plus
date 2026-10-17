# RM IP++ - konsola sterowania kamerami Sony (SRG/BRC)

Jedno okno, zakladki dla kazdej kamery: pelne PTZ, presety, kadry lokalne,
obraz (ekspozycja/WB) + most sieciowy WiFi+Ethernet. Zero konfiguracji IP.

## Co potrafi
- **Wykrywanie kamer**: ARP + SSDP + znane IP + zakres CIDR, przycisk Stop,
  kolumna statusu i modelu (np. `SRG-X400 (CAM2)`).
- **Most sieciowy**: WiFi z internetem zostaje NIETKNIETE; na Ethernet
  dokladane jest tylko secondary IP (`SkipAsSource`, bez bramy, UAC),
  wiec ruch do kamer idzie kablem, a Internet dalej po WiFi.
  Temp IP czyszczone przy wyjsciu (idempotentnie), wykrywanie sierot.
- **Sterowanie PTZ**: pad z trybem Jazda (press=ruch, release=stop) i Krok
  (klik = 1 precyzyjny krok; przytrzymanie = po 0,3 s plynny slizg).
  Suwak szybkosci 0-24, zoom/focus, przyciski Hold z powtorzeniem.
- **Presety kamery 1-256**: siatka, nazwy, zapis/odczyt/kasowanie, SpeedSelect,
  miniaturki 16:9 z `/oneshotimage1` (cache w TEMP).
- **Kadry (lokalne) 1-16 + pasek szybki 1-6**: zapisuja TYLKO pan/tilt/zoom/focus
  (`AbsolutePTZF` w configu aplikacji), przywracane jednym poleceniem.
  Nigdy nie ruszaja ekspozycji ani balansu bieli.
- **Obraz**: ekspozycja (iris/gain/shutter/komp.) i balans bieli z odczytem
  stanu z kamery; wartosci czytelne (F3.1, 1/30, +3 dB, stopnie, xN).
- **Styl**: czern + amber akcent (Alpha 7), techniczna czcionka.

## Uzycie
1. `pip install -r requirements.txt`
2. `python main.py` - skan startuje sam, ostatnie kamery probowane od razu.
3. Dwuklik na kamerze = zakladka sterowania. PPM = menu (Steruj/Edge/Diagnostyka).

## Test bez kamery
```
python tests/test_basic.py    # szybki test modulow
python mock_sony_cam.py       # atrapa 127.0.0.1:8080 + :52381
```

## Uwagi
- Kamera SRG-X400: ICMP czesto zablokowany (ping nie dziala, HTTP tak).
- `SlowPanTiltMode` przyjmowane (204), ale na tym FW nie wchodzi w zycie -
  nie uzywamy.
- Config (z haslem kamery) trzymany w `%APPDATA%\RMIP++\config.json`, nie w repo.

## Pliki
- `src/ui_main.py` - okno glowne, tabela kamer, skan (ScanWorker), motyw
- `src/ui_control.py` - panel sterowania: PTZ, presety, kadry, obraz
- `src/cam_control.py` - CGI API kamery (ruch, pozycje, presety, imaging)
- `src/sony_client.py` - klient HTTP digest (naglowki przegladarki)
- `src/discovery.py` - ARP/SSDP/probe rownolegly z postepem
- `src/net_manager.py` - karty, temp IP, UAC, cleanup
- `src/subnet_bridge.py` - SSDP M-SEARCH, ARP, dobor bridge IP
- `src/human.py` - mapy wartosci (shutter/iris/gain/dB/stopnie/zoom)
- `src/theme.py` - motyw Alpha 7 (czern + amber)
- `src/edge_view.py` - karta Edge `--app` per kamera (fallback)

## Wazne: najpierw link fizyczny
Most to warstwa L3 - nie zastapi kabla ani zasilania. Jesli Windows pokazuje
`Ethernet Disconnected / 0 bps`, sprawdz: zasilanie (12V albo PoE+), diode POWER,
LEDy LAN, klik wtyku, odczekaj ~60 s na boot.

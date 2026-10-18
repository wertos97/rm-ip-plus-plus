# RM IP++ 0.1 - Sony IP camera control console (SRG / BRC)

One window, one tab per camera: full PTZ, camera presets, local shots,
image (exposure/WB) and a Wi-Fi + Ethernet network bridge. No IP setup required.

## Quick start (for colleagues)

1. Unpack the folder and run `RMIPpp.exe`.
   Windows SmartScreen may warn about an unsigned app: **More info -> Run anyway**.
2. The app scans the network on start (ARP, SSDP, UDP 52380). Cameras appear in
   the list with model and status. If your cameras use a different login, open
   **Advanced** and change **Login / Password** (default: `admin` / `admin`).
3. Double-click a camera (or use **Control selected**) to open its control tab.

Notes:
- **Cameras on another subnet / directly on Ethernet:** use **Bridge unreachable**.
  Windows asks for admin rights once (UAC) and adds a temporary secondary IP on
  Ethernet. Wi-Fi stays online - Internet traffic keeps using Wi-Fi.
- **Changing camera IP/mask/gateway/name** (UDP SET) works only with `WRITE:on`
  in the camera; the WRITE state is shown in the device tooltip.
- **No video preview** by design: the camera feeds SDI/HDMI to the mixer.
- On first run Windows Firewall may ask to allow the app - allow it (private
  networks) so discovery replies are not blocked.

## Models

- **SRG-X400 / BRC-X400** (and relatives with the same CGI) - full support,
  verified live on SRG-X400.
- **BRC-AM7** - support based on Sony "CGI Command List" v2.0, detected
  automatically (`inq=viewermode` -> ModelName):
  PanTiltMove/ZoomMove (0-127 scale), PanTiltSpeedMode, RelativePanTilt,
  AbsolutePTZF (20-bit, 1 unit = 0.001 deg), presets (max 100), imaging.
  Differences: focus Near/Far works in steps (AbsoluteFocus - the camera has no
  continuous focus movement over CGI), preset recall has no speed, instead of
  ExposureMode there are three auto switches (shutter/iris/AGC), iris/gain in
  AM7 units (F/dB), shutter 50p, WB: atw/memory_a/preset, OnePush AF/WB as
  press+release. Details in the **About** window.

## Features

- **Camera discovery**: ARP + SSDP + known IPs + CIDR range, Stop button,
  status and model column (e.g. `SRG-X400 (CAM2)`). In parallel the app sends a
  **UDP 52380 broadcast** (Sony `ENQ:network`) - a camera with an address from
  another subnet answers too (same as "Auto IP Setup").
- **Camera network (UDP)**: change the camera IP/mask/gateway/name over
  broadcast (`MAC:<mac> ...` + ACK/NAK) - works without changing the PC
  adapter address, even when the camera is outside the PC subnet. Requires
  `WRITE:on` in the camera.
- **RM-IP panel table (UDP)**: `ENQ:camtable1..4` reads the camera table from
  the panel (112 slots, Group1-1..Group7-16), slot preview + CSV export/import
  in RM-IP Setup Tool format.
- **CSV (Sony format)**: export/import of the camera list (6 columns) and the
  panel table (`;Group No-Camera No,...` + 112 rows `GroupG-C,...`) - compatible
  with the original tool.
- **Network bridge**: Wi-Fi with Internet stays UNTOUCHED; Ethernet only gets a
  secondary IP (`SkipAsSource`, no gateway, UAC), so camera traffic goes over
  the cable while Internet keeps using Wi-Fi. Temporary IPs are cleaned up on
  exit (idempotent), orphan detection included.
- **PTZ control**: 8-way pad with Drive mode (press = move, release = stop) and
  Step mode (click = one precise step; hold = continuous glide after 0.3 s).
  Speed slider 0-24, zoom/focus, hold buttons with repeat.
- **Camera presets 1-256**: grid, names, save/recall/clear, SpeedSelect,
  16:9 thumbnails from `/oneshotimage1` (cached in TEMP).
- **Shots (local) 1-16 + quick bar 1-6**: store ONLY pan/tilt/zoom/focus
  (`AbsolutePTZF` in the app config), recalled with a single command.
  They never touch exposure or white balance.
- **Image**: exposure (iris/gain/shutter/comp.) and white balance with state
  read back from the camera; readable values (F3.1, 1/30, +3 dB, degrees, xN);
  units matched to the model (SRG vs BRC-AM7).
- **About**: button in the side panel - version, models, differences and
  limitations.
- **Style**: black + amber accent (Alpha 7), technical font.

## Running from source

1. `pip install -r requirements.txt`
2. `python main.py` - the scan starts by itself; recent cameras are probed first.
3. Double-click a camera = control tab. Right-click = menu (Control / Edge /
   Diagnostics).

## Building the portable exe

```
powershell -ExecutionPolicy Bypass -File build.ps1
```

Result: `dist/RMIPpp/RMIPpp.exe` (onedir). Copy the whole `dist/RMIPpp` folder -
no Python installation is needed on the target machine.

## Testing without a camera

```
python tests/test_basic.py      # quick module test
python tools/mock_sony_cam.py   # fake camera on 127.0.0.1:8080 + :52381
python tools/udp_probe.py       # UDP 52380 listen/diagnostics
python tools/udp_probe.py --camtable            # table from the RM-IP panel
python tools/udp_probe.py --write --mac ... --ip ... --name ...   # network SET
```

## Notes

- SRG-X400: ICMP is often blocked (ping fails, HTTP works).
- `SlowPanTiltMode` is accepted (204) but has no effect on this firmware - not used.
- Config (with the camera password) is kept in `%APPDATA%\RMIP++\config.json`,
  never in the repo.

## Files

- `main.py` - entry point (theme, window icon, AppUserModelID)
- `src/ui_main.py` - main window, camera table, scan (ScanWorker), About
- `src/ui_control.py` - control panel: PTZ, presets, shots, image
- `src/ui_udp.py` - UDP dialogs: camera network SET + RM-IP panel table + CSV
- `src/sony_udp.py` - UDP 52380 protocol (discovery, network SET, camtable)
- `src/sony_csv.py` - CSV compatible with RM-IP Setup Tool (camera list + panel table)
- `src/cam_control.py` - camera CGI API (movement, positions, presets, imaging)
- `src/sony_client.py` - HTTP digest client (browser headers)
- `src/discovery.py` - ARP/SSDP/parallel probe with progress
- `src/net_manager.py` - adapters, temp IPs, UAC, cleanup
- `src/subnet_bridge.py` - SSDP M-SEARCH, ARP, bridge IP selection
- `src/human.py` - value maps (shutter/iris/gain/dB/degrees/zoom; SRG + BRC-AM7)
- `src/theme.py` - Alpha 7 theme (black + amber)
- `src/edge_view.py` - Edge `--app` window per camera (fallback)
- `src/version.py` - app version (single source for UI and exe metadata)
- `assets/icon.svg` - app icon (vector); `python tools/make_ico.py` -> `assets/icon.ico`
- `tools/` - developer utilities (UI harness, UDP probe, icon generator, mock camera)

## Important: physical link first

The bridge is an L3 layer - it will not replace a cable or power. If Windows
shows `Ethernet Disconnected / 0 bps`, check: power (12V or PoE+), POWER LED,
LAN LEDs, connector, and wait ~60 s for boot.

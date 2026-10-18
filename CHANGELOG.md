# Changelog

## 0.1 - 2026-10-19

First public release.

### Highlights
- Single-window console: one tab per camera, no video preview (camera feeds SDI/HDMI to the mixer).
- Full PTZ with Drive/Step modes, speed control, zoom and focus.
- Camera presets 1-256 with names, recall speed and thumbnails.
- Local shots 1-16 + quick 1-6 (pan/tilt/zoom/focus only, via `AbsolutePTZF`).
- Exposure and white balance with readable values and state read-back.
- Discovery: ARP, SSDP, Sony UDP 52380; CIDR scan with progress and stop.
- Camera network over UDP (`SET` + ACK/NAK) and RM-IP500 panel table (`ENQ:camtable`).
- Sony-format CSV import/export (camera list and panel table).
- Wi-Fi + Ethernet bridge with temporary secondary IPs and cleanup.
- Automatic camera logins (SRG-X400 / BRC-AM7 defaults, per-camera prompt, remembered).
- Built-in demo camera to explore the interface without hardware.
- English UI, dark amber theme, tooltips and About window.
- Portable single-file exe with Windows version metadata and taskbar integration.

### Models
- SRG-X400 / BRC-X400: verified live.
- BRC-AM7: mapped from Sony CGI Command List v2.0; not yet verified on hardware.

### Known limitations
- No video preview by design.
- UDP `SET` requires `WRITE:on` in the camera.
- RM-IP500 panel table is read-only.
- Shots do not include exposure, white balance or colours.

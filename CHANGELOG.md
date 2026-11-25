# Changelog

## Unreleased

### Fixed
- Camera model detection now uses `inq=system`, including BRC-AM7.
- BRC-AM7 One Push WB uses `cameraoperation.cgi`.
- BRC-AM7 PTZ step scaling matches the documented 0.001 degree units.
- BRC-AM7 ISO mode is detected and manual gain is not sent in the wrong mode.
- SRG slow pan/tilt and focus mode use `camera.cgi`.
- SRG zoom readout uses the documented nonlinear curve.
- SRG shutter labels and demo mechanical limits match the documentation.
- Preset names reject query delimiters and values longer than 32 characters.
- Thumbnail refresh no longer moves the camera or overwrites presets.
- Windows keeps the legacy temporary thumbnail and bridge-state paths.
- Network cleanup verifies address removal before forgetting cleanup state.
- macOS ARP parsing accepts unpadded MAC addresses.
- macOS bridge detects USB and Thunderbolt Ethernet adapters.
- macOS cleanup retries for addresses added after startup.
- Windows Edge profile lookup uses a valid PowerShell query.
- Config loading tolerates valid JSON that is not an object.
- macOS icon generation emits a complete standard iconset.
- macOS builds fail if the app is not arm64.
- SSDP fallback enables broadcast sockets.
- Windows build fails on native command errors and removes stale executables.
- Shots now save against the camera IP instead of the tab label.
- Preset saves keep the name entered by the user.
- Generated thumbnails are no longer deleted from the cache.
- Camera refresh runs outside the GUI thread.
- Scan failures show an explicit error state.
- Configuration saves use an atomic replace.
- ARP interface filtering imports the adapter lookup correctly.

### Changed
- Keyboard support, visible focus and stronger control contrast.
- English user-facing messages throughout the UI.
- README structure, development commands and license status.
- Tests are isolated from real user data and run through pytest.
- Added Ruff, pinned dependencies and GitHub Actions workflows.
- Standardized comments and removed decorative separators.

### Added
- macOS Apple Silicon preview with platform-specific paths, browser integration and network bridge.
- Ad-hoc signed `.app` bundle packaged as a single ZIP for GitHub Releases.
- macOS CI on the `macos-15` arm64 runner.

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

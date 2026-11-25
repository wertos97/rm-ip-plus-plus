"""Generate README screenshots using the built-in demo camera (no hardware).

Usage:  python tools/make_screenshots.py [output_dir]

Isolates config in a temporary folder, so your real settings/credentials are
not touched. Screenshots show sample cameras; the control data is simulated.
"""

import atexit
import os
import shutil
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
os.environ.pop("QT_QPA_PLATFORM", None)

# keep the user's config untouched
import config_store as cfg  # noqa: E402

_TMP = tempfile.mkdtemp(prefix="rmip_shots_")
atexit.register(shutil.rmtree, _TMP, ignore_errors=True)
cfg.APP_DIR = _TMP
cfg.CONFIG_FILE = os.path.join(_TMP, "config.json")

from PySide6.QtWidgets import QApplication  # noqa: E402

import net_manager as nm  # noqa: E402
import ui_control  # noqa: E402
from demo_api import DemoCameraAPI  # noqa: E402
from theme import apply_theme  # noqa: E402
from ui_creds import CredentialsDialog  # noqa: E402
from ui_main import AboutDialog, MainWindow  # noqa: E402

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "assets", "screenshots")
os.makedirs(OUT, exist_ok=True)

app = QApplication([])
apply_theme(app)
nm.STATE_FILE = os.path.join(_TMP, "temp_ips.json")
w = MainWindow()
w.start_scan = lambda mode: None  # no automatic scan: sample data only
atexit.unregister(nm.cleanup_all)
w.resize(1600, 940)
w.show()
pump_until = time.time() + 1.2
while time.time() < pump_until:
    app.processEvents()
    time.sleep(0.05)


def pump(seconds=0.4):
    end = time.time() + seconds
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)


def shot(widget, name):
    pump(0.5)
    path = os.path.join(OUT, name)
    widget.grab().save(path)
    print("saved", path)


CAMS = [
    {"ip": "192.168.1.101", "http": True, "http_port": 80, "visca_52381": True, "model": "SRG-X400 (CAM2)"},
    {"ip": "192.168.1.102", "http": True, "http_port": 80, "visca_52381": True, "model": "BRC-AM7 (CAM1)"},
]
w.cams = [dict(c) for c in CAMS]
w.on_scan_done(w.cams, announce=False)
w.btn_demo.hide()
w.lbl.setText("Found: 2")
w.log.clear()
w.log_line("Scan fast (cidr=192.168.1.0/24).")
w.log_line("Scan done: ['192.168.1.101', '192.168.1.102']")

api = DemoCameraAPI("192.168.1.101")
tab = ui_control.CameraTab("192.168.1.101", "admin", "admin123", log=w.log_line, api=api)
tab.setProperty("ip", "192.168.1.101")
idx = w.ctrl_tabs.addTab(tab, "SRG-X400 (CAM2)")
w.ctrl_tabs.setTabToolTip(idx, "192.168.1.101 · CGI control")
w.ctrl_tabs.setCurrentWidget(tab)
w.refresh_panel_col()

api._pan = int(12.3 * 51.2)
api._tilt = int(-4.0 * 51.2)
api._zoom = int((3.2 - 1.0) / 19.0 * 0x4000)
tab.refresh_all()
pump(0.8)

PRESETS = {1: "Wide", 2: "MCU host", 3: "Two-shot", 4: "CU guest", 5: "Panel", 6: "Logo"}
for n, name in PRESETS.items():
    api.home()
    api.move("right" if n % 2 else "left", 4 + n)
    api.zoom_move("tele" if n > 3 else "wide", 3)
    api.preset_set(n, name)
    ui_control.save_still(api, f"still_{n}.jpg")
tab.preset_panel.refresh_names(PRESETS)
pump(1.6)

SHOTS = ["Wide", "MCU host", "Two-shot", "CU guest"]
for i, name in enumerate(SHOTS):
    api.home()
    api.move("right" if i % 2 else "left", 6 + i * 2)
    api.zoom_move("tele", i * 2)
    p, t, z, f = api.status()[1]["AbsolutePTZF"].split(",")
    tab.frames[i] = {"name": name, "ptzf": [p, t, z, f]}
tab.frame_panel.reload()
tab.refresh_quick()
pump(0.4)

api._pan = int(12.3 * 51.2)
api._tilt = int(-4.0 * 51.2)
api._zoom = int((3.2 - 1.0) / 19.0 * 0x4000)
tab.pages.setCurrentIndex(0)
tab.refresh_all()
pump(0.6)

shot(w, "main.png")
shot(tab, "control.png")
tab.pages.setCurrentIndex(1)
pump(0.8)
shot(tab, "presets.png")
tab.pages.setCurrentIndex(2)
pump(0.4)
shot(tab, "shots.png")

about = AboutDialog(w)
about.resize(880, 680)
about.show()
pump(0.5)
shot(about, "about.png")
about.close()

login = CredentialsDialog(
    w, ip="192.168.1.110", user="admin", error="The default login was not accepted by this camera."
)
login.resize(540, 250)
login.show()
pump(0.4)
shot(login, "login.png")
login.close()

while w.ctrl_tabs.count():
    w.close_ctrl_tab(0)
w.cams = []
w.on_scan_done([], announce=False)
w.lbl.setText("Found: 0")
w.log.clear()
w.log_line("Scan fast (cidr=192.168.1.0/24).")
w.log_line("Scan done: []")
pump(0.4)
shot(w, "demo.png")

w.close()
print("all screenshots in", OUT, flush=True)

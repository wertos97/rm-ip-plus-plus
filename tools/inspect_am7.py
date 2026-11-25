"""Render the BRC-AM7 camera tab and About window without hardware.

Usage: python tools/inspect_am7.py <output_dir>

Uses CGI 2.0 sample responses and QWidget.grab, so it works without a window compositor.
"""

import atexit
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "ui_am7")
os.makedirs(OUT, exist_ok=True)

import net_manager as nm  # noqa: E402

atexit.unregister(nm.cleanup_all)

from PySide6.QtWidgets import QApplication  # noqa: E402

import ui_control  # noqa: E402
from theme import apply_theme  # noqa: E402


class FakeAM7:
    """Fake BRC-AM7 API using CGI 2.0 sample responses."""

    def __init__(self, ip, user, password, http_port=80):
        self.ip = ip

    @property
    def family(self):
        return "am7"

    def status(self, timeout=None):
        return True, {
            "AbsolutePTZF": "2ab98,10394,2000,2f1a",
            "PtzfStatus": "idle",
            "FocusMode": "auto",
            "PanTiltSpeedStep": "extended",
        }

    def imaging(self, timeout=None):
        return True, {
            "ExposureAutoShutterEnable": "off",
            "ExposureAutoIris": "on",
            "ExposureAGCEnable": "on",
            "ExposureIris": 32000,
            "ExposureGain": 9,
            "ExposureExposureTime": 15,
            "ExposureCompensation": 12,
            "ExposureGainRange": "9,45",
            "ExposureExposureTimeRange": "5,25",
            "ExposureISOGainMode": "gain",
            "WhiteBalanceMode": "atw",
            "WhiteBalanceCbGain": 0,
            "WhiteBalanceCrGain": 0,
            "WhiteBalanceOffsetColorTemp": -7,
        }

    def preset_list(self, timeout=None):
        return True, {1: "KAM", 2: "WIDE", 5: "TABLICA", 6: "OKNO", 17: "DRZWI", 42: "KAM2"}


ui_control.CameraAPI = FakeAM7

app = QApplication(sys.argv[:1])
apply_theme(app)

frames = [None] * 16
frames[0] = {"name": "KAM A", "ptzf": ["2ab98", "10394", "2000", "2f1a"]}
frames[3] = {"name": "TABLICA", "ptzf": ["d5468", "0f000", "3000", "3a2c"]}

tab = ui_control.CameraTab("192.168.0.50", "admin", "admin", frames=frames)
tab.timer.stop()  # No background polling for screenshots.
tab.resize(1560, 820)
tab.show()

shots = [
    (0, "01_sterowanie_am7.png"),
    (1, "02_presety_am7.png"),
    (2, "03_kadry_am7.png"),
]
for idx, name in shots:
    tab.pages.setCurrentIndex(idx)
    app.processEvents()
    tab.grab().save(os.path.join(OUT, name))

# Verify the values reconstructed from the AM7 auto switches.
print("exp mode:", tab.cb_exp.currentText())
print("iris:", tab.sl_iris.value(), tab.sl_iris._lb.text())
print("gain:", tab.sl_gain.value(), tab.sl_gain._lb.text(), "range", tab.sl_gain.minimum(), tab.sl_gain.maximum())
print("shutter:", tab.sl_shut.value(), tab.sl_shut._lb.text())
print("comp:", tab.sl_comp.value(), tab.sl_comp._lb.text())
print("wb:", tab.cb_wb.currentText(), "items", [tab.cb_wb.itemText(i) for i in range(tab.cb_wb.count())])
print("wb off:", tab.sl_wboff.value(), "range", tab.sl_wboff.minimum(), tab.sl_wboff.maximum())
print("preset max:", tab.preset_panel.max_num, "speed enabled:", tab.preset_panel.sp_speed.isEnabled())
print("status:", tab.status.text())

# The last AM7 preset page contains slots 97-100.
tab.preset_panel.set_page(6)
app.processEvents()
tab.preset_panel.grab().save(os.path.join(OUT, "04_presety_am7_ostatnia.png"))
tab.preset_panel.set_page(0)
app.processEvents()

# About window.
import ui_main  # noqa: E402

dlg = ui_main.AboutDialog()
dlg.resize(780, 640)
dlg.show()
app.processEvents()
dlg.grab().save(os.path.join(OUT, "05_o_aplikacji.png"))
print("shots ->", OUT)
sys.exit(0)

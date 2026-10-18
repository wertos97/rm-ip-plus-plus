"""Zrzuty nowych okien UDP (bez wysylania SET - tylko widoki).

Uzycie:  python tools/inspect_udp.py [katalog_zrzutow]
"""
import atexit
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "ui_shots_udp")
os.makedirs(OUT, exist_ok=True)

os.environ.pop("QT_QPA_PLATFORM", None)
from PySide6.QtCore import QCoreApplication, QEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import net_manager as nm  # noqa: E402
atexit.unregister(nm.cleanup_all)  # test nie dotyka sieci

import config_store as cfg  # noqa: E402
import sony_udp as su  # noqa: E402
from theme import apply_theme  # noqa: E402
from ui_udp import CamtableDialog, WriteNetDialog  # noqa: E402

app = QApplication(sys.argv[:1])
apply_theme(app)


def pump(sec: float) -> None:
    t0 = time.time()
    while time.time() - t0 < sec:
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        time.sleep(0.02)


def snap(name: str, widget) -> None:
    widget.grab().save(os.path.join(OUT, name + ".png"))
    print(f"[shot] {name}", flush=True)


# --- 1) okno SET sieci: stan spoczynkowy + ACK + wymuszony WRITE:off ---
ok = {"mac": "F8-4E-17-DE-30-9F", "ip": "192.168.4.101", "mask": "255.255.255.0",
      "gateway": "192.168.4.1", "name": "CAM2", "writable": True}
d = WriteNetDialog(None, defaults=ok, old_ip="192.168.4.101")
d.show()
pump(0.8)
snap("udp_01_write_ok", d)

d.on_result({"ok": True, "kind": "ACK", "ip": "192.168.4.101",
             "reply_mac": "F8-4E-17-DE-30-9F",
             "replies": [{"kind": "ACK", "mac": "F8-4E-17-DE-30-9F",
                          "src_ip": "192.168.4.101",
                          "raw": b'\x02ACK:"F8-4E-17-DE-30-9F"\xff\x03'}]})
pump(0.5)
snap("udp_02_write_ack", d)
d.close()

dbad = WriteNetDialog(None, defaults={"mac": "F8-4E-17-DE-30-9F", "ip": "",
                                      "mask": "255.255.255.0", "gateway": "",
                                      "name": "CAM2", "writable": False},
                      old_ip="192.168.4.101")
dbad.show()
pump(0.8)
dbad.on_result({"ok": False, "kind": "timeout", "replies": []})
pump(0.4)
snap("udp_03_write_timeout", dbad)
dbad.close()

# --- 2) tabela panelu: pusty odczyt (stub UDP) + widok z danymi ---
real_q = su.query_camtable
su.query_camtable = lambda **kw: {"pages": [], "misc": [], "raw": []}
ct = CamtableDialog(None)
ct.show()
pump(1.0)
snap("udp_04_camtable_empty", ct)
su.query_camtable = real_q

fake = {"pages": [
    {"page": 1, "panel_mac": "02-00-C0-A8-00-01", "src_ip": "192.168.4.50",
     "entries": [{"slot": i,
                  "mac": (f"F8-4E-17-DE-30-{i:02X}" if i % 3 else ""),
                  "ip": (f"192.168.4.{100 + i}" if i % 3 else ""),
                  "name": (f"CAM{i}" if i % 3 else "")} for i in range(1, 29)]},
    {"page": 2, "panel_mac": "02-00-C0-A8-00-01", "src_ip": "192.168.4.50",
     "entries": [{"slot": i, "mac": "", "ip": "", "name": ""} for i in range(29, 57)]}],
    "misc": [], "raw": [b'\x02MAC:02-00-C0-A8-00-01\xffINFO:camtable1\xff...\xff\x03']}
ct.on_pages(fake)
pump(0.5)
snap("udp_05_camtable", ct)

# podglad z pliku CSV (bez zapisu do panelu)
import sony_csv as sc  # noqa: E402
csv_txt = sc.table_csv_text({1: {"name": "CAM2", "mac": "F8-4E-17-DE-30-9F",
                                 "ip": "192.168.4.101"}})
parsed = sc.parse_table_csv(csv_txt)
ct._slots = {r["slot"]: r for r in parsed["rows"]}
ct._fill(ct._slots)
ct.head.setText("Preview from file: rmip_table.csv · rows: 112, "
                "filled: 1 · (no write to the panel)")
pump(0.4)
snap("udp_06_camtable_csv", ct)
if ct.worker is not None:
    ct.worker.wait(6000)
ct.close()

# --- 3) glowne okno: nowy rząd przyciskow (bez mostu/UAC i bez zakladek) ---
real_load = cfg.load
cfg.load = lambda: {**real_load(), "known_ips": [], "open_tabs": []}
from ui_main import MainWindow  # noqa: E402
w = MainWindow()
w.showMaximized()
pump(1.0)
t0 = time.time()
while time.time() - t0 < 30:
    app.processEvents()
    if w.worker is None or not w.worker.isRunning():
        break
    time.sleep(0.05)
pump(1.0)
snap("udp_07_main_buttons", w)
left = w.cam_table.parentWidget()
pump(0.3)
snap("udp_08_left_panel", left)
cfg.load = real_load

print("DONE", flush=True)

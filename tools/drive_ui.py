"""Sterownik UI (computer-use przez Qt): przechodzi wszystkie widoki aplikacji
i zapisuje zrzuty per-widget. Kamera nie jest ruszana (zero komend ruchu).

Uzycie:  python tools/drive_ui.py <katalog_zrzutow> [ip]
"""
import os
import sys
import time
import atexit

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "ui_shots")
IP = sys.argv[2] if len(sys.argv) > 2 else "192.168.4.101"
os.makedirs(OUT, exist_ok=True)

os.environ.pop("QT_QPA_PLATFORM", None)
from PySide6.QtWidgets import QApplication  # noqa: E402
from PySide6.QtCore import QCoreApplication, QEvent  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

import net_manager as nm  # noqa: E402
from ui_main import MainWindow  # noqa: E402
from theme import apply_theme  # noqa: E402

atexit.unregister(nm.cleanup_all)  # test nie dotyka sieci

app = QApplication(sys.argv[:1])
apply_theme(app)

w = MainWindow()
w.showMaximized()


def pump(sec: float) -> None:
    t0 = time.time()
    while time.time() - t0 < sec:
        app.processEvents()
        # bez petli exec() DeferredDelete sam sie nie wykona (deleteLater!)
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        time.sleep(0.02)


def find_tab(w, ip: str) -> int:
    for i in range(w.ctrl_tabs.count()):
        tw = w.ctrl_tabs.widget(i)
        if (tw.property("ip") if tw else None) == ip or w.ctrl_tabs.tabText(i) == ip:
            return i
    return -1


def snap(name: str, widget=None) -> None:
    (widget or w).grab().save(os.path.join(OUT, name + ".png"))
    print(f"[shot] {name}", flush=True)


# 1) czekamy na skan startowy
t0 = time.time()
while time.time() - t0 < 45:
    app.processEvents()
    if w.worker is None or not w.worker.isRunning():
        break
    time.sleep(0.05)
pump(1.0)

# 2) karta sterowania kamery
if find_tab(w, IP) < 0:
    w.add_ctrl_tab(IP)
w.ctrl_tabs.setCurrentIndex(find_tab(w, IP))
pump(5.0)

tab = w.ctrl_tabs.currentWidget()

# 3) wszystkie widoki
pump(1.0)
snap("01_sterowanie")

tab.pages.setCurrentIndex(1)
pump(4.5)
snap("02_presety")

tab.pages.setCurrentIndex(2)
pump(2.0)
snap("03_kadry_ptz")

tab.pages.setCurrentIndex(0)
pump(0.8)
snap("04_powrot")

# 4) panel Zaawansowane
try:
    w.btn_adv.click()
    pump(1.5)
    snap("05_zaawansowane")
    w.btn_adv.click()
    pump(0.5)
except Exception as e:
    print(f"[warn] zaawansowane: {e}", flush=True)

# 5) interakcja jak uzytkownik: przelacz tryb padu Krok -> Jazda (QTest)
try:
    QTest.mouseClick(tab.rb_step, __import__("PySide6.QtCore", fromlist=["Qt"]).Qt.LeftButton)
    pump(0.4)
    snap("06_tryb_krok")
    QTest.mouseClick(tab.rb_drive, __import__("PySide6.QtCore", fromlist=["Qt"]).Qt.LeftButton)
    pump(0.4)
except Exception as e:
    print(f"[warn] tryb padu: {e}", flush=True)

print("DONE", flush=True)

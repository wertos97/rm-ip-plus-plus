"""Visual check: demo button after an empty scan, then the demo tab."""
import atexit
import os
import sys
import time

ROOT = r"C:\Users\Mateusz\Documents\RM IP ++"
sys.path.insert(0, os.path.join(ROOT, "src"))
os.environ.pop("QT_QPA_PLATFORM", None)

from PySide6.QtWidgets import QApplication  # noqa: E402

import net_manager as nm  # noqa: E402
from theme import apply_theme  # noqa: E402
from ui_main import MainWindow  # noqa: E402

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "ui_shots_text")
os.makedirs(OUT, exist_ok=True)

app = QApplication([])
apply_theme(app)
w = MainWindow()
atexit.unregister(nm.cleanup_all)
w.resize(1500, 900)
w.show()

deadline = time.time() + 60
while time.time() < deadline:
    app.processEvents()
    time.sleep(0.1)
    wk = getattr(w, "worker", None)
    if wk is not None and not wk.isRunning():
        break

for _ in range(20):
    app.processEvents()
    time.sleep(0.05)

print("cams:", [c["ip"] for c in w.cams])
print("demo button visible:", w.btn_demo.isVisible(), "geom:", w.btn_demo.geometry())
w.grab().save(os.path.join(OUT, "demo_no_devices.png"))

w.add_demo_camera()
for _ in range(40):
    app.processEvents()
    time.sleep(0.05)

print("cams after:", [c["ip"] for c in w.cams])
print("demo button visible:", w.btn_demo.isVisible())
print("tabs:", [w.ctrl_tabs.tabText(i) for i in range(w.ctrl_tabs.count())])
w.grab().save(os.path.join(OUT, "demo_added.png"))

tab = w.ctrl_tabs.currentWidget()
if tab is not None:
    from ui_control import save_still
    tab.api.home()
    tab.api.preset_set(1, "Wide")
    save_still(tab.api, "still_1.jpg")
    tab.api.move("right", 12)
    tab.api.zoom_move("tele", 8)
    tab.api.preset_set(2, "Close")
    save_still(tab.api, "still_2.jpg")
    tab.preset_panel.refresh_names({1: "Wide", 2: "Close"})
    for _ in range(30):
        app.processEvents()
        time.sleep(0.05)
    tab.grab().save(os.path.join(OUT, "demo_tab.png"))
    tab.pages.setCurrentIndex(1)
    for _ in range(20):
        app.processEvents()
        time.sleep(0.05)
    tab.grab().save(os.path.join(OUT, "demo_presets.png"))

print("saved to", OUT, flush=True)
sys.exit(0)

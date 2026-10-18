"""Test: polling statusu nie blokuje watku GUI, gdy kamera nie odpowiada.

Symuluje zakladke kamery z nieosiagalnym IP (192.168.4.101 bez trasy) i mierzy,
czy petla zdarzen Qt tyka plynnie (heartbeat 200 ms) w trakcie nieudanych pollow.
Sprawdza tez backoff timera. Offscreen - bez okien.
"""
import os
import sys
import time

os.environ["QT_QPA_PLATFORM"] = "offscreen"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

app = QApplication(sys.argv[:1])

from ui_control import CameraTab

tab = CameraTab("192.168.4.101", "admin", "admin", reachable=False)
tab.show()

ticks = [0]
hb = QTimer()
hb.setInterval(200)
hb.timeout.connect(lambda: ticks.__setitem__(0, ticks[0] + 1))
hb.start()

t0 = time.time()
while time.time() - t0 < 12.5:
    app.processEvents()
    time.sleep(0.01)
elapsed = time.time() - t0

hb.stop()
tab.shutdown()

# heartbeat: ~62 tyknięcia w 12.5 s; nawet z narzutem powinno być > 40
print(f"heartbeat: {ticks[0]} tickow w {elapsed:.1f}s")
print(f"interwal timera po porazkach: {tab.timer.interval()} ms")
assert ticks[0] >= 40, "the Qt event loop was blocked!"
assert tab.timer.interval() >= 5000, "no backoff after failed polls"
print("POLLING OK - GUI stays responsive, backoff works")

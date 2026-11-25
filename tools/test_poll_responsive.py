"""Check that status polling keeps the Qt GUI responsive.

Uses an unreachable camera address and a 200 ms heartbeat. Runs offscreen.
"""

import os
import sys
import time

os.environ["QT_QPA_PLATFORM"] = "offscreen"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv[:1])

from ui_control import CameraTab  # noqa: E402

tab = CameraTab("192.168.1.101", "admin", "admin", reachable=False)
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

# About 62 heartbeat ticks in 12.5 s; allow generous CI overhead.
print(f"heartbeat: {ticks[0]} ticks in {elapsed:.1f}s")
print(f"timer interval after failures: {tab.timer.interval()} ms")
assert ticks[0] >= 40, "the Qt event loop was blocked!"
assert tab.timer.interval() >= 5000, "no backoff after failed polls"
print("POLLING OK: GUI stays responsive, backoff works")

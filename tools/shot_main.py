"""Grab MainWindow (Qt widget grab, no compositor) to a PNG."""
import atexit
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
os.environ.pop("QT_QPA_PLATFORM", None)

from PySide6.QtWidgets import QApplication  # noqa: E402

import net_manager as nm  # noqa: E402
from theme import apply_theme  # noqa: E402
from ui_main import MainWindow  # noqa: E402

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "ui_shots_text", "main_en.png")

app = QApplication([])
apply_theme(app)
w = MainWindow()
atexit.unregister(nm.cleanup_all)
w.resize(1600, 940)
w.show()
qapp = app
for _ in range(60):
    qapp.processEvents()
    time.sleep(0.05)
os.makedirs(os.path.dirname(OUT), exist_ok=True)
w.grab().save(OUT)
print("saved", OUT, flush=True)
sys.exit(0)

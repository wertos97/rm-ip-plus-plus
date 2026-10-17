import sys, os, time, atexit
sys.path.insert(0, "src")
os.environ.pop("QT_QPA_PLATFORM", None)
import net_manager as nm
from PySide6.QtWidgets import QApplication
from ui_main import MainWindow
try:
    from theme import apply_theme
except ImportError:
    from src.theme import apply_theme  # noqa

app = QApplication([])
apply_theme(app)
w = MainWindow()
atexit.unregister(nm.cleanup_all)
w.showMaximized()
t0 = time.time()
wb = None
while time.time() - t0 < 5:
    app.processEvents()
    time.sleep(0.1)
    if w.worker is not None:
        wb = w.worker
        break
if wb:
    wb.wait(30000)
for _ in range(10):
    app.processEvents()
    time.sleep(0.2)
w.add_ctrl_tab("192.168.4.101")
for _ in range(12):
    app.processEvents()
    time.sleep(0.2)
px = app.primaryScreen().grabWindow(w.winId())
px.save("C:/Users/Mateusz/AppData/Local/Temp/rmip_amber.png")
print("shot amber", flush=True)
sys.exit(0)

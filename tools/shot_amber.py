import sys, os, time, atexit, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
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
IP = sys.argv[1] if len(sys.argv) > 1 else "192.168.4.101"
w.add_ctrl_tab(IP)
for _ in range(12):
    app.processEvents()
    time.sleep(0.2)
px = app.primaryScreen().grabWindow(w.winId())
out = os.path.join(tempfile.gettempdir(), "rmip_main.png")
px.save(out)
print("saved", out, flush=True)
sys.exit(0)

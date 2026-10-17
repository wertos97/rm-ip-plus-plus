"""Test mobilnej strony kamery (sv.html) w silniku aplikacji z UA iPhone."""
import sys, time
sys.path.insert(0, "src")
from PySide6.QtWidgets import QApplication
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineProfile
from PySide6.QtCore import QUrl, QEventLoop, QTimer

IPHONE = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
          "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
          "Mobile/15E148 Safari/604.1")
app = QApplication([])
prof = QWebEngineProfile("rmip-mobile-test")
prof.setHttpUserAgent(IPHONE)
view = QWebEngineView()
view.resize(1280, 800)
# auth jak w aplikacji
view.page().authenticationRequired.connect(
    lambda url, auth: (auth.setUser("admin"), auth.setPassword("admin123")))
loop = QEventLoop()
t0 = time.time()
view.loadFinished.connect(lambda ok: print(f"[{time.time()-t0:.1f}] loadFinished:", ok, flush=True))
view.load(QUrl("http://192.168.4.101/"))
QTimer.singleShot(25000, loop.quit)
loop.exec()
print("final url:", view.url().toString(), flush=True)
loop2 = QEventLoop()
QTimer.singleShot(6000, loop2.quit)
def done(h):
    import re
    txt = " ".join(re.sub(r"<[^>]+>", " ", h).split())
    print("BODY:", txt[-500:], flush=True)
    loop2.quit()
view.page().toHtml(done)
loop2.exec()

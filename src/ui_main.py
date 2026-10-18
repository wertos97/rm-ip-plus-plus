"""RM IP++: wykrywanie kamer Sony w sieci + otwieranie polaczen (karty web).

Zero konfiguracji: brak wyboru karty (wszystkie interfejsy na raz, wirtualne
typu Bluetooth/komorkowe sa ignorowane), skan startuje sam po uruchomieniu,
a most dobudowuje sie automatycznie tylko gdy kamera jest nieosiagalna.
"""
from __future__ import annotations

import atexit
import datetime
import os
import sys
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QEvent, Qt, QThread, Signal, QTimer
from PySide6.QtGui import QColor, QCursor, QIcon
try:  # ensures the SVG icon engine plugin is bundled by PyInstaller
    from PySide6 import QtSvg  # noqa: F401
except Exception:
    pass
from PySide6.QtWidgets import (
    QApplication, QDialog, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton,
    QSplitter, QStatusBar, QTableWidget, QTableWidgetItem, QTabWidget,
    QTextBrowser, QVBoxLayout, QWidget,
)

try:
    from . import net_manager as nm
    from . import discovery as disc
    from . import config_store as cfg
    from . import diagnostics as diag
    from . import subnet_bridge as bridge
    from . import edge_view as ev
    from . import sony_csv, sony_udp
    from .sony_client import DEFAULT_USER, DEFAULT_PASSWORD
    from .version import __version__ as APP_VERSION
except ImportError:
    import net_manager as nm  # noqa: E402
    import discovery as disc  # noqa: E402
    import config_store as cfg  # noqa: E402
    import diagnostics as diag  # noqa: E402
    import subnet_bridge as bridge  # noqa: E402
    import edge_view as ev  # noqa: E402
    import sony_csv  # noqa: E402
    import sony_udp  # noqa: E402
    from sony_client import DEFAULT_USER, DEFAULT_PASSWORD  # noqa: E402
    from version import __version__ as APP_VERSION  # noqa: E402


class _CenterHint(QLabel):
    """Szary napis wysrodkowany na pustej tabeli - rozciaga sie z viewportem."""

    def __init__(self, text: str, viewport):
        super().__init__(text, viewport)
        self.setAlignment(Qt.AlignCenter)
        self.setWordWrap(True)
        self.setStyleSheet("color:#6f757c; font-size:12px; background:transparent;")
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setGeometry(viewport.rect())
        viewport.installEventFilter(self)

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Type.Resize:
            self.setGeometry(obj.rect())
        return False


ABOUT_HTML = """
<style>
  body { color: #f2f2f2; font-size: 13px; }
  h3 { color: #ff9e2c; margin: 2px 0 2px 0; }
  h4 { color: #ff9e2c; margin: 16px 0 4px 0; letter-spacing: 1px; }
  li { margin-bottom: 4px; }
  .dim { color: #9aa0a6; }
  .tag { color: #ffd9a0; font-weight: bold; }
</style>
<h3>RM IP++ &nbsp;<span class="dim" style="font-size:12px;">v{{VERSION}} &middot; Sony IP camera control</span></h3>
<p>Windows, PySide6. One window, one tab per camera. No video preview &mdash; the camera
feeds SDI/HDMI to a mixer. The app sends HTTP CGI (Digest) commands and reads camera state.</p>

<h4>FEATURES</h4>
<ul>
<li><span class="tag">PTZ</span> &mdash; 8-way pad + HOME. Drive: moves while held
  (short click = 0.5 s). Step: click = one step (size 1-2000), hold = continuous
  after 0.3 s. Speed 0-24 (0 = auto, follows zoom).</li>
<li><span class="tag">Zoom / Focus</span> &mdash; W-/T+ (speed 0-8); Near/Far,
  One Push AF, auto/manual mode.</li>
<li><span class="tag">Shots 1-16 + quick 1-6</span> &mdash; store and recall
  pan/tilt/zoom/focus only (AbsolutePTZF); buttons 1-6 light up the shot
  matching the current camera position.</li>
<li><span class="tag">Camera presets</span> &mdash; grid 1-256 (BRC-AM7: 1-100):
  recall, save, clear, names, thumbnails taken from the camera frame.</li>
<li><span class="tag">Image</span> &mdash; exposure (mode, iris, gain, shutter,
  compensation) and white balance (mode, gains, offset); values in camera units
  (F, dB / EV, 1/..., frames).</li>
<li><span class="tag">Network</span> &mdash; camera discovery (ARP, SSDP, UDP 52380);
  IP / mask / gateway / name change over UDP (SET + ACK/NAK); RM-IP500 panel slot
  table read; Sony-format CSV import/export.</li>
<li><span class="tag">Log</span> &mdash; commands, replies and errors at the bottom
  of the main window.</li>
</ul>

<h4>MODELS</h4>
<ul>
<li><span class="tag">SRG-X400 / BRC-X400</span> &mdash; verified on SRG-X400
  (HTTP CGI with digest auth, port 80).</li>
<li><span class="tag">BRC-AM7</span> &mdash; mapped per Sony &bdquo;CGI Command List&rdquo; v2.0;
  model detected via inq=viewermode. Command set not yet verified on hardware.</li>
</ul>

<h4>BRC-AM7 &mdash; DIFFERENCES</h4>
<ul>
<li>Focus Near/Far in steps (AbsoluteFocus); no continuous focus movement over CGI.</li>
<li>Presets 1-100; recall by number only, no speed.</li>
<li>No ExposureMode: three auto switches (shutter / iris / AGC); the app
  combines them into auto / shutter / iris / manual modes.</li>
<li>Scales: iris CLOSE / F2.8-F11, gain -9 to +36 dB, shutter 50p (1/50-1/8000,
  64F-2F), angles in 0.001 deg steps, zoom up to 25x.</li>
<li>White balance: atw / memory_a / preset. One Push AF/WB as press+release.</li>
</ul>

<h4>LIMITATIONS</h4>
<ul>
<li>No video preview; the image goes from the camera over SDI/HDMI.</li>
<li>UDP SET works only with WRITE:on in the camera; WRITE state is shown in the
  device tooltip in the list.</li>
<li>RM-IP500 panel table: read and CSV export; no write to the panel.</li>
<li>Shots do not include exposure, white balance or colours.</li>
<li>Cameras unreachable on the network do not restore their tabs at startup.</li>
</ul>
<p class="dim">Control: HTTP CGI (Digest), camera port 80. Discovery and network SET: UDP 52380.</p>
"""


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About")
        self.resize(780, 640)
        v = QVBoxLayout(self)
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(10)
        tb = QTextBrowser()
        tb.setOpenExternalLinks(False)
        tb.setHtml(ABOUT_HTML.replace("{{VERSION}}", APP_VERSION))
        v.addWidget(tb, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        b = QPushButton("Close")
        b.setMinimumWidth(130)
        b.clicked.connect(self.accept)
        row.addWidget(b)
        v.addLayout(row)


class ScanWorker(QThread):
    done = Signal(list)
    prog = Signal(int, int)
    step = Signal(str)

    def __init__(self, mode, cidr, user, password, known=()):
        super().__init__()
        self.mode = mode
        self.cidr = cidr
        self.user = user
        self.password = password
        self.known = list(known)
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        if self.mode == "fast":
            # faza 1/4: kandydaci z ARP (szybkie trafienia najpierw)
            try:
                self.step.emit("Scan: ARP table...")
                self.prog.emit(3, 100)
                arp = [h["ip"] for h in bridge.arp_candidates(None)]
            except Exception:
                arp = []
            if self._stop:
                self.done.emit([])
                return
            # faza 2/4: SSDP (multicast, ~2 s)
            try:
                self.step.emit("Scan: SSDP/UPnP listening...")
                self.prog.emit(8, 100)
                ssdp = [h["ip"] for h in bridge.ssdp_search(timeout=2.0)]
            except Exception:
                ssdp = []
            if self._stop:
                self.done.emit([])
                return
            # znane + ARP najpierw (trafienia od razu), domyslne na koncu
            targets = list(dict.fromkeys(
                list(self.known) + arp + ssdp + list(disc.LIKELY_DEFAULTS)))
            # faza 3/4: sondowanie TCP + rownolegle UDP ENQ:network (52380)
            self.step.emit(f"Scan: probing ({len(targets)} addresses)...")
            with ThreadPoolExecutor(max_workers=1) as uex:
                fut_udp = self._start_udp(uex)
                out = disc.probe_many(
                    targets, self.user, self.password,
                    progress=lambda d, t: (self.prog.emit(12 + 88 * d // max(1, t), 100),
                                           self.step.emit(f"Scan: {d}/{t}...")))
                out = disc.merge_udp(out, self._udp_result(fut_udp))
        else:
            self.step.emit("Scan: UDP 52380...")
            with ThreadPoolExecutor(max_workers=1) as uex:
                fut_udp = self._start_udp(uex)
                out = disc.scan_subnet(self.cidr, self.user, self.password,
                                       progress=lambda d, t: self.prog.emit(d, t),
                                       stop_flag=lambda: self._stop)
                out = disc.merge_udp(out, self._udp_result(fut_udp))
        self.done.emit(out)

    def _start_udp(self, ex: ThreadPoolExecutor):
        """UDP ENQ:network (52380) - rownolegle z TCP, znajduje tez kamery
        z innym IP w tym samym segmencie L2."""
        try:
            homes = bridge.guess_homes([{"ip": ip} for ip in self.known])
            extra = [h + ".255" for h in homes]
        except Exception:
            extra = []
        try:
            return ex.submit(disc.udp_discover, 2.0, extra,
                             lambda s: self.step.emit("Scan: " + str(s)))
        except Exception:
            return None

    def _udp_result(self, fut) -> list[dict]:
        if fut is None:
            return []
        try:
            return fut.result(timeout=3.0) or []
        except Exception:
            return []


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RM IP++")
        self.resize(1360, 820)
        self.config = cfg.load()
        self.user = self.config.get("user", DEFAULT_USER)
        self.password = self.config.get("password", DEFAULT_PASSWORD)
        self.cams: list[dict] = []
        self.worker: ScanWorker | None = None
        self.edge = ev.EdgeTabs()

        root = QWidget()
        self.setCentralWidget(root)
        v = QVBoxLayout(root)
        v.setContentsMargins(12, 10, 12, 10)
        v.setSpacing(10)

        top = QHBoxLayout()
        top.setSpacing(8)
        v.addLayout(top)
        self.btn_fast = QPushButton("Scan")
        self.btn_fast.setMinimumHeight(32)
        self.btn_fast.setToolTip("Rescan the network (ARP, SSDP, UDP 52380).")
        self.btn_fast.clicked.connect(lambda: self.start_scan("fast"))
        top.addWidget(self.btn_fast)
        self.btn_stop = QPushButton("Stop")
        self.btn_stop.setToolTip("Stop the current scan.")
        self.btn_stop.clicked.connect(self.on_stop)
        self.btn_stop.setEnabled(False)
        self.btn_stop.setVisible(False)
        top.addWidget(self.btn_stop)
        self.lbl = QLabel("Starting scan...")
        self.lbl.setStyleSheet("color: #9aa0a6;")
        self.lbl.setWordWrap(True)
        top.addWidget(self.lbl, 1)
        self.prog = QProgressBar()
        self.prog.setMaximumWidth(220)
        self.prog.setMinimumHeight(14)
        self.prog.setTextVisible(True)
        self.prog.setFormat("%p%")
        self.prog.setVisible(False)
        top.addWidget(self.prog)
        self.btn_adv = QPushButton("Advanced ▸")
        self.btn_adv.setCheckable(True)
        self.btn_adv.setChecked(False)
        self.btn_adv.setToolTip("Show or hide advanced network options.")
        self.btn_adv.toggled.connect(self.toggle_adv)
        top.addWidget(self.btn_adv)

        # pasek zaawansowany (domyslnie schowany)
        self.adv = QWidget()
        self.adv.setObjectName("adv")
        adv_lay = QVBoxLayout(self.adv)
        adv_lay.setContentsMargins(14, 12, 14, 12)
        adv_lay.setSpacing(10)
        v.addWidget(self.adv)
        ar1 = QHBoxLayout()
        adv_lay.addLayout(ar1)
        ar1.addWidget(QLabel("Subnet (CIDR):"))
        self.e_cidr = QLineEdit(self.config.get("scan_cidr", "192.168.0.0/24"))
        self.e_cidr.setMaximumWidth(150)
        self.e_cidr.setToolTip("Subnet to scan, e.g. 192.168.4.0/24.")
        ar1.addWidget(self.e_cidr)
        self.btn_full = QPushButton("Scan subnet")
        self.btn_full.setToolTip("Scan the whole subnet address by address (slower).")
        self.btn_full.clicked.connect(lambda: self.start_scan("full"))
        ar1.addWidget(self.btn_full)
        self.btn_bridge = QPushButton("Bridge unreachable")
        self.btn_bridge.setToolTip(
            "Add temporary IPs on Ethernet for unreachable cameras (one UAC prompt).\n"
            "Wi-Fi stays online.")
        self.btn_bridge.clicked.connect(self.on_bridge)
        ar1.addWidget(self.btn_bridge)
        ar1.addStretch(1)
        ar2 = QHBoxLayout()
        adv_lay.addLayout(ar2)
        ar2.addWidget(QLabel("Login:"))
        self.e_user = QLineEdit(self.user)
        self.e_user.setMaximumWidth(110)
        self.e_user.setToolTip("Camera login (default: admin).")
        ar2.addWidget(self.e_user)
        ar2.addWidget(QLabel("Password:"))
        self.e_pass = QLineEdit(self.password)
        self.e_pass.setEchoMode(QLineEdit.Password)
        self.e_pass.setMaximumWidth(130)
        self.e_pass.setToolTip("Camera password (default: admin).")
        ar2.addWidget(self.e_pass)
        self.btn_diag = QPushButton("Check connection")
        self.btn_diag.setToolTip("Ping and test HTTP/VISCA ports on the selected camera.")
        self.btn_diag.clicked.connect(self.on_diag)
        ar2.addWidget(self.btn_diag)
        self.net_lbl = QLabel()
        self.net_lbl.setStyleSheet("color: #9aa0a6;")
        ar2.addWidget(self.net_lbl, 1)
        self.update_net_label()
        self.adv.setVisible(False)

        split = QSplitter(Qt.Horizontal)
        split.setHandleWidth(6)
        v.addWidget(split, 1)

        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(8)
        devrow = QHBoxLayout()
        lv.addLayout(devrow)
        self.dev_title = QLabel("Devices")
        f = self.dev_title.font()
        f.setPointSize(11)
        f.setBold(True)
        self.dev_title.setFont(f)
        devrow.addWidget(self.dev_title)
        devrow.addStretch(1)
        self.cam_table = QTableWidget(0, 5)
        self.cam_table.setHorizontalHeaderLabels(["IP", "Model", "HTTP", "VISCA", "Panel"])
        for i in (0, 1):
            it = self.cam_table.horizontalHeaderItem(i)
            if it is not None:
                it.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        hh = self.cam_table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        for i, wdt in ((2, 66), (3, 66), (4, 96)):
            hh.setSectionResizeMode(i, QHeaderView.Fixed)
            self.cam_table.setColumnWidth(i, wdt)
        self.cam_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.cam_table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.cam_table.setAlternatingRowColors(True)
        self.cam_table.verticalHeader().setDefaultSectionSize(34)
        self.cam_table.verticalHeader().setFixedWidth(28)
        f = self.cam_table.font()
        f.setPointSize(11)
        self.cam_table.setFont(f)
        self.cam_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.cam_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.cam_table.customContextMenuRequested.connect(self.dev_menu)
        self.cam_table.doubleClicked.connect(self.open_web_tab)
        self.cam_empty = _CenterHint("No devices.", self.cam_table.viewport())
        lv.addWidget(self.cam_table, 1)
        devbtn = QHBoxLayout()
        devbtn.setSpacing(8)
        lv.addLayout(devbtn)
        self.btn_addip = QPushButton("Add IP...")
        self.btn_addip.setToolTip("Add a camera by IP address.")
        self.btn_addip.clicked.connect(self.add_manual_ip)
        devbtn.addWidget(self.btn_addip)
        self.btn_all = QPushButton("Control all")
        self.btn_all.setToolTip("Open control tabs for all cameras in the list.")
        self.btn_all.clicked.connect(self.open_all_tabs)
        devbtn.addWidget(self.btn_all)
        devbtn2 = QHBoxLayout()
        devbtn2.setSpacing(8)
        lv.addLayout(devbtn2)
        self.btn_udpnet = QPushButton("Camera network…")
        self.btn_udpnet.setToolTip("Change camera IP, mask, gateway and name over UDP 52380.")
        self.btn_udpnet.clicked.connect(self.open_udp_write)
        devbtn2.addWidget(self.btn_udpnet)
        self.btn_camtable = QPushButton("Panel table…")
        self.btn_camtable.setToolTip("Read the RM-IP500 panel camera table.")
        self.btn_camtable.clicked.connect(self.open_camtable)
        devbtn2.addWidget(self.btn_camtable)
        self.btn_csv = QPushButton("CSV…")
        self.btn_csv.setToolTip("Import or export the camera list in Sony CSV format.")
        self.btn_csv.clicked.connect(self.csv_menu)
        devbtn2.addWidget(self.btn_csv)
        self.btn_about = QPushButton("About")
        self.btn_about.setToolTip("Version, features and limitations.")
        self.btn_about.clicked.connect(self.show_about)
        devbtn2.addWidget(self.btn_about)
        split.addWidget(left)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(8)
        self.ctrl_tabs = QTabWidget()
        self.ctrl_tabs.setTabsClosable(True)
        self.ctrl_tabs.tabCloseRequested.connect(self.close_ctrl_tab)
        rv.addWidget(self.ctrl_tabs, 3)
        row = QHBoxLayout()
        row.setSpacing(8)
        rv.addLayout(row)
        self.btn_add = QPushButton("Control selected")
        self.btn_add.setToolTip("Open the control tab for the selected camera.")
        self.btn_add.clicked.connect(self.add_ctrl_tab)
        row.addWidget(self.btn_add)
        self.btn_web = QPushButton("Open in Edge")
        self.btn_web.setToolTip("Open the camera web UI in Edge (app window).")
        self.btn_web.clicked.connect(self.open_external)
        row.addWidget(self.btn_web)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(500)
        self.log.setPlaceholderText("Log...")
        self.log.setMaximumHeight(130)
        rv.addWidget(self.log)
        split.addWidget(right)
        split.setSizes([400, 750])

        sb = QStatusBar()
        self.setStatusBar(sb)
        if nm.is_admin():
            sb.showMessage("ADMIN")

        atexit.register(nm.cleanup_all)
        self.check_orphans()
        self.log_line("Start. " + diag.env_report())
        # start: najpierw most dla znanych kamer (jedno UAC), potem autoskan
        QTimer.singleShot(800, self._startup)

    def _startup(self):
        known = self.config.get("known_ips", [])
        if known:
            iface = nm.best_bridge_iface()
            if iface:
                # Most tylko dla nieosiagalnych: IP z biezacej podsieci (np. w sieci
                # hotelowej router z LIKELY_DEFAULTS) nie moze dostac dodatkowego
                # adresu na Ethernet - inaczej trasa do wlasnej podsieci sie miesza,
                # a Internet ma zostac na WiFi.
                with ThreadPoolExecutor(max_workers=8) as ex:
                    reach = dict(zip(known, ex.map(nm.tcp_reachable, known)))
                need = [ip for ip in known if not reach.get(ip)]
                if need:
                    self.log_line(f"Start: restoring the bridge for {need} on '{iface}'...")
                    try:
                        ok, msg = nm.ensure_homes_visible(iface, need)
                    except Exception as e:
                        ok, msg = False, str(e)[:200]
                    self.log_line("Startup bridge: " + msg)
                    self.update_net_label()
        self.start_scan("fast")

    def toggle_adv(self, on: bool):
        self.adv.setVisible(on)
        self.btn_adv.setText("Advanced ▾" if on else "Advanced ▸")

    def log_line(self, t: str):
        from html import escape
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self.log.appendHtml(
            f'<span style="color:#6f757c">[{ts}]</span> '
            f'<span style="color:#d8dade">{escape(str(t))}</span>')

    def update_net_label(self):
        try:
            bi = nm.best_bridge_iface() or "no Ethernet"
            n = len(nm._load_state())
            n_txt = str(n) if n else "none"
            self.net_lbl.setText(f"Auto bridge: {bi} | temp IP: {n_txt}")
        except Exception:
            pass

    def check_orphans(self):
        orph = nm.find_orphans()
        if orph:
            txt = "\n".join(f"{o['interface_alias']} {o['ip']}/{o['prefix']}" for o in orph)
            if QMessageBox.question(self, "Leftover IPs from the previous session",
                                    f"Temporary IPs found:\n{txt}\nRemove?") == QMessageBox.Yes:
                msgs = nm.cleanup_all()
                self.log_line("Cleanup: " + " | ".join(msgs))
                self.update_net_label()

    def closeEvent(self, ev):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(3000)
        for i in range(self.ctrl_tabs.count()):  # domknij polling statusu w kartach
            wdg = self.ctrl_tabs.widget(i)
            if hasattr(wdg, "shutdown"):
                wdg.shutdown()
        # sprzatanie w tle - zamkniecie nigdy nie wisi na UAC
        import threading
        threading.Thread(target=nm.cleanup_all, daemon=True).start()
        self.config.update({"user": self.e_user.text(), "password": self.e_pass.text(),
                            "scan_cidr": self.e_cidr.text()})
        cfg.save(self.config)
        super().closeEvent(ev)

    def on_bridge(self):
        """Automat: dla kazdej widocznej (ARP/SSDP/znanej) lecz nieosiagalnej kamery
        dobuduj most na fizycznym Ethernecie. Bez wyboru karty."""
        self.user = self.e_user.text().strip() or DEFAULT_USER
        self.password = self.e_pass.text()
        cands = list(self.config.get("known_ips", []))
        try:
            cands += [h["ip"] for h in bridge.arp_candidates(None)]
            cands += [h["ip"] for h in bridge.ssdp_search(timeout=3.0)]
        except Exception:
            pass
        cands = list(dict.fromkeys(cands))
        if not cands:
            QMessageBox.information(self, "Bridge", "No candidates (ARP/SSDP empty).")
            return
        for ip in cands:
            ok, msg = nm.ensure_reachable(ip)
            self.log_line(f"Bridge {ip}: {msg}")
        self.update_net_label()
        self.start_scan("fast")

    def start_scan(self, mode):
        self.user = self.e_user.text().strip() or DEFAULT_USER
        self.password = self.e_pass.text()
        # nigdy dwa skany naraz (stary worker porywal sygnaly + crash przy GC)
        self._scan_gen = getattr(self, "_scan_gen", 0) + 1
        my_gen = self._scan_gen
        if self.worker is not None:
            for sig in ("done", "prog", "step"):
                try:
                    getattr(self.worker, sig).disconnect()
                except Exception:
                    pass
            if self.worker.isRunning():
                self.log_line("Waiting for the previous scan to finish...")
                self.worker.stop()
                self.worker.wait(8000)
        self.prog.setVisible(True)
        self.prog.setRange(0, 100)
        self.prog.setValue(0)
        self.btn_stop.setEnabled(True)
        self.btn_stop.setVisible(True)
        self.btn_fast.setEnabled(False)
        self.lbl.setText("Scanning...")
        self.log_line(f"Scan {mode} (cidr={self.e_cidr.text()}).")
        self.worker = ScanWorker(mode, self.e_cidr.text().strip(), self.user, self.password,
                                 known=self.config.get("known_ips", []))
        self.worker.done.connect(lambda found, g=my_gen: self.on_scan_done(found, g))
        self.worker.prog.connect(lambda d, t: (self.prog.setMaximum(t), self.prog.setValue(d)))
        self.worker.step.connect(self.lbl.setText)
        self.worker.start()

    def on_stop(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.log_line("Scan stopped.")

    def on_scan_done(self, found, gen=None):
        if gen is not None and gen != getattr(self, "_scan_gen", gen):
            return  # przestarzaly skan - ignoruj
        self.prog.setVisible(False)
        self.btn_stop.setEnabled(False)
        self.btn_stop.setVisible(False)
        self.btn_fast.setEnabled(True)
        self.cams = sorted(found, key=lambda d: d["ip"])
        self.cam_table.setRowCount(len(self.cams))
        self.cam_table.setVerticalHeaderLabels([str(i + 1) for i in range(len(self.cams))])
        for r in range(len(self.cams)):
            it = self.cam_table.verticalHeaderItem(r)
            if it is not None:
                it.setTextAlignment(Qt.AlignCenter)
        for r, c in enumerate(self.cams):
            up = bool(c.get("http"))
            ip_item = QTableWidgetItem(("● " if up else "○ ") + c["ip"])
            ip_item.setForeground(QColor("#8fce8f") if up else QColor("#8a8f96"))
            tip = c["ip"]
            u = c.get("udp") or {}
            if u:
                tip += (f"\nUDP 52380: {u.get('model') or '?'} · MAC {u.get('mac') or '?'} · "
                        f"FW {u.get('softversion') or '?'} · WRITE:{u.get('writable') or '?'}")
            if c.get("note"):
                tip += "\n" + str(c["note"])
            ip_item.setToolTip(tip)
            self.cam_table.setItem(r, 0, ip_item)
            self.cam_table.setItem(r, 1, QTableWidgetItem(str(c.get("model", "?"))))
            for col, ok in ((2, c.get("http")), (3, c.get("visca_52381"))):
                it = QTableWidgetItem("yes" if ok else "no")
                it.setTextAlignment(Qt.AlignCenter)
                it.setForeground(QColor("#8fce8f") if ok else QColor("#8a8f96"))
                self.cam_table.setItem(r, col, it)
            self.cam_table.setItem(r, 4, QTableWidgetItem(""))
        self.refresh_panel_col()
        self._refresh_tab_labels()
        self.dev_title.setText(f"Devices ({len(self.cams)})")
        self.cam_empty.setVisible(not self.cams)
        self.cam_empty.raise_()
        n = len(found)
        self.lbl.setText(f"Found: {n}")
        self.log_line(f"Scan done: {[c['ip'] for c in found]}")
        if not getattr(self, "_restored", False):
            self._restored = True
            self.restore_tabs()
        try:
            known = list(dict.fromkeys(list(self.config.get("known_ips", [])) + [c["ip"] for c in found]))[:20]
            self.config["known_ips"] = known
            cfg.save(self.config)
        except Exception:
            pass

    def selected_ip(self):
        r = self.cam_table.currentRow()
        if 0 <= r < len(self.cams):
            return self.cams[r]["ip"]
        return None

    def selected_ips(self):
        rows = sorted({i.row() for i in self.cam_table.selectedIndexes()})
        return [self.cams[r]["ip"] for r in rows if 0 <= r < len(self.cams)]

    def refresh_panel_col(self):
        open_ips = set(self.ctrl_ips())
        for r, c in enumerate(self.cams):
            opened = c["ip"] in open_ips
            item = QTableWidgetItem("open" if opened else "—")
            item.setTextAlignment(Qt.AlignCenter)
            item.setForeground(QColor("#ffb14e") if opened else QColor("#6f757c"))
            self.cam_table.setItem(r, 4, item)

    def dev_menu(self, pos):
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        a1 = menu.addAction("Control")
        a2 = menu.addAction("Open in Edge")
        a3 = menu.addAction("Check connection")
        a4 = menu.addAction("Forget IP")
        act = menu.exec(self.cam_table.viewport().mapToGlobal(pos))
        if act == a1:
            self.add_ctrl_tab()
        elif act == a2:
            self.open_external()
        elif act == a3:
            self.on_diag()
        elif act == a4:
            self.forget_selected()

    def forget_selected(self):
        ips = set(self.selected_ips())
        if not ips:
            return
        self.cams = [c for c in self.cams if c["ip"] not in ips]
        try:
            self.config["known_ips"] = [x for x in self.config.get("known_ips", []) if x not in ips]
            cfg.save(self.config)
        except Exception:
            pass
        self.on_scan_done(self.cams)
        self.log_line(f"Forgotten: {sorted(ips)}")

    def add_manual_ip(self):
        from PySide6.QtWidgets import QInputDialog
        ip, ok = QInputDialog.getText(self, "Add IP", "Camera address (e.g. 192.168.4.101):")
        if not ok or not ip.strip():
            return
        ip = ip.strip()
        import re as _re
        if not _re.match(r"^\d{1,3}(\.\d{1,3}){3}(:\d+)?$", ip):
            QMessageBox.warning(self, "Add IP", "This does not look like an IPv4 address.")
            return
        self.log_line(f"Probing {ip}...")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            hit = disc.probe_ip(ip, self.e_user.text().strip() or DEFAULT_USER, self.e_pass.text())
        finally:
            QApplication.restoreOverrideCursor()
        if not hit:
            okm, msg = nm.ensure_reachable(ip)
            self.log_line(f"Bridge for {ip}: {msg}")
            if okm:
                hit = disc.probe_ip(ip, self.e_user.text().strip() or DEFAULT_USER, self.e_pass.text())
        if hit:
            if all(c["ip"] != hit["ip"] for c in self.cams):
                self.cams.append(hit)
            self.on_scan_done(self.cams)
            self.log_line(f"Added {hit['ip']}.")
        else:
            QMessageBox.warning(self, "Add IP", f"{ip} does not respond (HTTP/VISCA).")

    def open_all_tabs(self):
        for c in self.cams:
            self.add_ctrl_tab(c["ip"])

    def open_web_tab(self):
        # dwuklik = od razu sterowanie (zakladka w aplikacji)
        self.add_ctrl_tab()

    def ctrl_ips(self):
        out = []
        for i in range(self.ctrl_tabs.count()):
            wdg = self.ctrl_tabs.widget(i)
            out.append((wdg.property("ip") if wdg is not None else None)
                       or self.ctrl_tabs.tabText(i))
        return out

    def _tab_label(self, ip: str) -> str:
        return next((str(c.get("model") or "") for c in self.cams if c["ip"] == ip), "") or ip

    def _refresh_tab_labels(self):
        for i in range(self.ctrl_tabs.count()):
            wdg = self.ctrl_tabs.widget(i)
            ip = (wdg.property("ip") if wdg is not None else None) or self.ctrl_tabs.tabText(i)
            self.ctrl_tabs.setTabText(i, self._tab_label(ip))

    def add_ctrl_tab(self, ip=None):
        try:
            from .ui_control import CameraTab
        except ImportError:
            from ui_control import CameraTab  # noqa: E402
        ip = ip or self.selected_ip()
        if not ip:
            QMessageBox.warning(self, "No selection", "Select a camera in the table.")
            return
        if ip in self.ctrl_ips():
            self.ctrl_tabs.setCurrentIndex(self.ctrl_ips().index(ip))
            return
        port = next((c.get("http_port", 80) for c in self.cams if c["ip"] == ip), 80)
        http = bool(next((c.get("http") for c in self.cams if c["ip"] == ip), False))
        tab = CameraTab(ip, self.e_user.text().strip() or DEFAULT_USER,
                        self.e_pass.text(), http_port=port, log=self.log_line,
                        frames=self.config.get("frames", {}).get(ip),
                        save_frames=lambda: self.save_frames(ip), reachable=http)
        tab.setProperty("ip", ip)
        idx = self.ctrl_tabs.addTab(tab, self._tab_label(ip))
        self.ctrl_tabs.setTabToolTip(idx, f"{ip} · CGI control")
        self.ctrl_tabs.setCurrentWidget(tab)
        self.log_line(f"Control tab added for {ip}.")
        self.refresh_panel_col()
        self.save_open_tabs()

    def save_frames(self, ip):
        try:
            for i in range(self.ctrl_tabs.count()):
                if self.ctrl_tabs.tabText(i) == ip:
                    tab = self.ctrl_tabs.widget(i)
                    fr = self.config.get("frames", {})
                    fr[ip] = tab.frames
                    self.config["frames"] = fr
                    cfg.save(self.config)
                    break
        except Exception:
            pass

    def close_ctrl_tab(self, i):
        wdg = self.ctrl_tabs.widget(i)
        if hasattr(wdg, "shutdown"):
            wdg.shutdown()
        self.ctrl_tabs.removeTab(i)
        self.refresh_panel_col()
        self.save_open_tabs()

    def save_open_tabs(self):
        try:
            self.config["open_tabs"] = self.ctrl_ips()
            cfg.save(self.config)
        except Exception:
            pass

    def restore_tabs(self):
        try:
            from .ui_control import CameraTab
        except ImportError:
            from ui_control import CameraTab  # noqa: E402
        found = {c["ip"] for c in self.cams}
        for ip in self.config.get("open_tabs", []):
            if ip in self.ctrl_ips():
                continue  # juz otwarta (np. dodana recznie tuz po skanie)
            if ip not in found:
                # kamera nie odpowiada (inna siec) - zakladka zamulalaby okno
                self.log_line(f"Skipping tab {ip} (camera not responding).")
                continue
            try:
                port = next((c.get("http_port", 80) for c in self.cams if c["ip"] == ip), 80)
                http = bool(next((c.get("http") for c in self.cams if c["ip"] == ip), False))
                tab = CameraTab(ip, self.e_user.text().strip() or DEFAULT_USER,
                                self.e_pass.text(), http_port=port, log=self.log_line,
                                frames=self.config.get("frames", {}).get(ip),
                                save_frames=lambda ip=ip: self.save_frames(ip),
                                reachable=http)
                tab.setProperty("ip", ip)
                idx = self.ctrl_tabs.addTab(tab, self._tab_label(ip))
                self.ctrl_tabs.setTabToolTip(idx, f"{ip} · CGI control")
            except Exception as e:
                self.log_line(f"Could not restore {ip}: {e}"[:150])
        self.refresh_panel_col()

    def open_external(self):
        ip = self.selected_ip()
        if not ip:
            QMessageBox.warning(self, "No selection", "Select a camera in the table.")
            return
        port = next((c.get("http_port", 80) for c in self.cams if c["ip"] == ip), 80)
        how, msg = self.edge.open(ip, port)
        if how == "no-browser":
            import webbrowser
            webbrowser.open(f"http://{ip}:{port}/")
            self.log_line(msg + " Opened in the default browser.")
        else:
            self.log_line(msg + (" (Edge will remember the password in the app profile.)"
                                 if how == "opened" else ""))

    def on_diag(self):
        ip = self.selected_ip()
        if not ip:
            QMessageBox.warning(self, "No selection", "Select a camera.")
            return
        ok_p, ping_msg = diag.ping(ip)
        h = diag.tcp_open(ip, 80)
        h8 = diag.tcp_open(ip, 8080)
        v = diag.tcp_open(ip, 52381)
        txt = (f"{ip}: ping={'OK' if ok_p else 'FAIL'} {ping_msg}\n"
               f"80={'open' if h else 'closed'} 8080={'open' if h8 else 'closed'} "
               f"VISCA 52381={'open' if v else 'closed'}")
        self.log_line(txt.replace("\n", " | "))
        QMessageBox.information(self, "Connection", txt)

    # -- UDP: SET sieci + tabela panelu + CSV (formaty Sony) -----------------
    def _dev_defaults(self, ip: str) -> dict:
        """Wartosci do prefillu dialogu UDP z danych skanu (UDP > CGI)."""
        c = next((x for x in self.cams if x["ip"] == ip), None) or {}
        u = c.get("udp") or {}
        net = c.get("network") if isinstance(c.get("network"), dict) else {}
        writable = None
        if u:
            writable = (u.get("writable") or "") == "on"
        return {"mac": u.get("mac") or "",
                "ip": c.get("ip", "") or "",
                "mask": u.get("mask") or "255.255.255.0",
                "gateway": u.get("gateway") or "",
                "name": u.get("name") or net.get("CameraName") or "",
                "writable": writable}

    def open_udp_write(self):
        try:
            from .ui_udp import WriteNetDialog
        except ImportError:
            from ui_udp import WriteNetDialog  # noqa: E402
        ip = self.selected_ip()
        if not ip:
            QMessageBox.warning(self, "No selection", "Select a camera in the table.")
            return
        dlg = WriteNetDialog(self, defaults=self._dev_defaults(ip), old_ip=ip)
        dlg.applied.connect(self.on_udp_write_applied)
        dlg.exec()

    def on_udp_write_applied(self, info: dict):
        old_ip = (info or {}).get("old_ip") or ""
        new_ip = (info or {}).get("ip") or ""
        if new_ip and new_ip != old_ip:
            try:
                known = [x for x in self.config.get("known_ips", []) if x != old_ip]
                if new_ip not in known:
                    known.append(new_ip)
                self.config["known_ips"] = known[:20]
                self.config["open_tabs"] = [new_ip if t == old_ip else t
                                            for t in self.config.get("open_tabs", [])]
                cfg.save(self.config)
            except Exception:
                pass
        self.log_line(f"UDP SET: ACK confirmed, {old_ip} -> {new_ip}.")
        QMessageBox.information(
            self, "UDP SET",
            f"Camera confirmed the change (ACK):\n\n  {old_ip}  ->  {new_ip}")
        QTimer.singleShot(900, lambda: self.start_scan("fast"))

    def open_camtable(self):
        try:
            from .ui_udp import CamtableDialog
        except ImportError:
            from ui_udp import CamtableDialog  # noqa: E402
        dlg = CamtableDialog(self)
        dlg.exec()

    def show_about(self):
        dlg = AboutDialog(self)
        dlg.exec()

    def csv_menu(self):
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        a1 = menu.addAction("Export camera list (CSV)...")
        a2 = menu.addAction("Import camera list (CSV)...")
        act = menu.exec(self.btn_csv.mapToGlobal(self.btn_csv.rect().center()))
        if act == a1:
            self.export_camera_csv()
        elif act == a2:
            self.import_camera_csv()

    def _cam_csv_row(self, c: dict) -> dict:
        u = c.get("udp") or {}
        net = c.get("network") if isinstance(c.get("network"), dict) else {}
        return {"name": u.get("name") or net.get("CameraName") or "",
                "mac": u.get("mac") or net.get("MACAddress") or net.get("MAC") or "",
                "ip": c.get("ip", ""),
                "mask": u.get("mask") or "255.255.255.0",
                "gateway": u.get("gateway") or "",
                "version": u.get("softversion") or net.get("SoftVersion") or ""}

    def export_camera_csv(self):
        if not self.cams:
            QMessageBox.information(self, "CSV", "Device list is empty.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export camera list (CSV)", "rmip_cameras.csv",
            "CSV (*.csv);;All files (*)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(sony_csv.camera_csv_text([self._cam_csv_row(c) for c in self.cams]))
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "CSV", f"Could not save: {e}")
            return
        self.log_line(f"CSV: saved {len(self.cams)} cameras -> {path}")
        QMessageBox.information(self, "CSV", f"Saved {len(self.cams)} rows:\n{path}")

    def import_camera_csv(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import camera list (CSV)", "", "CSV (*.csv);;All files (*)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
                text = f.read()
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "CSV", f"Could not load: {e}")
            return
        parsed = sony_csv.parse_camera_csv(text)
        rows = parsed["rows"]
        if parsed["warnings"]:
            extra = ("" if len(parsed["warnings"]) <= 12
                     else f"\n... and {len(parsed['warnings']) - 12} more")
            QMessageBox.warning(self, "CSV - warnings",
                                "\n".join(parsed["warnings"][:12]) + extra)
        if not rows:
            QMessageBox.warning(self, "CSV", "File contains no camera rows.")
            return
        by_ip = {c["ip"]: c for c in self.cams}
        ips: list[str] = []
        added = 0
        for r in rows:
            ip = (r.get("ip") or "").strip()
            if not sony_udp.is_ipv4(ip):
                continue
            ips.append(ip)
            cam = by_ip.get(ip)
            if cam is not None:
                cam.setdefault("csv", r)
                continue
            cam = {"ip": ip, "http": False, "http_port": 0, "visca_52381": False,
                   "model": r.get("name") or "?", "csv": r,
                   "note": f"from CSV: MAC {r.get('mac') or '?'} FW {r.get('version') or '?'}"}
            self.cams.append(cam)
            by_ip[ip] = cam
            added += 1
        try:
            known = list(dict.fromkeys(list(self.config.get("known_ips", [])) + ips))[:40]
            self.config["known_ips"] = known
            cfg.save(self.config)
        except Exception:
            pass
        self.on_scan_done(list(self.cams))
        self.log_line(f"CSV: loaded {len(rows)} rows ({added} new on the list).")
        QMessageBox.information(
            self, "CSV",
            f"Loaded {len(rows)} cameras from the file. New on the list: {added}.")
        self.start_scan("fast")


def app_icon():
    """App icon from assets/icon.svg (vector: sharp at every size).

    Works both from source and from a PyInstaller bundle (sys._MEIPASS).
    """
    base = getattr(sys, "_MEIPASS", None)
    if base:
        candidates = [os.path.join(base, "assets", "icon.svg"),
                      os.path.join(base, "assets", "icon.ico")]
    else:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        candidates = [os.path.join(root, "assets", "icon.svg"),
                      os.path.join(root, "assets", "icon.ico")]
    for path in candidates:
        if os.path.exists(path):
            icon = QIcon(path)
            if not icon.isNull():
                return icon
    return QIcon()


def set_windows_app_id():
    """Windows: wlasny AppUserModelID, zeby taskbar bral ikone z okna (nie z pythona)."""
    if os.name != "nt":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "wertos97.RMIPPlusPlus")
    except Exception:
        pass


def run():
    import sys
    try:
        from .theme import apply_theme
    except ImportError:
        from theme import apply_theme  # noqa: E402
    set_windows_app_id()
    app = QApplication(sys.argv)
    apply_theme(app)
    app.setWindowIcon(app_icon())
    w = MainWindow()
    w.showMaximized()
    sys.exit(app.exec())

"""RM IP++: discover Sony cameras on the network + open connections (web tabs).

Zero configuration: no adapter choice (all interfaces at once, virtual ones
such as Bluetooth/cellular are ignored), the scan starts by itself on launch,
and the bridge is built automatically only when a camera is unreachable.
"""

from __future__ import annotations

import atexit
import datetime
import os
import sys
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QEvent, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QIcon

try:  # ensures the SVG icon engine plugin is bundled by PyInstaller
    from PySide6 import QtSvg  # noqa: F401
except Exception:
    pass
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

try:
    from . import config_store as cfg
    from . import creds as credman
    from . import diagnostics as diag
    from . import discovery as disc
    from . import edge_view as ev
    from . import net_manager as nm
    from . import sony_csv, sony_udp
    from . import subnet_bridge as bridge
    from .demo_api import DEMO_IP, DemoCameraAPI
    from .ui_creds import CredentialsDialog
    from .version import __version__ as APP_VERSION

    if os.name == "nt":
        from .win_shortcut import ensure_shortcut
    else:

        def ensure_shortcut(*args, **kwargs):
            return False
except ImportError:
    import config_store as cfg  # noqa: E402
    import creds as credman  # noqa: E402
    import diagnostics as diag  # noqa: E402
    import discovery as disc  # noqa: E402
    import edge_view as ev  # noqa: E402
    import net_manager as nm  # noqa: E402
    import sony_csv  # noqa: E402
    import sony_udp  # noqa: E402
    import subnet_bridge as bridge  # noqa: E402
    from demo_api import DEMO_IP, DemoCameraAPI  # noqa: E402
    from ui_creds import CredentialsDialog  # noqa: E402
    from version import __version__ as APP_VERSION  # noqa: E402

    if os.name == "nt":
        from win_shortcut import ensure_shortcut  # noqa: E402
    else:

        def ensure_shortcut(*args, **kwargs):
            return False


def tab_ip(widget, fallback: str = "") -> str:
    value = widget.property("ip") if widget is not None else None
    return str(value) if value else fallback


class _CenterHint(QLabel):
    """Gray text centered on the empty table - stretches with the viewport."""

    def __init__(self, text: str, viewport):
        super().__init__(text, viewport)
        self.setAlignment(Qt.AlignCenter)
        self.setWordWrap(True)
        self.setStyleSheet("color:#8b9198; font-size:12px; background:transparent;")
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
  h3 { color: #ff9e2c; margin: 2px 0; }
  h4 { color: #ff9e2c; margin: 16px 0 4px; }
  li { margin-bottom: 4px; }
  .dim { color: #9aa0a6; }
  .tag { color: #ffd9a0; font-weight: bold; }
</style>
<h3>RM IP++ &nbsp;<span class="dim" style="font-size:12px;">v{{VERSION}} &middot; Sony IP camera control</span></h3>
<p>Windows, PySide6. One window, one tab per camera. No video preview: the camera
feeds SDI/HDMI to a mixer. The app sends HTTP CGI (Digest) commands and reads camera state.</p>

<h4>Features</h4>
<ul>
<li><span class="tag">PTZ:</span> 8-way pad and Home. Drive moves while held
  (a short click lasts 0.5 s). Step moves once per click, then glides after 0.3 s.
  Speed 0-24, where 0 follows the current zoom.</li>
<li><span class="tag">Zoom and focus:</span> W/T at speed 0-8, Near/Far,
  One Push AF and auto/manual focus.</li>
<li><span class="tag">Shots:</span> 16 local positions and 6 quick shots store
  pan/tilt/zoom/focus only through AbsolutePTZF. A quick shot lights up when the
  camera reaches its position.</li>
<li><span class="tag">Camera presets:</span> 1-256 (BRC-AM7: 1-100) with recall,
  save, clear, names and thumbnails from the camera frame.</li>
<li><span class="tag">Image:</span> exposure and white balance with values shown
  in camera units such as F, dB, EV, shutter speed and frames.</li>
<li><span class="tag">Network:</span> ARP, SSDP and UDP 52380 discovery; IP, mask,
  gateway and name changes over UDP; RM-IP500 table read; Sony CSV import/export.</li>
<li><span class="tag">Login:</span> per-model defaults, with a prompt and per-IP
  storage when a camera rejects them.</li>
<li><span class="tag">Log:</span> commands, replies and errors in the main window.</li>
</ul>

<h4>Camera support</h4>
<ul>
<li><span class="tag">SRG-X400 / BRC-X400:</span> verified on SRG-X400 with
  HTTP CGI and Digest authentication on port 80.</li>
<li><span class="tag">BRC-AM7:</span> mapped from Sony CGI Command List v2.0 and
  detected through inq=system. Not yet verified on hardware.</li>
</ul>

<h4>BRC-AM7 differences</h4>
<ul>
<li>Focus Near/Far uses AbsoluteFocus steps. CGI has no continuous focus move.</li>
<li>Presets 1-100 recall by number. The camera controls recall speed.</li>
<li>Three auto switches replace ExposureMode: shutter, iris and AGC.</li>
<li>Units differ: iris CLOSE/F2.8-F11, gain -9 to +36 dB, 50p shutter,
  0.001 degree angles and zoom up to 25x.</li>
<li>White balance uses atw, memory_a or preset. One Push AF/WB uses press and release.</li>
<li>In ISO mode, Gain is camera-controlled and manual exposure reports a clear error.</li>
</ul>

<h4>Limitations</h4>
<ul>
<li>No video preview. Use the camera SDI/HDMI output.</li>
<li>UDP SET requires WRITE:on. The device tooltip shows the last reported state.</li>
<li>The RM-IP500 panel table supports read and CSV export, not write-back.</li>
<li>Shots store position only, not exposure, white balance or colour.</li>
<li>Tabs for unreachable cameras are not restored at startup.</li>
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
    error = Signal(str)
    prog = Signal(int, int)
    step = Signal(str)

    def __init__(self, mode, cidr, creds_for, known=()):
        super().__init__()
        self.mode = mode
        self.cidr = cidr
        self.creds_for = creds_for or (lambda ip: None)
        self.known = list(known)
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            self._run()
        except Exception as exc:
            self.error.emit(str(exc)[:300])

    def _run(self):
        if self.mode == "fast":
            try:
                self.step.emit("Scan: ARP table...")
                self.prog.emit(3, 100)
                arp = [h["ip"] for h in bridge.arp_candidates(None)]
            except Exception:
                arp = []
            if self._stop:
                self.done.emit([])
                return
            try:
                self.step.emit("Scan: SSDP/UPnP listening...")
                self.prog.emit(8, 100)
                ssdp = [h["ip"] for h in bridge.ssdp_search(timeout=2.0)]
            except Exception:
                ssdp = []
            if self._stop:
                self.done.emit([])
                return
            # known + ARP first (hits right away), defaults last
            targets = list(dict.fromkeys(list(self.known) + arp + ssdp + list(disc.LIKELY_DEFAULTS)))
            self.step.emit(f"Scan: probing ({len(targets)} addresses)...")
            with ThreadPoolExecutor(max_workers=1) as uex:
                fut_udp = self._start_udp(uex)
                out = disc.probe_many(
                    targets,
                    creds_for=self.creds_for,
                    progress=lambda d, t: (
                        self.prog.emit(12 + 88 * d // max(1, t), 100),
                        self.step.emit(f"Scan: {d}/{t}..."),
                    ),
                )
                out = disc.merge_udp(out, self._udp_result(fut_udp))
        else:
            self.step.emit("Scan: UDP 52380...")
            with ThreadPoolExecutor(max_workers=1) as uex:
                fut_udp = self._start_udp(uex)
                out = disc.scan_subnet(
                    self.cidr,
                    creds_for=self.creds_for,
                    progress=lambda d, t: self.prog.emit(d, t),
                    stop_flag=lambda: self._stop,
                )
                out = disc.merge_udp(out, self._udp_result(fut_udp))
        self.done.emit(out)

    def _start_udp(self, ex: ThreadPoolExecutor):
        """UDP ENQ:network (52380) - parallel with TCP, also finds cameras
        with a different IP in the same L2 segment."""
        try:
            homes = bridge.guess_homes([{"ip": ip} for ip in self.known])
            extra = [h + ".255" for h in homes]
        except Exception:
            extra = []
        try:
            return ex.submit(disc.udp_discover, 2.0, extra, lambda s: self.step.emit("Scan: " + str(s)))
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
        self._cred_skipped: set[str] = set()
        self._cred_prompt_active = False
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

        # advanced bar (hidden by default)
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
        self.e_cidr.setToolTip("Subnet to scan, e.g. 192.168.1.0/24.")
        ar1.addWidget(self.e_cidr)
        self.btn_full = QPushButton("Scan subnet")
        self.btn_full.setToolTip("Scan the whole subnet address by address (slower).")
        self.btn_full.clicked.connect(lambda: self.start_scan("full"))
        ar1.addWidget(self.btn_full)
        self.btn_bridge = QPushButton("Bridge unreachable")
        self.btn_bridge.setToolTip(
            "Add temporary IPs on Ethernet for unreachable cameras (one UAC prompt).\nWi-Fi stays online."
        )
        self.btn_bridge.clicked.connect(self.on_bridge)
        ar1.addWidget(self.btn_bridge)
        ar1.addStretch(1)
        ar2 = QHBoxLayout()
        adv_lay.addLayout(ar2)
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
        self.btn_demo = QPushButton("Add demo camera", self.cam_table.viewport())
        self.btn_demo.setCursor(Qt.PointingHandCursor)
        self.btn_demo.setStyleSheet(
            "QPushButton { color:#ffd9a0; background:#141619; border:1px solid #3a2c14;"
            " border-radius:5px; padding:5px 12px; }"
            "QPushButton:hover { border-color:#ff9e2c; }"
        )
        self.btn_demo.setToolTip("Add a simulated camera to explore the interface without hardware.")
        self.btn_demo.clicked.connect(self.add_demo_camera)
        self.btn_demo.hide()
        self.cam_table.viewport().installEventFilter(self)
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
        self.btn_web = QPushButton("Open in browser")
        self.btn_web.setToolTip("Open the camera web UI in a browser.")
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
        # start: first the bridge for known cameras (one UAC), then the auto-scan
        QTimer.singleShot(800, self._startup)

    def _startup(self):
        known = self.config.get("known_ips", [])
        if known:
            iface = nm.best_bridge_iface()
            if iface:
                # Bridge only for unreachable ones: an IP from the current subnet (e.g. a
                # hotel router from LIKELY_DEFAULTS) must not get an extra
                # address on Ethernet - otherwise the route to its own subnet gets mixed up,
                # and the Internet is supposed to stay on Wi-Fi.
                with ThreadPoolExecutor(max_workers=8) as ex:
                    reach = dict(zip(known, ex.map(nm.tcp_reachable, known), strict=True))
                need = [ip for ip in known if not reach.get(ip)]
                if need:
                    self.log_line(f"Start: restoring the bridge for {need} on '{iface}'...")
                    try:
                        ok, msg = nm.ensure_homes_visible(iface, need)
                    except Exception as e:
                        msg = str(e)[:200]
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
            f'<span style="color:#8b9198">[{ts}]</span> <span style="color:#d8dade">{escape(str(t))}</span>'
        )

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
            if (
                QMessageBox.question(
                    self, "Leftover IPs from the previous session", f"Temporary IPs found:\n{txt}\nRemove?"
                )
                == QMessageBox.Yes
            ):
                msgs = nm.cleanup_all()
                self.log_line("Cleanup: " + " | ".join(msgs))
                self.update_net_label()

    def closeEvent(self, ev):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(3000)
        for i in range(self.ctrl_tabs.count()):  # close status polling in the tabs
            wdg = self.ctrl_tabs.widget(i)
            if hasattr(wdg, "shutdown"):
                wdg.shutdown()
        # Remove temporary addresses before the process exits.
        try:
            messages = nm.cleanup_all()
            if messages:
                self.log_line("Cleanup: " + " | ".join(messages))
        except Exception as exc:
            self.log_line(f"Cleanup failed: {exc}"[:200])
        self.config.update({"scan_cidr": self.e_cidr.text()})
        cfg.save(self.config)
        super().closeEvent(ev)

    def on_bridge(self):
        """Automatic: for every visible (ARP/SSDP/known) but unreachable camera
        build a bridge on physical Ethernet. No adapter selection."""
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
            _, msg = nm.ensure_reachable(ip)
            self.log_line(f"Bridge {ip}: {msg}")
        self.update_net_label()
        self.start_scan("fast")

    def start_scan(self, mode):
        # never two scans at once (an old worker stole signals + crashed on GC)
        self._scan_gen = getattr(self, "_scan_gen", 0) + 1
        my_gen = self._scan_gen
        if self.worker is not None:
            for sig in ("done", "error", "prog", "step"):
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
        self.worker = ScanWorker(
            mode, self.e_cidr.text().strip(), self.creds_for, known=self.config.get("known_ips", [])
        )
        self.worker.done.connect(lambda found, g=my_gen: self.on_scan_done(found, g))
        self.worker.error.connect(lambda msg, g=my_gen: self.on_scan_error(msg, g))
        self.worker.prog.connect(lambda d, t: (self.prog.setMaximum(t), self.prog.setValue(d)))
        self.worker.step.connect(self.lbl.setText)
        self.worker.start()

    def on_stop(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.log_line("Scan stopped.")

    def on_scan_error(self, message: str, gen=None):
        if gen is not None and gen != getattr(self, "_scan_gen", gen):
            return
        self.prog.setVisible(False)
        self.btn_stop.setEnabled(False)
        self.btn_stop.setVisible(False)
        self.btn_fast.setEnabled(True)
        self.lbl.setText("Scan failed. Check the log for details.")
        self.log_line(f"Scan error: {message}")

    def on_scan_done(self, found, gen=None, announce=True):
        if gen is not None and gen != getattr(self, "_scan_gen", gen):
            return  # stale scan - ignore
        # the demo camera stays on the list after another scan too
        demo = next((c for c in self.cams if c["ip"] == DEMO_IP), None)
        found = list(found)
        if demo is not None and not any(c["ip"] == DEMO_IP for c in found):
            found.append(demo)
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
                tip += (
                    f"\nUDP 52380: {u.get('model') or '?'} · MAC {u.get('mac') or '?'} · "
                    f"FW {u.get('softversion') or '?'} · WRITE:{u.get('writable') or '?'}"
                )
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
        self.btn_demo.setVisible(not self.cams)
        if not self.cams:
            self._place_demo_btn()
            self.btn_demo.raise_()
        n = len(found)
        if announce:
            self.lbl.setText(f"Found: {n}")
            self.log_line(f"Scan done: {[c['ip'] for c in found]}")
        if not getattr(self, "_restored", False):
            self._restored = True
            self.restore_tabs()
        try:
            known = list(
                dict.fromkeys(list(self.config.get("known_ips", [])) + [c["ip"] for c in found if c["ip"] != DEMO_IP])
            )[:20]
            self.config["known_ips"] = known
            cfg.save(self.config)
        except Exception:
            pass
        if announce:
            # cameras that rejected every default login: ask for credentials
            QTimer.singleShot(150, self.prompt_missing_creds)

    def eventFilter(self, obj, ev):
        if obj is self.cam_table.viewport() and ev.type() == QEvent.Type.Resize:
            self._place_demo_btn()
        return super().eventFilter(obj, ev)

    def _place_demo_btn(self):
        if not hasattr(self, "btn_demo"):
            return
        vp = self.cam_table.viewport()
        self.btn_demo.adjustSize()
        x = max(0, (vp.width() - self.btn_demo.width()) // 2)
        y = min(max(0, vp.height() // 2 + 26), max(0, vp.height() - self.btn_demo.height() - 8))
        self.btn_demo.move(x, y)

    def add_demo_camera(self):
        """Add the simulated camera (no network) and open its control tab."""
        if not any(c["ip"] == DEMO_IP for c in self.cams):
            self.cams.append(
                {
                    "ip": DEMO_IP,
                    "http": True,
                    "http_port": 0,
                    "visca_52381": False,
                    "model": "DEMO",
                    "note": "Simulated camera - no network. Safe to experiment.",
                }
            )
            self.log_line("Demo camera added (simulated, no hardware).")
        self.on_scan_done(self.cams, announce=False)
        self.add_ctrl_tab(DEMO_IP)

    def creds_for(self, ip: str):
        """Credential pairs to try for a camera (saved -> defaults)."""
        return credman.candidates(self.config, ip)

    def ask_credentials(self, ip: str, error: str = ""):
        """Prompt for login/password until the camera accepts or the user skips.

        Returns the fresh probe result (dict) on success, None when skipped.
        """
        if ip == DEMO_IP:
            return None
        cands = self.creds_for(ip)
        user = (cands[0][0] if cands else "admin") or "admin"
        while True:
            dlg = CredentialsDialog(self, ip=ip, user=user, error=error)
            if dlg.exec() != QDialog.Accepted:
                return None
            u, p = dlg.values()
            if not u:
                error = "Login cannot be empty."
                continue
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                hit = disc.probe_ip(ip, creds_list=[(u, p)])
            finally:
                QApplication.restoreOverrideCursor()
            if hit and not hit.get("auth_failed"):
                credman.save_credentials(self.config, ip, u, p)
                cfg.save(self.config)
                self.log_line(f"Login accepted for {ip}.")
                return hit
            error = (
                "Login or password is incorrect." if hit and hit.get("auth_failed") else "The camera did not respond."
            )
            user = u

    def prompt_missing_creds(self):
        """Ask for credentials for cameras that rejected all default logins."""
        if self._cred_prompt_active:
            return
        pending = [c["ip"] for c in self.cams if c.get("auth_failed") and c["ip"] not in self._cred_skipped]
        if not pending:
            return
        self._cred_prompt_active = True
        try:
            for ip in pending:
                if ip in self._cred_skipped:
                    continue
                hit = self.ask_credentials(ip)
                if hit is None:
                    self._cred_skipped.add(ip)
                    self.log_line(f"Login skipped for {ip}.")
                    continue
                self.cams = [hit if c["ip"] == ip else c for c in self.cams]
                self.on_scan_done(self.cams, announce=False)
                if ip in (self.config.get("open_tabs") or []):
                    self.add_ctrl_tab(ip)
        finally:
            self._cred_prompt_active = False

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
            item = QTableWidgetItem("open" if opened else "-")
            item.setTextAlignment(Qt.AlignCenter)
            item.setForeground(QColor("#ffb14e") if opened else QColor("#8b9198"))
            self.cam_table.setItem(r, 4, item)

    def dev_menu(self, pos):
        from PySide6.QtWidgets import QMenu

        menu = QMenu(self)
        a1 = menu.addAction("Control")
        a2 = menu.addAction("Open in browser")
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

        ip, ok = QInputDialog.getText(self, "Add IP", "Camera address (e.g. 192.168.1.101):")
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
            hit = disc.probe_ip(ip, creds_list=self.creds_for(ip))
        finally:
            QApplication.restoreOverrideCursor()
        if not hit:
            okm, msg = nm.ensure_reachable(ip)
            self.log_line(f"Bridge for {ip}: {msg}")
            if okm:
                QApplication.setOverrideCursor(Qt.WaitCursor)
                try:
                    hit = disc.probe_ip(ip, creds_list=self.creds_for(ip))
                finally:
                    QApplication.restoreOverrideCursor()
        if hit and hit.get("auth_failed"):
            hit = self.ask_credentials(ip)
        if hit:
            if all(c["ip"] != hit["ip"] for c in self.cams):
                self.cams.append(hit)
            self.on_scan_done(self.cams)
            self.log_line(f"Added {hit['ip']}.")
        else:
            QMessageBox.warning(self, "Add IP", f"{ip}: no response or login was cancelled.")

    def open_all_tabs(self):
        for c in self.cams:
            self.add_ctrl_tab(c["ip"])

    def open_web_tab(self):
        # double-click = control right away (in-app tab)
        self.add_ctrl_tab()

    def ctrl_ips(self):
        return [tab_ip(self.ctrl_tabs.widget(i), self.ctrl_tabs.tabText(i)) for i in range(self.ctrl_tabs.count())]

    def _tab_label(self, ip: str) -> str:
        return next((str(c.get("model") or "") for c in self.cams if c["ip"] == ip), "") or ip

    def _refresh_tab_labels(self):
        for i in range(self.ctrl_tabs.count()):
            wdg = self.ctrl_tabs.widget(i)
            ip = tab_ip(wdg, self.ctrl_tabs.tabText(i))
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
        cam = next((x for x in self.cams if x["ip"] == ip), {}) or {}
        if cam.get("auth_failed") and ip != DEMO_IP:
            hit = self.ask_credentials(ip)
            if hit is None:
                return
            cam = hit
            self.cams = [hit if x["ip"] == ip else x for x in self.cams]
            self.on_scan_done(self.cams, announce=False)
            port = hit.get("http_port", port)
            http = bool(hit.get("http"))
        user = str(cam.get("user") or "")
        password = str(cam.get("password") or "")
        if not user:
            cands = self.creds_for(ip)
            user, password = cands[0] if cands else ("admin", "admin123")
        demo_api = DemoCameraAPI(ip) if ip == DEMO_IP else None
        tab = CameraTab(
            ip,
            user,
            password,
            http_port=port,
            log=self.log_line,
            frames=self.config.get("frames", {}).get(ip),
            save_frames=lambda: self.save_frames(ip),
            reachable=http or demo_api is not None,
            api=demo_api,
        )
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
                tab = self.ctrl_tabs.widget(i)
                if tab_ip(tab) == ip:
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
            self.config["open_tabs"] = [ip for ip in self.ctrl_ips() if ip != DEMO_IP]
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
                continue  # already open (e.g. added manually right after a scan)
            if ip not in found:
                # camera does not respond (another network) - the tab would freeze the window
                self.log_line(f"Skipping tab {ip} (camera not responding).")
                continue
            cam = next((c for c in self.cams if c["ip"] == ip), {}) or {}
            if cam.get("auth_failed"):
                self.log_line(f"Skipping tab {ip} (login required).")
                continue
            try:
                port = next((c.get("http_port", 80) for c in self.cams if c["ip"] == ip), 80)
                http = bool(next((c.get("http") for c in self.cams if c["ip"] == ip), False))
                user = str(cam.get("user") or "")
                password = str(cam.get("password") or "")
                if not user:
                    cands = self.creds_for(ip)
                    user, password = cands[0] if cands else ("admin", "admin123")
                tab = CameraTab(
                    ip,
                    user,
                    password,
                    http_port=port,
                    log=self.log_line,
                    frames=self.config.get("frames", {}).get(ip),
                    save_frames=lambda ip=ip: self.save_frames(ip),
                    reachable=http,
                )
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
        if ip == DEMO_IP:
            QMessageBox.information(self, "Demo camera", "The demo camera has no web interface.")
            return
        port = next((c.get("http_port", 80) for c in self.cams if c["ip"] == ip), 80)
        how, msg = self.edge.open(ip, port)
        if how == "no-browser":
            import webbrowser

            webbrowser.open(f"http://{ip}:{port}/")
            self.log_line(msg + " Opened in the default browser.")
        else:
            self.log_line(msg + (" (Edge will remember the password in the app profile.)" if how == "opened" else ""))

    def on_diag(self):
        ip = self.selected_ip()
        if not ip:
            QMessageBox.warning(self, "No selection", "Select a camera.")
            return
        if ip == DEMO_IP:
            QMessageBox.information(self, "Demo camera", "Simulated camera - no network to test.")
            return
        ok_p, ping_msg = diag.ping(ip)
        h = diag.tcp_open(ip, 80)
        h8 = diag.tcp_open(ip, 8080)
        v = diag.tcp_open(ip, 52381)
        txt = (
            f"{ip}: ping={'OK' if ok_p else 'FAIL'} {ping_msg}\n"
            f"80={'open' if h else 'closed'} 8080={'open' if h8 else 'closed'} "
            f"VISCA 52381={'open' if v else 'closed'}"
        )
        self.log_line(txt.replace("\n", " | "))
        QMessageBox.information(self, "Connection", txt)

    # -- UDP: network SET + panel table + CSV (Sony formats) -----------------
    def _dev_defaults(self, ip: str) -> dict:
        """Values to prefill the UDP dialog from scan data (UDP > CGI)."""
        c = next((x for x in self.cams if x["ip"] == ip), None) or {}
        u = c.get("udp") or {}
        net = c.get("network") if isinstance(c.get("network"), dict) else {}
        writable = None
        if u:
            writable = (u.get("writable") or "") == "on"
        return {
            "mac": u.get("mac") or "",
            "ip": c.get("ip", "") or "",
            "mask": u.get("mask") or "255.255.255.0",
            "gateway": u.get("gateway") or "",
            "name": u.get("name") or net.get("CameraName") or "",
            "writable": writable,
        }

    def open_udp_write(self):
        try:
            from .ui_udp import WriteNetDialog
        except ImportError:
            from ui_udp import WriteNetDialog  # noqa: E402
        ip = self.selected_ip()
        if not ip:
            QMessageBox.warning(self, "No selection", "Select a camera in the table.")
            return
        if ip == DEMO_IP:
            QMessageBox.information(self, "Demo camera", "The demo camera has no network settings.")
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
                self.config["open_tabs"] = [new_ip if t == old_ip else t for t in self.config.get("open_tabs", [])]
                cfg.save(self.config)
            except Exception:
                pass
        self.log_line(f"UDP SET: ACK confirmed, {old_ip} -> {new_ip}.")
        QMessageBox.information(self, "UDP SET", f"Camera confirmed the change (ACK):\n\n  {old_ip}  ->  {new_ip}")
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
        return {
            "name": u.get("name") or net.get("CameraName") or "",
            "mac": u.get("mac") or net.get("MACAddress") or net.get("MAC") or "",
            "ip": c.get("ip", ""),
            "mask": u.get("mask") or "255.255.255.0",
            "gateway": u.get("gateway") or "",
            "version": u.get("softversion") or net.get("SoftVersion") or "",
        }

    def export_camera_csv(self):
        rows_out = [self._cam_csv_row(c) for c in self.cams if c["ip"] != DEMO_IP]
        if not rows_out:
            QMessageBox.information(self, "CSV", "Device list is empty.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export camera list (CSV)", "rmip_cameras.csv", "CSV (*.csv);;All files (*)"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(sony_csv.camera_csv_text(rows_out))
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "CSV", f"Could not save: {e}")
            return
        self.log_line(f"CSV: saved {len(rows_out)} cameras -> {path}")
        QMessageBox.information(self, "CSV", f"Saved {len(rows_out)} rows:\n{path}")

    def import_camera_csv(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import camera list (CSV)", "", "CSV (*.csv);;All files (*)")
        if not path:
            return
        try:
            with open(path, encoding="utf-8-sig", errors="replace") as f:
                text = f.read()
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "CSV", f"Could not load: {e}")
            return
        parsed = sony_csv.parse_camera_csv(text)
        rows = parsed["rows"]
        if parsed["warnings"]:
            extra = "" if len(parsed["warnings"]) <= 12 else f"\n... and {len(parsed['warnings']) - 12} more"
            QMessageBox.warning(self, "CSV - warnings", "\n".join(parsed["warnings"][:12]) + extra)
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
            cam = {
                "ip": ip,
                "http": False,
                "http_port": 0,
                "visca_52381": False,
                "model": r.get("name") or "?",
                "csv": r,
                "note": f"from CSV: MAC {r.get('mac') or '?'} FW {r.get('version') or '?'}",
            }
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
        QMessageBox.information(self, "CSV", f"Loaded {len(rows)} cameras from the file. New on the list: {added}.")
        self.start_scan("fast")


def app_icon():
    """App icon from assets/icon.svg (vector: sharp at every size).

    Works both from source and from a PyInstaller bundle (sys._MEIPASS).
    """
    base = getattr(sys, "_MEIPASS", None)
    if base:
        # Frozen bundles prefer the platform-native icon.
        candidates = [
            os.path.join(base, "assets", "icon.icns"),
            os.path.join(base, "assets", "icon.ico"),
            os.path.join(base, "assets", "icon.svg"),
        ]
    else:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        candidates = [
            os.path.join(root, "assets", "icon.icns"),
            os.path.join(root, "assets", "icon.svg"),
            os.path.join(root, "assets", "icon.ico"),
        ]
    for path in candidates:
        if os.path.exists(path):
            icon = QIcon(path)
            if not icon.isNull():
                return icon
    return QIcon()


def set_windows_app_id():
    """Windows: AppUserModelID + taskbar icon registration (HKCU).

    SetCurrentProcessExplicitAppUserModelID alone is not enough on Windows 11 -
    the shell looks for the AUMID icon in the shortcut/class. An AppUserModelId
    entry with IconUri (as Chrome does) gives the taskbar an unambiguous icon source.
    """
    if os.name != "nt":
        return
    aumid = "wertos97.RMIPPlusPlus.App"
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(aumid)
    except Exception:
        pass
    try:
        import shutil
        import tempfile
        import winreg

        exe = sys.executable if getattr(sys, "frozen", False) else None
        if exe and os.path.exists(exe):
            # stable icon file (shell reads .ico more reliably than an exe in onefile)
            icon_uri = exe
            src = os.path.join(getattr(sys, "_MEIPASS", "") or "", "assets", "icon.ico")
            if os.path.exists(src):
                dst_dir = os.path.join(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir(), "RMIP++")
                os.makedirs(dst_dir, exist_ok=True)
                dst = os.path.join(dst_dir, "icon.ico")
                try:
                    shutil.copyfile(src, dst)
                    icon_uri = dst
                except Exception:
                    icon_uri = exe
            key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, "Software\\Classes\\AppUserModelId\\" + aumid)
            winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, "RM IP++")
            winreg.SetValueEx(key, "IconUri", 0, winreg.REG_SZ, icon_uri)
            winreg.CloseKey(key)
            # Start Menu shortcut carries the AUMID -> taskbar icon on Win11
            try:
                lnk_dir = os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs")
                ensure_shortcut(os.path.join(lnk_dir, "RM IP++.lnk"), exe, icon_uri, aumid)
                # tell the shell the registration changed (icon refresh)
                ctypes.windll.shell32.SHChangeNotify(0x08000000, 0x0000, None, None)
            except Exception:
                pass
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
    w.setWindowIcon(app_icon())
    w.showMaximized()
    sys.exit(app.exec())

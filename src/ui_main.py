"""RM IP++: wykrywanie kamer Sony w sieci + otwieranie polaczen (karty web).

Zero konfiguracji: brak wyboru karty (wszystkie interfejsy na raz, wirtualne
typu Bluetooth/komorkowe sa ignorowane), skan startuje sam po uruchomieniu,
a most dobudowuje sie automatycznie tylko gdy kamera jest nieosiagalna.
"""
from __future__ import annotations

import atexit
import datetime
import os
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QEvent, Qt, QThread, Signal, QTimer
from PySide6.QtGui import QColor, QCursor, QIcon
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
<h3>RM IP++ &nbsp;<span class="dim" style="font-size:12px;">program do kamer Sony po sieci IP</span></h3>
<p>Windows, PySide6. Jedno okno, zakładka na kamerę. Program nie odbiera obrazu wideo &mdash;
kamera nadaje po SDI/HDMI do miksera. Do kamery wysyła komendy HTTP CGI (Digest) i odczytuje jej stan.</p>

<h4>FUNKCJE</h4>
<ul>
<li><span class="tag">PTZ</span> &mdash; pad 8-kierunkowy + HOME. Jazda: ruch trwa w trakcie
  przytrzymania (krótki klik = 0,5 s ruchu). Krok: klik = 1 krok (wielkość 1-2000),
  przytrzymanie = po 0,3 s ruch ciągły. Prędkość 0-24 (0 = auto wg zoomu).</li>
<li><span class="tag">Zoom / Focus</span> &mdash; W-/T+ (prędkość 0-8); Near/Far,
  OnePush AF, tryb auto/manual.</li>
<li><span class="tag">Kadry 1-16 + szybkie 1-6</span> &mdash; zapis i przywołanie
  wyłącznie pan/tilt/zoom/focus (AbsolutePTZF); przyciski 1-6 podświetlają kadr
  zgodny z bieżącą pozycją kamery.</li>
<li><span class="tag">Presety kamery</span> &mdash; siatka 1-256 (BRC-AM7: 1-100):
  przywołanie, zapis, kasowanie, nazwy, miniaturki z kadru kamery.</li>
<li><span class="tag">Obraz</span> &mdash; ekspozycja (tryb, przysłona, gain, migawka,
  kompensacja) i balans bieli (tryb, wzmocnienia, offset); wartości w jednostkach
  kamery (F, dB / EV, 1/…, klatki).</li>
<li><span class="tag">Sieć</span> &mdash; wykrywanie kamer (ARP, SSDP, UDP 52380);
  zmiana IP / maski / bramy / nazwy przez UDP (SET + ACK/NAK); odczyt tabeli slotów
  panelu RM-IP500; import/eksport CSV w formacie Sony.</li>
<li><span class="tag">Log</span> &mdash; komendy, odpowiedzi i błędy na dole okna głównego.</li>
</ul>

<h4>MODELE</h4>
<ul>
<li><span class="tag">SRG-X400 / BRC-X400</span> &mdash; komendy zweryfikowane na SRG-X400
  (HTTP CGI z digest auth, port 80).</li>
<li><span class="tag">BRC-AM7</span> &mdash; mapowanie wg Sony &bdquo;CGI Command List&rdquo; v2.0;
  model rozpoznawany przez inq=viewermode. Zestaw komend nieprzetestowany na sprzęcie.</li>
</ul>

<h4>BRC-AM7 &mdash; RÓŻNICE</h4>
<ul>
<li>Focus Near/Far krokowo (AbsoluteFocus); brak ciągłego ruchu ostrości w CGI.</li>
<li>Presety 1-100; przywołanie tylko numerem, bez prędkości.</li>
<li>Brak ExposureMode: trzy przełączniki auto (migawka / przysłona / AGC); program
  spina je w tryby auto / shutter / iris / manual.</li>
<li>Skale: przysłona CLOSE / F2.8-F11, gain -9 do +36 dB, migawka 50p (1/50-1/8000,
  64F-2F), kąty co 0,001°, zoom do 25x.</li>
<li>Balans bieli: atw / memory_a / preset. OnePush AF/WB jako press+release.</li>
</ul>

<h4>OGRANICZENIA</h4>
<ul>
<li>Brak podglądu wideo; obraz idzie z kamery po SDI/HDMI.</li>
<li>UDP SET działa tylko przy WRITE:on w kamerze; stan WRITE jest w podpowiedzi
  urządzenia na liście.</li>
<li>Tabela panelu RM-IP500: odczyt i eksport CSV; zapis do panelu nie jest wysyłany.</li>
<li>Kadry nie obejmują ekspozycji, balansu bieli ani kolorów.</li>
<li>Kamery nieosiągalne w sieci nie odtwarzają zakładek przy starcie.</li>
</ul>
<p class="dim">Sterowanie: HTTP CGI (Digest), port 80 kamery. Wykrywanie i SET sieci: UDP 52380.</p>
"""


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("O aplikacji")
        self.resize(780, 640)
        v = QVBoxLayout(self)
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(10)
        tb = QTextBrowser()
        tb.setOpenExternalLinks(False)
        tb.setHtml(ABOUT_HTML)
        v.addWidget(tb, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        b = QPushButton("Zamknij")
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
                self.step.emit("Skan: tabela ARP...")
                self.prog.emit(3, 100)
                arp = [h["ip"] for h in bridge.arp_candidates(None)]
            except Exception:
                arp = []
            if self._stop:
                self.done.emit([])
                return
            # faza 2/4: SSDP (multicast, ~2 s)
            try:
                self.step.emit("Skan: nasluch SSDP/UPnP...")
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
            self.step.emit(f"Skan: sondowanie ({len(targets)} adresow)...")
            with ThreadPoolExecutor(max_workers=1) as uex:
                fut_udp = self._start_udp(uex)
                out = disc.probe_many(
                    targets, self.user, self.password,
                    progress=lambda d, t: (self.prog.emit(12 + 88 * d // max(1, t), 100),
                                           self.step.emit(f"Skan: {d}/{t}...")))
                out = disc.merge_udp(out, self._udp_result(fut_udp))
        else:
            self.step.emit("Skan: UDP 52380...")
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
                             lambda s: self.step.emit("Skan: " + str(s)))
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
        self.btn_fast = QPushButton("Skanuj")
        self.btn_fast.setMinimumHeight(32)
        self.btn_fast.clicked.connect(lambda: self.start_scan("fast"))
        top.addWidget(self.btn_fast)
        self.btn_stop = QPushButton("Stop")
        self.btn_stop.clicked.connect(self.on_stop)
        self.btn_stop.setEnabled(False)
        self.btn_stop.setVisible(False)
        top.addWidget(self.btn_stop)
        self.lbl = QLabel("Skanowanie startowe...")
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
        self.btn_adv = QPushButton("Zaawansowane ▸")
        self.btn_adv.setCheckable(True)
        self.btn_adv.setChecked(False)
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
        ar1.addWidget(QLabel("Podsiec (CIDR):"))
        self.e_cidr = QLineEdit(self.config.get("scan_cidr", "192.168.0.0/24"))
        self.e_cidr.setMaximumWidth(150)
        ar1.addWidget(self.e_cidr)
        self.btn_full = QPushButton("Skanuj podsiec")
        self.btn_full.clicked.connect(lambda: self.start_scan("full"))
        ar1.addWidget(self.btn_full)
        self.btn_bridge = QPushButton("Dobuduj most do nieosiagalnych")
        self.btn_bridge.clicked.connect(self.on_bridge)
        ar1.addWidget(self.btn_bridge)
        ar1.addStretch(1)
        ar2 = QHBoxLayout()
        adv_lay.addLayout(ar2)
        ar2.addWidget(QLabel("Login:"))
        self.e_user = QLineEdit(self.user)
        self.e_user.setMaximumWidth(110)
        ar2.addWidget(self.e_user)
        ar2.addWidget(QLabel("Haslo:"))
        self.e_pass = QLineEdit(self.password)
        self.e_pass.setEchoMode(QLineEdit.Password)
        self.e_pass.setMaximumWidth(130)
        ar2.addWidget(self.e_pass)
        self.btn_diag = QPushButton("Sprawdz polaczenie")
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
        self.dev_title = QLabel("Urzadzenia")
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
        self.cam_empty = _CenterHint("Brak urzadzen.", self.cam_table.viewport())
        lv.addWidget(self.cam_table, 1)
        devbtn = QHBoxLayout()
        devbtn.setSpacing(8)
        lv.addLayout(devbtn)
        self.btn_addip = QPushButton("Dodaj IP...")
        self.btn_addip.clicked.connect(self.add_manual_ip)
        devbtn.addWidget(self.btn_addip)
        self.btn_all = QPushButton("Steruj wszystkimi")
        self.btn_all.clicked.connect(self.open_all_tabs)
        devbtn.addWidget(self.btn_all)
        devbtn2 = QHBoxLayout()
        devbtn2.setSpacing(8)
        lv.addLayout(devbtn2)
        self.btn_udpnet = QPushButton("Sieć kamery…")
        self.btn_udpnet.clicked.connect(self.open_udp_write)
        devbtn2.addWidget(self.btn_udpnet)
        self.btn_camtable = QPushButton("Tabela panelu…")
        self.btn_camtable.clicked.connect(self.open_camtable)
        devbtn2.addWidget(self.btn_camtable)
        self.btn_csv = QPushButton("CSV…")
        self.btn_csv.clicked.connect(self.csv_menu)
        devbtn2.addWidget(self.btn_csv)
        self.btn_about = QPushButton("O aplikacji")
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
        self.btn_add = QPushButton("Steruj zaznaczona")
        self.btn_add.clicked.connect(self.add_ctrl_tab)
        row.addWidget(self.btn_add)
        self.btn_web = QPushButton("Otworz w Edge")
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
                    self.log_line(f"Start: odtwarzam most dla {need} na '{iface}'...")
                    try:
                        ok, msg = nm.ensure_homes_visible(iface, need)
                    except Exception as e:
                        ok, msg = False, str(e)[:200]
                    self.log_line("Most startowy: " + msg)
                    self.update_net_label()
        self.start_scan("fast")

    def toggle_adv(self, on: bool):
        self.adv.setVisible(on)
        self.btn_adv.setText("Zaawansowane ▾" if on else "Zaawansowane ▸")

    def log_line(self, t: str):
        from html import escape
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self.log.appendHtml(
            f'<span style="color:#6f757c">[{ts}]</span> '
            f'<span style="color:#d8dade">{escape(str(t))}</span>')

    def update_net_label(self):
        try:
            bi = nm.best_bridge_iface() or "brak Ethernetu"
            n = len(nm._load_state())
            n_txt = str(n) if n else "brak"
            self.net_lbl.setText(f"Most auto: {bi} | temp IP: {n_txt}")
        except Exception:
            pass

    def check_orphans(self):
        orph = nm.find_orphans()
        if orph:
            txt = "\n".join(f"{o['interface_alias']} {o['ip']}/{o['prefix']}" for o in orph)
            if QMessageBox.question(self, "Sieroty po poprzedniej sesji",
                                    f"Znaleziono tymczasowe IP:\n{txt}\nUsunac?") == QMessageBox.Yes:
                msgs = nm.cleanup_all()
                self.log_line("Sprzatanie: " + " | ".join(msgs))
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
            QMessageBox.information(self, "Most", "Brak kandydatow (ARP/SSDP puste).")
            return
        for ip in cands:
            ok, msg = nm.ensure_reachable(ip)
            self.log_line(f"Most {ip}: {msg}")
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
                self.log_line("Czekam na zakonczenie poprzedniego skanu...")
                self.worker.stop()
                self.worker.wait(8000)
        self.prog.setVisible(True)
        self.prog.setRange(0, 100)
        self.prog.setValue(0)
        self.btn_stop.setEnabled(True)
        self.btn_stop.setVisible(True)
        self.btn_fast.setEnabled(False)
        self.lbl.setText("Skanowanie...")
        self.log_line(f"Skan {mode} (cidr={self.e_cidr.text()}).")
        self.worker = ScanWorker(mode, self.e_cidr.text().strip(), self.user, self.password,
                                 known=self.config.get("known_ips", []))
        self.worker.done.connect(lambda found, g=my_gen: self.on_scan_done(found, g))
        self.worker.prog.connect(lambda d, t: (self.prog.setMaximum(t), self.prog.setValue(d)))
        self.worker.step.connect(self.lbl.setText)
        self.worker.start()

    def on_stop(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.log_line("Przerwano skan.")

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
                it = QTableWidgetItem("tak" if ok else "nie")
                it.setTextAlignment(Qt.AlignCenter)
                it.setForeground(QColor("#8fce8f") if ok else QColor("#8a8f96"))
                self.cam_table.setItem(r, col, it)
            self.cam_table.setItem(r, 4, QTableWidgetItem(""))
        self.refresh_panel_col()
        self._refresh_tab_labels()
        self.dev_title.setText(f"Urzadzenia ({len(self.cams)})")
        self.cam_empty.setVisible(not self.cams)
        self.cam_empty.raise_()
        n = len(found)
        self.lbl.setText(f"Wykryto: {n}")
        self.log_line(f"Skan koniec: {[c['ip'] for c in found]}")
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
            item = QTableWidgetItem("otwarty" if opened else "—")
            item.setTextAlignment(Qt.AlignCenter)
            item.setForeground(QColor("#ffb14e") if opened else QColor("#6f757c"))
            self.cam_table.setItem(r, 4, item)

    def dev_menu(self, pos):
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        a1 = menu.addAction("Steruj")
        a2 = menu.addAction("Otworz w Edge")
        a3 = menu.addAction("Sprawdz polaczenie")
        a4 = menu.addAction("Zapomnij IP")
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
        self.log_line(f"Zapomniano: {sorted(ips)}")

    def add_manual_ip(self):
        from PySide6.QtWidgets import QInputDialog
        ip, ok = QInputDialog.getText(self, "Dodaj IP", "Adres kamery (np. 192.168.4.101):")
        if not ok or not ip.strip():
            return
        ip = ip.strip()
        import re as _re
        if not _re.match(r"^\d{1,3}(\.\d{1,3}){3}(:\d+)?$", ip):
            QMessageBox.warning(self, "Dodaj IP", "To nie wyglada na adres IPv4.")
            return
        self.log_line(f"Sondowanie {ip}...")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            hit = disc.probe_ip(ip, self.e_user.text().strip() or DEFAULT_USER, self.e_pass.text())
        finally:
            QApplication.restoreOverrideCursor()
        if not hit:
            okm, msg = nm.ensure_reachable(ip)
            self.log_line(f"Most dla {ip}: {msg}")
            if okm:
                hit = disc.probe_ip(ip, self.e_user.text().strip() or DEFAULT_USER, self.e_pass.text())
        if hit:
            if all(c["ip"] != hit["ip"] for c in self.cams):
                self.cams.append(hit)
            self.on_scan_done(self.cams)
            self.log_line(f"Dodano {hit['ip']}.")
        else:
            QMessageBox.warning(self, "Dodaj IP", f"{ip} nie odpowiada (HTTP/VISCA).")

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
            QMessageBox.warning(self, "Brak wyboru", "Zaznacz kamere w tabeli.")
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
        self.ctrl_tabs.setTabToolTip(idx, f"{ip} · sterowanie CGI")
        self.ctrl_tabs.setCurrentWidget(tab)
        self.log_line(f"Dodano sterowanie {ip}.")
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
                self.log_line(f"Pomijam zakladke {ip} (kamera nie odpowiada).")
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
                self.ctrl_tabs.setTabToolTip(idx, f"{ip} · sterowanie CGI")
            except Exception as e:
                self.log_line(f"Nie przywrocono {ip}: {e}"[:150])
        self.refresh_panel_col()

    def open_external(self):
        ip = self.selected_ip()
        if not ip:
            QMessageBox.warning(self, "Brak wyboru", "Zaznacz kamere w tabeli.")
            return
        port = next((c.get("http_port", 80) for c in self.cams if c["ip"] == ip), 80)
        how, msg = self.edge.open(ip, port)
        if how == "no-browser":
            import webbrowser
            webbrowser.open(f"http://{ip}:{port}/")
            self.log_line(msg + " Otwarto w domyslnej przegladarce.")
        else:
            self.log_line(msg + (" (Edge zapamieta haslo w profilu aplikacji.)"
                                 if how == "opened" else ""))

    def on_diag(self):
        ip = self.selected_ip()
        if not ip:
            QMessageBox.warning(self, "Brak wyboru", "Zaznacz kamere.")
            return
        ok_p, ping_msg = diag.ping(ip)
        h = diag.tcp_open(ip, 80)
        h8 = diag.tcp_open(ip, 8080)
        v = diag.tcp_open(ip, 52381)
        txt = (f"{ip}: ping={'OK' if ok_p else 'FAIL'} {ping_msg}\n"
               f"80={'open' if h else 'closed'} 8080={'open' if h8 else 'closed'} "
               f"VISCA 52381={'open' if v else 'closed'}")
        self.log_line(txt.replace("\n", " | "))
        QMessageBox.information(self, "Polaczenie", txt)

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
            QMessageBox.warning(self, "Brak wyboru", "Zaznacz kamere w tabeli.")
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
        self.log_line(f"UDP SET: ACK potwierdzone, {old_ip} -> {new_ip}.")
        QMessageBox.information(
            self, "UDP SET",
            f"Kamera potwierdzila zmiane (ACK):\n\n  {old_ip}  ->  {new_ip}")
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
        a1 = menu.addAction("Eksportuj liste kamer (CSV)...")
        a2 = menu.addAction("Importuj liste kamer (CSV)...")
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
            QMessageBox.information(self, "CSV", "Lista urzadzen jest pusta.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Eksport listy kamer (CSV)", "rmip_cameras.csv",
            "CSV (*.csv);;Wszystkie pliki (*)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(sony_csv.camera_csv_text([self._cam_csv_row(c) for c in self.cams]))
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "CSV", f"Nie udalo sie zapisac: {e}")
            return
        self.log_line(f"CSV: zapisano {len(self.cams)} kamer -> {path}")
        QMessageBox.information(self, "CSV", f"Zapisano {len(self.cams)} wierszy:\n{path}")

    def import_camera_csv(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import listy kamer (CSV)", "", "CSV (*.csv);;Wszystkie pliki (*)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
                text = f.read()
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "CSV", f"Nie udalo sie wczytac: {e}")
            return
        parsed = sony_csv.parse_camera_csv(text)
        rows = parsed["rows"]
        if parsed["warnings"]:
            extra = ("" if len(parsed["warnings"]) <= 12
                     else f"\n... i {len(parsed['warnings']) - 12} wiecej")
            QMessageBox.warning(self, "CSV - ostrzezenia",
                                "\n".join(parsed["warnings"][:12]) + extra)
        if not rows:
            QMessageBox.warning(self, "CSV", "Plik nie zawiera wierszy kamer.")
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
                   "note": f"z CSV: MAC {r.get('mac') or '?'} FW {r.get('version') or '?'}"}
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
        self.log_line(f"CSV: wczytano {len(rows)} wierszy ({added} nowych na liscie).")
        QMessageBox.information(
            self, "CSV",
            f"Wczytano {len(rows)} kamer z pliku. Nowych na liscie: {added}.")
        self.start_scan("fast")


def app_icon():
    """Ikona aplikacji z assets/icon.svg (wektor: ostra w kazdym rozmiarze)."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        os.pardir, "assets", "icon.svg")
    return QIcon(os.path.normpath(path))


def run():
    import sys
    try:
        from .theme import apply_theme
    except ImportError:
        from theme import apply_theme  # noqa: E402
    app = QApplication(sys.argv)
    apply_theme(app)
    app.setWindowIcon(app_icon())
    w = MainWindow()
    w.showMaximized()
    sys.exit(app.exec())

"""RM IP++: wykrywanie kamer Sony w sieci + otwieranie polaczen (karty web).

Zero konfiguracji: brak wyboru karty (wszystkie interfejsy na raz, wirtualne
typu Bluetooth/komorkowe sa ignorowane), skan startuje sam po uruchomieniu,
a most dobudowuje sie automatycznie tylko gdy kamera jest nieosiagalna.
"""
from __future__ import annotations

import atexit
import datetime

from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton,
    QSplitter, QStatusBar, QTableWidget, QTableWidgetItem, QTabWidget,
    QVBoxLayout, QWidget,
)

try:
    from . import net_manager as nm
    from . import discovery as disc
    from . import config_store as cfg
    from . import diagnostics as diag
    from . import subnet_bridge as bridge
    from . import edge_view as ev
    from .sony_client import DEFAULT_USER, DEFAULT_PASSWORD
except ImportError:
    import net_manager as nm  # noqa: E402
    import discovery as disc  # noqa: E402
    import config_store as cfg  # noqa: E402
    import diagnostics as diag  # noqa: E402
    import subnet_bridge as bridge  # noqa: E402
    import edge_view as ev  # noqa: E402
    from sony_client import DEFAULT_USER, DEFAULT_PASSWORD  # noqa: E402


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
            # faza 1/3: kandydaci z ARP (szybkie trafienia najpierw)
            try:
                self.step.emit("Skan: tabela ARP...")
                self.prog.emit(3, 100)
                arp = [h["ip"] for h in bridge.arp_candidates(None)]
            except Exception:
                arp = []
            if self._stop:
                self.done.emit([])
                return
            # faza 2/3: SSDP (multicast, ~2 s)
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
            self.step.emit(f"Skan: sondowanie ({len(targets)} adresow)...")
            out = disc.probe_many(
                targets, self.user, self.password,
                progress=lambda d, t: (self.prog.emit(12 + 88 * d // max(1, t), 100),
                                       self.step.emit(f"Skan: {d}/{t}...")))
        else:
            out = disc.scan_subnet(self.cidr, self.user, self.password,
                                   progress=lambda d, t: self.prog.emit(d, t),
                                   stop_flag=lambda: self._stop)
        self.done.emit(out)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("RM IP++ - wykrywanie kamer Sony")
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

        top = QHBoxLayout()
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
        adv_lay = QVBoxLayout(self.adv)
        adv_lay.setContentsMargins(0, 0, 0, 0)
        v.addWidget(self.adv)
        ar1 = QHBoxLayout()
        adv_lay.addLayout(ar1)
        ar1.addWidget(QLabel("Skan calej podsieci (CIDR):"))
        self.e_cidr = QLineEdit(self.config.get("scan_cidr", "192.168.0.0/24"))
        self.e_cidr.setMaximumWidth(150)
        ar1.addWidget(self.e_cidr)
        self.btn_full = QPushButton("Skanuj podsieci")
        self.btn_full.clicked.connect(lambda: self.start_scan("full"))
        ar1.addWidget(self.btn_full)
        self.btn_bridge = QPushButton("Dobuduj most do nieosiagalnych")
        self.btn_bridge.setToolTip("Dla kamer spoza zasiegu: doklada secondary IP na fizycznym Ethernecie. WiFi z internetem nietkniete.")
        self.btn_bridge.clicked.connect(self.on_bridge)
        ar1.addWidget(self.btn_bridge)
        ar1.addStretch(1)
        ar2 = QHBoxLayout()
        adv_lay.addLayout(ar2)
        ar2.addWidget(QLabel("Login do kamer:"))
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
        self.net_lbl.setStyleSheet("color: gray;")
        ar2.addWidget(self.net_lbl, 1)
        self.update_net_label()
        self.adv.setVisible(False)

        split = QSplitter(Qt.Horizontal)
        v.addWidget(split, 1)

        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
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
        hh = self.cam_table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        for i in (2, 3, 4):
            hh.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        self.cam_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.cam_table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.cam_table.setAlternatingRowColors(True)
        self.cam_table.verticalHeader().setDefaultSectionSize(30)
        f = self.cam_table.font()
        f.setPointSize(11)
        self.cam_table.setFont(f)
        self.cam_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.cam_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.cam_table.customContextMenuRequested.connect(self.dev_menu)
        self.cam_table.doubleClicked.connect(self.open_web_tab)
        lv.addWidget(self.cam_table, 1)
        devbtn = QHBoxLayout()
        lv.addLayout(devbtn)
        self.btn_addip = QPushButton("Dodaj IP...")
        self.btn_addip.setToolTip("Recznie dopisz kamere (gdy skan jej nie widzi).")
        self.btn_addip.clicked.connect(self.add_manual_ip)
        devbtn.addWidget(self.btn_addip)
        self.btn_all = QPushButton("Steruj wszystkimi")
        self.btn_all.setToolTip("Otwiera zakladki sterowania dla wszystkich z tabeli.")
        self.btn_all.clicked.connect(self.open_all_tabs)
        devbtn.addWidget(self.btn_all)
        split.addWidget(left)

        right = QWidget()
        rv = QVBoxLayout(right)
        self.ctrl_tabs = QTabWidget()
        self.ctrl_tabs.setTabsClosable(True)
        self.ctrl_tabs.tabCloseRequested.connect(self.close_ctrl_tab)
        rv.addWidget(self.ctrl_tabs, 3)
        row = QHBoxLayout()
        rv.addLayout(row)
        self.btn_add = QPushButton("Steruj zaznaczona")
        self.btn_add.setToolTip("Otwiera zakladke sterowania VISCA/CGI dla kamery z tabeli.")
        self.btn_add.clicked.connect(self.add_ctrl_tab)
        row.addWidget(self.btn_add)
        self.btn_web = QPushButton("Otworz w Edge")
        self.btn_web.setToolTip("Pelna strona kamery w Edge (osobne okno, wideo H.264).")
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
        admin = nm.is_admin()
        sb.showMessage(f"{'ADMIN' if admin else 'most poprosi o UAC tylko gdy bedzie potrzebny'}")

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
                self.log_line(f"Start: odtwarzam most dla znanych {known} na '{iface}'...")
                try:
                    ok, msg = nm.ensure_homes_visible(iface, known)
                except Exception as e:
                    ok, msg = False, str(e)[:200]
                self.log_line("Most startowy: " + msg)
                self.update_net_label()
        self.start_scan("fast")

    def toggle_adv(self, on: bool):
        self.adv.setVisible(on)
        self.btn_adv.setText("Zaawansowane ▾" if on else "Zaawansowane ▸")

    def log_line(self, t: str):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self.log.appendPlainText(f"[{ts}] {t}")

    def update_net_label(self):
        try:
            bi = nm.best_bridge_iface() or "brak Ethernetu"
            n = len(nm._load_state())
            self.net_lbl.setText(f"Most auto: {bi} | temp IP: {n} | WiFi: internet")
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
        self.lbl.setText("Skanowanie... (reszta aplikacji dziala normalnie)")
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
        for r, c in enumerate(self.cams):
            ip_item = QTableWidgetItem(("● " if c.get("http") else "○ ") + c["ip"])
            if c.get("http"):
                ip_item.setForeground(Qt.darkGreen)
            self.cam_table.setItem(r, 0, ip_item)
            self.cam_table.setItem(r, 1, QTableWidgetItem(str(c.get("model", "?"))))
            self.cam_table.setItem(r, 2, QTableWidgetItem("tak" if c.get("http") else "nie"))
            self.cam_table.setItem(r, 3, QTableWidgetItem("tak" if c.get("visca_52381") else "nie"))
            self.cam_table.setItem(r, 4, QTableWidgetItem(""))
        self.refresh_panel_col()
        self.dev_title.setText(f"Urzadzenia ({len(self.cams)})")
        self.lbl.setText(f"Znaleziono {len(found)}. Dwuklik otwiera sterowanie.")
        self.lbl.setText(f"Znaleziono {len(found)}. Dwuklik otwiera sterowanie.")
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
            item = QTableWidgetItem("otwarty" if c["ip"] in open_ips else "—")
            if c["ip"] in open_ips:
                item.setForeground(Qt.darkGreen)
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
        return [self.ctrl_tabs.tabText(i) for i in range(self.ctrl_tabs.count())]

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
        tab = CameraTab(ip, self.e_user.text().strip() or DEFAULT_USER,
                        self.e_pass.text(), http_port=port, log=self.log_line,
                        frames=self.config.get("frames", {}).get(ip),
                        save_frames=lambda: self.save_frames(ip))
        self.ctrl_tabs.addTab(tab, ip)
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
        for ip in self.config.get("open_tabs", []):
            try:
                port = next((c.get("http_port", 80) for c in self.cams if c["ip"] == ip), 80)
                tab = CameraTab(ip, self.e_user.text().strip() or DEFAULT_USER,
                                self.e_pass.text(), http_port=port, log=self.log_line,
                                frames=self.config.get("frames", {}).get(ip),
                                save_frames=lambda ip=ip: self.save_frames(ip))
                self.ctrl_tabs.addTab(tab, ip)
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


def run():
    import sys
    try:
        from .theme import apply_theme
    except ImportError:
        from theme import apply_theme  # noqa: E402
    app = QApplication(sys.argv)
    apply_theme(app)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())

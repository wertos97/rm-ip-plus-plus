"""Okna protokolu UDP Sony: SET sieci kamery + odczyt tabeli z panelu RM-IP.

Protokol odtworzony z RM-IPSetupTool.exe v1.2.0 (patrz src/sony_udp.py):
  SET : 02 MAC:<mac> FF IPADR:.. FF MASK:.. FF GATEWAY:.. FF NAME:.. FF 03
  ENQ : 02 ENQ:camtable<N> FF 03   (N=1..4 -> 4 x 28 = 112 slotow panelu)
Oba leca na broadcast 255.255.255.255:52380, wiec dzialaja takze dla kamery
z adresem z innej podsieci niz komputer (bez zmiany IP karty).
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QSizePolicy,
    QTableWidget, QTableWidgetItem, QVBoxLayout,
)

try:
    from . import sony_csv, sony_udp
except ImportError:  # uruchomienie skryptowe / testy
    import sony_csv  # noqa: E402
    import sony_udp  # noqa: E402


def _raw_text(data: bytes) -> str:
    try:
        txt = data.decode("latin-1")
    except Exception:
        return repr(data)
    return "".join(ch if 0x20 <= ord(ch) < 0x7F else "." for ch in txt)


class WriteWorker(QThread):
    done = Signal(dict)

    def __init__(self, mac, ip, mask, gateway, name, parent=None):
        super().__init__(parent)
        self.args = (mac, ip, mask, gateway, name)

    def run(self):
        try:
            res = sony_udp.set_camera_network(*self.args, timeout=4.0)
        except Exception as e:  # noqa: BLE001
            res = {"ok": False, "kind": "error", "error": str(e)[:200], "replies": []}
        self.done.emit(res)


class WriteNetDialog(QDialog):
    """Ustawia siec kamery przez broadcast UDP (jak Auto IP Setup w Sony)."""

    applied = Signal(dict)   # {"old_ip", "ip", "mac"} - tylko po ACK

    def __init__(self, parent=None, defaults: dict | None = None, old_ip: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Sieć kamery — broadcast UDP 52380")
        self.setMinimumWidth(560)
        self.old_ip = old_ip or ""
        self.worker: WriteWorker | None = None
        d = defaults or {}

        v = QVBoxLayout(self)
        v.setContentsMargins(16, 14, 16, 12)
        v.setSpacing(10)
        info = QLabel(
            "Wysyła ustawienia sieci do kamery o podanym MAC (protokół Sony, "
            "broadcast UDP 52380). Działa też, gdy kamera ma adres z innej "
            "podsieci niż komputer — bez zmiany IP karty.")
        info.setWordWrap(True)
        info.setStyleSheet("color:#9aa0a6;")
        v.addWidget(info)

        g = QGridLayout()
        g.setHorizontalSpacing(12)
        g.setVerticalSpacing(8)
        g.setColumnStretch(1, 1)
        v.addLayout(g)
        self.e_mac = QLineEdit(d.get("mac", ""))
        self.e_mac.setPlaceholderText("F8-4E-17-DE-30-9F")
        self.e_ip = QLineEdit(d.get("ip", ""))
        self.e_mask = QLineEdit(d.get("mask", "") or "255.255.255.0")
        self.e_gw = QLineEdit(d.get("gateway", ""))
        self.e_name = QLineEdit(d.get("name", ""))
        rows = (
            ("MAC kamery:", self.e_mac, "Z tego MAC kamera rozpozna, że rozkaz jest dla niej."),
            ("Nowy adres IP:", self.e_ip, "Docelowy adres kamery."),
            ("Maska podsieci:", self.e_mask, "Np. 255.255.255.0"),
            ("Brama:", self.e_gw, "Może być pusta."),
            ("Nazwa kamery:", self.e_name, "Krótka nazwa, maks. 16 znaków ASCII, np. CAM2."),
        )
        for i, (lbl, wdg, tip) in enumerate(rows):
            g.addWidget(QLabel(lbl), i, 0)
            g.addWidget(wdg, i, 1)
            wdg.setToolTip(tip)
        if old_ip:
            self.e_ip.setPlaceholderText(old_ip)

        self.warn = QLabel("")
        self.warn.setWordWrap(True)
        self.warn.setStyleSheet("color:#ffb14e;")
        self.warn.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        if d.get("writable") is False:
            self.warn.setText("Uwaga: kamera zgłosiła ostatnio WRITE:off — zapis może zostać "
                              "odrzucony (blokada zmiany ustawień w kamerze).")
        elif d.get("writable") is None:
            self.warn.setText("Uwaga: brak danych WRITE z UDP (skan nie widział kamery przez UDP) "
                              "— nie wiadomo, czy zapis jest odblokowany.")
        self.warn.setVisible(bool(self.warn.text()))
        v.addWidget(self.warn)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        v.addWidget(self.status)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(84)
        self.log.setPlaceholderText("Surowe odpowiedzi ACK/NAK...")
        v.addWidget(self.log)

        row = QHBoxLayout()
        self.btn_send = QPushButton("Wyślij ustawienia (UDP)")
        self.btn_send.setProperty("kind", "primary")
        self.btn_send.setMinimumHeight(30)
        self.btn_send.clicked.connect(self.on_send)
        row.addWidget(self.btn_send)
        row.addStretch(1)
        self.btn_close = QPushButton("Zamknij")
        self.btn_close.clicked.connect(self.reject)
        row.addWidget(self.btn_close)
        v.addLayout(row)

    def on_send(self):
        try:
            mac = sony_udp.normalize_mac(self.e_mac.text())
        except ValueError as e:
            QMessageBox.warning(self, "MAC", str(e))
            return
        ip = self.e_ip.text().strip()
        mask = self.e_mask.text().strip()
        gw = self.e_gw.text().strip()
        name = self.e_name.text().strip()
        if not sony_udp.is_ipv4(ip):
            QMessageBox.warning(self, "IP", f"{ip!r} nie jest poprawnym adresem IPv4.")
            return
        if not sony_udp.is_ipv4(mask):
            QMessageBox.warning(self, "Maska", f"{mask!r} nie jest poprawną maską.")
            return
        if gw and not sony_udp.is_ipv4(gw):
            QMessageBox.warning(self, "Brama", f"{gw!r} nie jest poprawną bramą.")
            return
        if not name or len(name) > 16 or any(not (0x20 <= ord(ch) <= 0x7E) for ch in name):
            QMessageBox.warning(self, "Nazwa", "Nazwa: 1-16 drukowalnych znaków ASCII "
                                               "(bez polskich znaków), np. CAM2.")
            return
        warn = (f"Kamera {mac} zmieni ustawienia sieciowe na:\n\n"
                f"    IP:     {ip}\n    Maska:  {mask}\n    Brama:  {gw or '(pusta)'}\n"
                f"    Nazwa:  {name}\n\n"
                "Kamera straci stary adres od razu po potwierdzeniu (ACK). "
                "Jeśli nowy adres jest spoza podsieci komputera, do dalszej pracy "
                "potrzebny będzie most (Zaawansowane ▸ Dobuduj most).\n\nKontynuować?")
        ans = QMessageBox.warning(self, "Zmiana adresu kamery", warn,
                                  QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ans != QMessageBox.Yes:
            return
        self.btn_send.setEnabled(False)
        self.status.setStyleSheet("color:#ffb14e;")
        self.status.setText("Wysyłam i czekam na ACK/NAK (do 4 s)...")
        self.log.clear()
        self.worker = WriteWorker(mac, ip, mask, gw, name, self)
        self.worker.done.connect(self.on_result)
        self.worker.start()

    def on_result(self, res: dict):
        self.btn_send.setEnabled(True)
        kind = res.get("kind", "?")
        if res.get("ok"):
            who = res.get("reply_mac") or res.get("target_mac") or res.get("mac") or "?"
            self.status.setStyleSheet("color:#8fce8f;")
            self.status.setText(f"ACK — kamera potwierdziła zmianę (MAC {who}). "
                                "Zaktualizuję listę urządzeń nowym adresem.")
            self.applied.emit({"old_ip": self.old_ip, "ip": res.get("ip", ""),
                               "mac": who})
        elif kind == "NAK":
            self.status.setStyleSheet("color:#ff7b72;")
            self.status.setText("NAK — kamera odrzuciła zmianę (blokada WRITE:off, "
                                "złe pole albo MAC nie wskazuje tej kamery).")
        elif kind == "error":
            self.status.setStyleSheet("color:#ff7b72;")
            self.status.setText(f"Błąd: {res.get('error')}")
        else:
            self.status.setStyleSheet("color:#ffb14e;")
            self.status.setText("Brak odpowiedzi (timeout). Kamera może nie mieć WRITE:on, "
                                "być wyłączona albo MAC się nie zgadza. Możesz spróbować ponownie.")
        replies = res.get("replies") or []
        for r in replies:
            self.log.appendPlainText(
                f"{r.get('src_ip', '?'):>15}  {r.get('kind', '?'):<4} "
                f"mac={r.get('mac') or '-'}  {_raw_text(r.get('raw') or b'')}")
        if not replies:
            self.log.appendPlainText("(0 odpowiedzi w oknie nasłuchu)")


class CamtableWorker(QThread):
    done = Signal(dict)

    def run(self):
        try:
            res = sony_udp.query_camtable(timeout=5.0)
        except Exception as e:  # noqa: BLE001
            res = {"pages": [], "misc": [], "raw": [], "error": str(e)[:200]}
        self.done.emit(res)


class CamtableDialog(QDialog):
    """Tabela kamer panelu RM-IP (ENQ:camtable 1-4) + CSV zgodne z Sony."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Tabela kamer panelu RM-IP — UDP 52380")
        self.resize(780, 560)
        self.worker: CamtableWorker | None = None
        self._slots: dict[int, dict] = {}
        self._file_mode = False

        v = QVBoxLayout(self)
        v.setContentsMargins(16, 14, 16, 12)
        v.setSpacing(8)
        self.head = QLabel("Pytam panel o tabelę kamer (strony 1-4)...")
        self.head.setWordWrap(True)
        self.head.setStyleSheet("color:#9aa0a6;")
        v.addWidget(self.head)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Slot", "Grupa-Kamera", "Nazwa", "MAC", "IP"])
        hi = self.table.horizontalHeaderItem(0)
        if hi is not None:
            hi.setTextAlignment(Qt.AlignCenter)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 56)
        hh.setSectionResizeMode(1, QHeaderView.Fixed)
        self.table.setColumnWidth(1, 110)
        hh.setSectionResizeMode(2, QHeaderView.Stretch)
        hh.setSectionResizeMode(3, QHeaderView.Fixed)
        self.table.setColumnWidth(3, 170)
        hh.setSectionResizeMode(4, QHeaderView.Fixed)
        self.table.setColumnWidth(4, 130)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.verticalHeader().setFixedWidth(28)
        v.addWidget(self.table, 1)

        self.raw = QPlainTextEdit()
        self.raw.setReadOnly(True)
        self.raw.setMaximumHeight(96)
        self.raw.setPlaceholderText("Surowe odpowiedzi panelu...")
        v.addWidget(self.raw)

        row = QHBoxLayout()
        self.btn_refresh = QPushButton("Odśwież z panelu")
        self.btn_refresh.setProperty("kind", "primary")
        self.btn_refresh.clicked.connect(self.refresh)
        row.addWidget(self.btn_refresh)
        self.btn_export = QPushButton("Eksport CSV (Sony)…")
        self.btn_export.setToolTip("Zapisuje tabelę w formacie RM-IP Setup Tool "
                                   "(112 wierszy GroupG-C, pole maski 255.255.255.0).")
        self.btn_export.clicked.connect(self.export_csv)
        row.addWidget(self.btn_export)
        self.btn_import = QPushButton("Wczytaj CSV (podgląd)…")
        self.btn_import.setToolTip("Pokazuje tabelę z pliku CSV Sony — bez zapisu do panelu.")
        self.btn_import.clicked.connect(self.import_csv)
        row.addWidget(self.btn_import)
        row.addStretch(1)
        self.btn_close = QPushButton("Zamknij")
        self.btn_close.clicked.connect(self.accept)
        row.addWidget(self.btn_close)
        v.addLayout(row)

        self.refresh()

    # -- odczyt z panelu -----------------------------------------------------
    def refresh(self):
        if self.worker is not None and self.worker.isRunning():
            return
        self._file_mode = False
        self.btn_refresh.setEnabled(False)
        self.head.setText("Pytam panel o tabelę kamer (strony 1-4, do 5 s)...")
        self.worker = CamtableWorker(self)
        self.worker.done.connect(self.on_pages)
        self.worker.start()

    def on_pages(self, res: dict):
        self.btn_refresh.setEnabled(True)
        pages = res.get("pages") or []
        misc = res.get("misc") or []
        self.raw.clear()
        for p in pages:
            self.raw.appendPlainText(
                f"{p.get('src_ip', '?'):>15}  INFO:camtable{p.get('page')}  "
                f"{_raw_text(p.get('raw') or b'')}")
        for m in misc:
            self.raw.appendPlainText(
                f"{m.get('src_ip', '?'):>15}  {m.get('kind', '?')}  "
                f"{_raw_text(m.get('raw') or b'')}")
        if res.get("error"):
            self.head.setText(f"Błąd: {res['error']}")
            return
        slots: dict[int, dict] = {}
        for p in pages:
            for e in p.get("entries") or []:
                slots[e["slot"]] = e
        if not slots:
            self._slots = {}
            self.table.setRowCount(0)
            self.head.setText("Brak odpowiedzi panelu (do 5 s). Czy panel RM-IP jest "
                              "w sieci, włączony i w tym samym segmencie L2?")
            return
        self._slots = slots
        self._fill(slots)
        filled = sum(1 for e in slots.values() if e.get("mac") or e.get("ip") or e.get("name"))
        panels = ", ".join(sorted({p.get("panel_mac") or p.get("src_ip") or "?"
                                   for p in pages}))
        self.head.setText(f"Panel: {panels} · wpisy wypełnione: {filled} "
                          f"(z {len(slots)} odebranych)")

    def _fill(self, slots: dict):
        rows = sorted(slots.items())
        self.table.setRowCount(len(rows))
        for r, (slot, e) in enumerate(rows):
            try:
                g, c = sony_csv.slot_to_group_camera(slot)
                gc = f"{g}-{c:02d}"
            except Exception:
                gc = "-"
            empty = not (e.get("mac") or e.get("ip") or e.get("name"))
            cells = [f"{slot:03d}", gc, e.get("name") or "", e.get("mac") or "", e.get("ip") or ""]
            for col, txt in enumerate(cells):
                it = QTableWidgetItem(txt if not empty or col < 2 else "")
                if col == 0:
                    it.setTextAlignment(Qt.AlignCenter)
                if empty and col >= 2:
                    it.setForeground(Qt.gray)
                self.table.setItem(r, col, it)

    # -- CSV -----------------------------------------------------------------
    def export_csv(self):
        slots = self._slots
        if not slots:
            QMessageBox.information(self, "CSV", "Najpierw odczytaj tabelę z panelu "
                                                 "(albo wczytaj plik do podglądu).")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Eksport tabeli (CSV Sony)", "rmip_table.csv", "CSV (*.csv);;Wszystkie pliki (*)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8", newline="") as f:
                f.write(sony_csv.table_csv_text(slots))
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "CSV", f"Nie udało się zapisać: {e}")
            return
        self.raw.appendPlainText(f"[CSV] zapisano tabelę -> {path}")
        QMessageBox.information(self, "CSV", f"Zapisano tabelę (format Sony):\n{path}")

    def import_csv(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Wczytaj tabelę CSV (Sony)", "", "CSV (*.csv);;Wszystkie pliki (*)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
                text = f.read()
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "CSV", f"Nie udało się wczytać: {e}")
            return
        parsed = sony_csv.parse_table_csv(text)
        rows = parsed["rows"]
        if parsed["warnings"]:
            extra = "" if len(parsed["warnings"]) <= 12 else \
                f"\n... i {len(parsed['warnings']) - 12} więcej"
            QMessageBox.warning(self, "CSV — ostrzeżenia",
                                "\n".join(parsed["warnings"][:12]) + extra)
        if not rows:
            QMessageBox.warning(self, "CSV", "Plik nie zawiera wierszy tabeli.")
            return
        self._file_mode = True
        self._slots = {r["slot"]: r for r in rows}
        self._fill(self._slots)
        filled = sum(1 for r in rows if r.get("mac") or r.get("ip") or r.get("name"))
        self.head.setText(f"Podgląd z pliku: {path} · wierszy: {len(rows)}, "
                          f"wypełnionych: {filled} · (bez zapisu do panelu)")

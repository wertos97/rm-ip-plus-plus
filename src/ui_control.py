"""Zakladka sterowania jedna kamera: PTZ (trzymanie + krok), zoom, focus,
ekspozycja, WB, presety, status. Wszystko przez zweryfikowane CGI."""
from __future__ import annotations

from PySide6.QtCore import Qt, QThread, Signal, QTimer, QRectF
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGridLayout, QHBoxLayout,
    QInputDialog, QLabel, QMessageBox, QPushButton, QScrollArea, QSlider,
    QSpinBox, QTabWidget, QVBoxLayout, QWidget,
)

try:
    from .cam_control import AM7_STEP_SCALE, AM7_WB_MODES, CameraAPI, rel16, rel20
    from .human import (IRIS_F, SHUTTER_50P, SHUTTER_50P_AM7, ae_level_ev, am7_iris_from_cam,
                        am7_iris_label, am7_iris_to_cam, expcomp_db, fmt_deg, gain_db, gain_db_am7,
                        pan_deg, pan_deg20, tilt_deg, tilt_deg20, zoom_x, zoom_x_max)
except ImportError:
    from cam_control import AM7_STEP_SCALE, AM7_WB_MODES, CameraAPI, rel16, rel20  # noqa: E402
    from human import (IRIS_F, SHUTTER_50P, SHUTTER_50P_AM7, ae_level_ev, am7_iris_from_cam,  # noqa: E402
                       am7_iris_label, am7_iris_to_cam, expcomp_db, fmt_deg, gain_db, gain_db_am7,
                       pan_deg, pan_deg20, tilt_deg, tilt_deg20, zoom_x, zoom_x_max)

DIRS = [("up-left", "↖", 0, 0), ("up", "↑", 0, 1), ("up-right", "↗", 0, 2),
        ("left", "←", 1, 0), ("home", "⌂", 1, 1), ("right", "→", 1, 2),
        ("down-left", "↙", 2, 0), ("down", "↓", 2, 1), ("down-right", "↘", 2, 2)]


class HoldButton(QPushButton):
    """Przycisk trzymany: press=start, release=stop. Hover nic nie wysyla."""

    def __init__(self, label, on_press, on_release):
        super().__init__(label)
        self._on_press = on_press
        self._on_release = on_release
        self._held = False
        self.setMinimumSize(52, 44)
        self.setFocusPolicy(Qt.NoFocus)

    def mousePressEvent(self, e):
        self._held = True
        try:
            self._on_press()
        except Exception:
            pass
        super().mousePressEvent(e)

    def _release(self):
        if not self._held:
            return
        self._held = False
        try:
            self._on_release()
        except Exception:
            pass

    def mouseReleaseEvent(self, e):
        self._release()
        super().mouseReleaseEvent(e)

    def leaveEvent(self, e):
        self._release()
        super().leaveEvent(e)


class SlotCard(QWidget):
    """Karta slotu (preset/kadr): miniatura wypelnia karte, na dole pasek z nazwa.

    Rysowana wlasnorecznie - QToolButton nie potrafi polozyc tekstu na miniaturze,
    przez co siatki wygladaly pusto."""

    clicked = Signal(int)

    def __init__(self, num: int, name: str = "", thumb: QPixmap | None = None,
                 empty_word: str = "free", tooltip: str = ""):
        super().__init__()
        self.num = num
        self.name = name or ""
        self.thumb = thumb
        self.empty_word = empty_word
        self.selected = False
        self.hover = False
        self.setMinimumSize(96, 88)
        from PySide6.QtWidgets import QSizePolicy
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setCursor(Qt.PointingHandCursor)
        if tooltip:
            self.setToolTip(tooltip)

    def set_selected(self, on: bool):
        on = bool(on)
        if on != self.selected:
            self.selected = on
            self.update()

    def enterEvent(self, e):
        self.hover = True
        self.update()

    def leaveEvent(self, e):
        self.hover = False
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit(self.num)

    def paintEvent(self, e):
        from PySide6.QtCore import QRectF as _RF
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = _RF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
        path = QPainterPath()
        path.addRoundedRect(r, 8, 8)
        p.fillPath(path, QColor("#1a1d21"))

        bar_h = 26.0
        img_r = _RF(r.x(), r.y(), r.width(), r.height() - bar_h)

        if self.thumb is not None and not self.thumb.isNull():
            p.save()
            p.setClipPath(path)
            pm = self.thumb
            w, h = img_r.width(), img_r.height()
            sw, sh = max(1, pm.width()), max(1, pm.height())
            k = max(w / sw, h / sh)
            dw, dh = sw * k, sh * k
            dx = img_r.x() + (w - dw) / 2
            dy = img_r.y() + (h - dh) / 2
            p.drawPixmap(_RF(dx, dy, dw, dh), pm, _RF(0, 0, sw, sh))
            g = QLinearGradient(0, r.bottom() - 64, 0, r.bottom())
            g.setColorAt(0.0, QColor(0, 0, 0, 0))
            g.setColorAt(1.0, QColor(0, 0, 0, 210))
            p.fillRect(_RF(r.x(), r.bottom() - 64, r.width(), 64), g)
            p.restore()
        else:
            f = p.font()
            f.setPointSize(20)
            f.setBold(True)
            p.setFont(f)
            p.setPen(QColor("#3d434b"))
            p.drawText(img_r, Qt.AlignCenter, str(self.num))

        # pasek z numerem i nazwa
        p.save()
        p.setClipPath(path)
        p.fillRect(_RF(r.x(), r.bottom() - bar_h, r.width(), bar_h),
                   QColor(9, 10, 12, 235))
        p.restore()
        p.setPen(QColor("#ffb14e") if self.selected else
                 (QColor("#e8eaed") if self.name else QColor("#6f757c")))
        f = p.font()
        f.setPointSize(10)
        f.setBold(True)
        p.setFont(f)
        txt = f"{self.num} · {self.name}" if self.name else f"{self.num} · {self.empty_word}"
        p.drawText(_RF(r.x() + 12, r.bottom() - bar_h, r.width() - 24, bar_h),
                   Qt.AlignVCenter | Qt.AlignLeft, txt)

        # ramka
        if self.selected:
            pen = QPen(QColor("#ff9e2c"), 2)
        elif self.hover:
            pen = QPen(QColor("#565c64"), 1.5)
        else:
            pen = QPen(QColor("#2b2f35"), 1)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(r, 8, 8)
        p.end()


class ThumbLoader(QThread):
    """Pobiera obrazki kafelkow w tle; wynik: {num: QPixmap}.

    jobs: lista (num, kind) gdzie kind='preset' (still_N.jpg, fallback
    miniaturka 64x36 z kamery) lub 'frame' (tylko still frame_N.jpg).
    Loader jest pasywny - nigdy nie rusza kamery.
    """
    done = Signal(object)  # object, nie dict - QPixmap nie konwertuje sie do QVariantMap

    def __init__(self, api: CameraAPI, jobs: list[tuple[int, str]]):
        super().__init__()
        self.api = api
        self.jobs = jobs

    def run(self):
        import os, tempfile
        out: dict[int, QPixmap] = {}
        cache = os.path.join(tempfile.gettempdir(), "rmip_thumbs", self.api.ip.replace(".", "_"))
        os.makedirs(cache, exist_ok=True)
        for num, kind in self.jobs:
            try:
                data = None
                fp = os.path.join(cache, f"{'still' if kind == 'preset' else 'frame'}_{num}.jpg")
                if os.path.exists(fp):
                    with open(fp, "rb") as f:
                        data = f.read()
                elif kind == "preset":
                    data = self.api.thumb(num)
                    if data and len(data) > 5000:
                        # miniaturka 64x36 z kamery - nie zapisuj, za slaba
                        pm = QPixmap()
                        if pm.loadFromData(data):
                            out[num] = pm
                        continue
                    if data:
                        with open(fp, "wb") as f:
                            f.write(data)
                if data:
                    pm = QPixmap()
                    if pm.loadFromData(data):
                        out[num] = pm
            except Exception:
                continue
        self.done.emit(out)


def save_still(api: CameraAPI, name: str) -> bool:
    """Zapisuje ostry still do cache. Zwraca powodzenie."""
    import os, tempfile
    try:
        data = api.still()
        if not data:
            return False
        cache = os.path.join(tempfile.gettempdir(), "rmip_thumbs", api.ip.replace(".", "_"))
        os.makedirs(cache, exist_ok=True)
        with open(os.path.join(cache, name), "wb") as f:
            f.write(data)
        return True
    except Exception:
        return False


class PresetPanel(QWidget):
    """Siatka presetow 1-256 (stronicowana po 16): przywolanie/zapis/czyszczenie/nazwy."""

    def __init__(self, api: CameraAPI, log, names: dict[int, str] | None = None):
        super().__init__()
        self.api = api
        self.log = log
        self.names = dict(names or {})
        self.thumbs: dict[int, QPixmap] = {}
        self.page = 0
        self.mode = "recall"
        self.max_num = 256      # BRC-AM7: 100 (PresetNum); SRG: 256
        self._speed_on = True
        self._build()
        self.reload()

    def _build(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(10, 10, 10, 10)
        v.setSpacing(8)
        top = QHBoxLayout()
        top.setSpacing(8)
        v.addLayout(top)
        self.btn_recall = QPushButton("Recall")
        self.btn_recall.setCheckable(True)
        self.btn_recall.setChecked(True)
        self.btn_save = QPushButton("Save")
        self.btn_save.setCheckable(True)
        for b, m in ((self.btn_recall, "recall"), (self.btn_save, "save")):
            b.clicked.connect(lambda _, mm=m: self.set_mode(mm))
            top.addWidget(b)
        top.addWidget(QLabel("Speed:"))
        self.sp_speed = QSpinBox()
        self.sp_speed.setRange(1, 25)
        self.sp_speed.setValue(10)
        self.sp_speed.setMaximumWidth(84)
        top.addWidget(self.sp_speed)
        self.btn_clear = QPushButton("Clear slot")
        self.btn_clear.clicked.connect(self.clear_slot)
        top.addWidget(self.btn_clear)
        self.btn_rename = QPushButton("Rename")
        self.btn_rename.clicked.connect(self.rename_slot)
        top.addWidget(self.btn_rename)
        self.btn_thumbs = QPushButton("Generate thumbnails")
        self.btn_thumbs.setToolTip("The camera will move.")
        self.btn_thumbs.clicked.connect(self.generate_thumbs)
        top.addWidget(self.btn_thumbs)
        nav = QHBoxLayout()
        nav.setSpacing(8)
        v.addLayout(nav)
        self.btn_prev = QPushButton("◀ 1-16")
        self.btn_prev.setMinimumWidth(96)
        self.btn_prev.clicked.connect(lambda: self.set_page(self.page - 1))
        nav.addWidget(self.btn_prev)
        self.lb_page = QLabel()
        self.lb_page.setStyleSheet("color: #9aa0a6;")
        nav.addWidget(self.lb_page, 1)
        self.btn_next = QPushButton("241-256 ▶")
        self.btn_next.setMinimumWidth(96)
        self.btn_next.clicked.connect(lambda: self.set_page(self.page + 1))
        nav.addWidget(self.btn_next)
        self.grid = QGridLayout()
        self.grid.setContentsMargins(0, 2, 0, 0)
        self.grid.setSpacing(10)
        v.addLayout(self.grid, 1)
        self.slot = 1

    def set_mode(self, m):
        self.mode = m
        self.btn_recall.setChecked(m == "recall")
        self.btn_save.setChecked(m == "save")
        base = self.page * 16
        self.lb_page.setText(f"Slots {base + 1}-{min(base + 16, self.max_num)}" + ("" if m == "recall" else " · will overwrite!"))

    def set_page(self, p):
        self.page = max(0, min((self.max_num - 1) // 16, p))
        self.reload()

    def set_max(self, n: int, speed: bool = True):
        """BRC-AM7: 100 presetow i brak predkosci przy przywolaniu (ustawia ja kamera)."""
        n = max(16, int(n))
        if n == self.max_num and speed == self._speed_on:
            return
        self.max_num = n
        self._speed_on = speed
        self.sp_speed.setEnabled(speed)
        self.sp_speed.setToolTip("" if speed else "BRC-AM7: speed is set in the camera.")
        self.page = max(0, min((self.max_num - 1) // 16, self.page))
        self.reload()

    def reload(self):
        while self.grid.count():
            w = self.grid.takeAt(0).widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        base = self.page * 16
        self.lb_page.setText(f"Slots {base + 1}-{min(base + 16, self.max_num)}" + ("" if self.mode == "recall" else " · will overwrite!"))
        last = (self.max_num - 1) // 16
        self.btn_prev.setText(f"◀ {max(1, base - 15)}-{base}" if base else "◀")
        self.btn_next.setText(f"{base + 17}-{min(base + 32, self.max_num)} ▶" if self.page < last else "▶")
        for i in range(16):
            num = base + i + 1
            if num > self.max_num:
                continue
            name = self.names.get(num, "")
            tip = f"Preset {num}" + (f": {name}" if name else " (free)")
            card = SlotCard(num, name, self.thumbs.get(num), "free", tip)
            card.set_selected(num == self.slot)
            card.clicked.connect(self.activate)
            self.grid.addWidget(card, i // 4, i % 4)
        for i in range(4):
            self.grid.setRowStretch(i, 1)
            self.grid.setColumnStretch(i, 1)
        self.load_thumbs([n for n in (base + i + 1 for i in range(16))
                          if n <= self.max_num and n in self.names and n not in self.thumbs])

    def _apply_selection(self):
        for i in range(self.grid.count()):
            w = self.grid.itemAt(i).widget()
            if isinstance(w, SlotCard):
                w.set_selected(w.num == self.slot)

    def load_thumbs(self, nums):
        if not nums:
            return
        if hasattr(self, "_tl") and self._tl.isRunning():
            return
        self._tl = ThumbLoader(self.api, [(n, "preset") for n in nums])
        self._tl.done.connect(self.apply_thumbs)
        self._tl.start()

    def apply_thumbs(self, thumbs: dict):
        new = {k: v for k, v in thumbs.items() if k not in self.thumbs}
        if not new:
            return
        self.thumbs.update(new)
        self.reload()

    def generate_thumbs(self):
        defined = sorted(n for n in self.names if n <= self.max_num)
        if not defined:
            QMessageBox.information(self, "Thumbnails", "No presets defined.")
            return
        if QMessageBox.question(
                self, "Generate thumbnails",
                f"The camera will visit {len(defined)} presets and save thumbnails. Continue?",
                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        import time
        self.log(f"[{self.api.ip}] Generating thumbnails ({len(defined)})...")
        QApplication = None
        try:
            from PySide6.QtWidgets import QApplication as _QA
            QApplication = _QA
        except Exception:
            pass
        for num in defined:
            ok, msg = self.api.preset_recall(num)
            if not ok:
                self.log(f"[{self.api.ip}] preset {num}: BLAD {msg[:80]}")
                continue
            # czekaj na idle (max 15 s)
            t0 = time.time()
            while time.time() - t0 < 15:
                if QApplication is not None:
                    QApplication.processEvents()
                time.sleep(0.5)
                ok, pt = self.api.status()
                if ok and isinstance(pt, dict) and "moving" not in pt.get("PtzfStatus", ""):
                    break
            name = self.names.get(num, f"Preset{num}")
            ok, msg = self.api.preset_set(num, name, "on")
            still_ok = save_still(self.api, f"still_{num}.jpg") if ok else False
            self.log(f"[{self.api.ip}] miniaturka {num}: {'OK' if ok else 'ERROR ' + msg[:80]}"
                     + ("" if still_ok else " (bad frame from camera)"))
        # wyczysc cache i przeladuj
        try:
            import os, shutil, tempfile
            shutil.rmtree(os.path.join(tempfile.gettempdir(), "rmip_thumbs",
                                       self.api.ip.replace(".", "_")), ignore_errors=True)
        except Exception:
            pass
        self.thumbs = {}
        self.load_thumbs([n for n in defined if n in range(self.page * 16 + 1, self.page * 16 + 17)])
        self.log(f"[{self.api.ip}] Done.")

    def refresh_names(self, names):
        self.names = dict(names)
        self.reload()

    def activate(self, num):
        self.slot = num
        self._apply_selection()
        if self.mode == "recall":
            ok, msg = self.api.preset_recall(num, self.sp_speed.value())
            self.log(f"[{self.api.ip}] Preset {num} przywolaj: {'OK' if ok else 'ERROR ' + msg[:100]}")
            if not ok:
                QMessageBox.warning(self, "Preset", msg[:300])
        else:
            name, okd = QInputDialog.getText(self, "Save preset",
                                             f"Preset name {num}:",
                                             text=self.names.get(num, f"Preset{num}"))
            if not okd:
                return
            name = self.names.get(num, f"Preset{num}")
            ok, msg = self.api.preset_set(num, name, "on")
            self.log(f"[{self.api.ip}] Preset {num} zapisz: {'OK' if ok else 'ERROR ' + msg[:100]}")
            if ok:
                save_still(self.api, f"still_{num}.jpg")  # ostry kadr od razu
                ok2, names = self.api.preset_list()
                if ok2:
                    self.refresh_names(names)

    def clear_slot(self):
        ok, msg = self.api.preset_clear(self.slot)
        self.log(f"[{self.api.ip}] Preset {self.slot} wyczysc: {'OK' if ok else 'ERROR ' + msg[:100]}")
        if ok:
            try:
                import os, tempfile
                fp = os.path.join(tempfile.gettempdir(), "rmip_thumbs",
                                  self.api.ip.replace(".", "_"), f"still_{self.slot}.jpg")
                if os.path.exists(fp):
                    os.remove(fp)
                self.thumbs.pop(self.slot, None)
            except Exception:
                pass
            ok2, names = self.api.preset_list()
            if ok2:
                self.refresh_names(names)

    def rename_slot(self):
        name, okd = QInputDialog.getText(self, "Preset name", f"Slot {self.slot}:",
                                         text=self.names.get(self.slot, ""))
        if not okd:
            return
        ok, msg = self.api.preset_rename(self.slot, name)
        self.log(f"[{self.api.ip}] Preset {self.slot} nazwa: {'OK' if ok else 'ERROR ' + msg[:100]}")
        if ok:
            self.names[self.slot] = name
            self.reload()


class PadButton(QPushButton):
    """Jeden pad do dwoch trybow: jazda (przytrzymaj) albo krok (klik).
    Stop wysylany tylko po faktycznym wcisnieciu (hover nic nie robi)."""

    def __init__(self, label, action):
        super().__init__(label)
        self._action = action  # fn(hold: bool)
        self._held = False
        self.setMinimumSize(68, 56)
        f = self.font()
        f.setPointSize(22)
        f.setBold(True)
        self.setFont(f)
        self.setFocusPolicy(Qt.NoFocus)

    def mousePressEvent(self, e):
        self._held = True
        try:
            self._action(True)
        except Exception:
            pass
        super().mousePressEvent(e)

    def _release(self):
        if not self._held:
            return
        self._held = False
        try:
            self._action(False)
        except Exception:
            pass

    def mouseReleaseEvent(self, e):
        self._release()
        super().mouseReleaseEvent(e)

    def leaveEvent(self, e):
        self._release()  # zjechanie z wcisnietego przycisku = stop (bezpieczenstwo)
        super().leaveEvent(e)


class FramePanel(QWidget):
    """Kadry PTZ (lokalne, tylko pozycja - imaging nietkniety).

    W przeciwienstwie do presetow kamery (std: PTZ + imaging), kadr zapisuje
    wylacznie AbsolutePTZF w konfiguracji aplikacji i przywraca jednym
    rozkazem - kolory/WB/ekspozycja nigdy sie nie zmieniaja.
    """

    def __init__(self, api: CameraAPI, log, frames, on_change):
        super().__init__()
        self.api = api
        self.log = log
        self.frames: list = list(frames or [None] * 16)
        while len(self.frames) < 16:
            self.frames.append(None)
        self.on_change = on_change
        self.mode = "recall"
        self.slot = 0
        self.thumbs: dict[int, QPixmap] = {}
        self._build()
        self.reload()

    def _build(self):
        from PySide6.QtWidgets import QSizePolicy, QToolButton
        v = QVBoxLayout(self)
        v.setContentsMargins(10, 10, 10, 10)
        v.setSpacing(8)
        top = QHBoxLayout()
        top.setSpacing(8)
        v.addLayout(top)
        self.btn_recall = QPushButton("Go to")
        self.btn_recall.setCheckable(True)
        self.btn_recall.setChecked(True)
        self.btn_save = QPushButton("Save")
        self.btn_save.setCheckable(True)
        for b, m in ((self.btn_recall, "recall"), (self.btn_save, "save")):
            b.clicked.connect(lambda _, mm=m: self.set_mode(mm))
            top.addWidget(b)
        self.btn_fclear = QPushButton("Clear")
        self.btn_fclear.clicked.connect(self.clear_frame)
        top.addWidget(self.btn_fclear)
        top.addStretch(1)
        self.grid = QGridLayout()
        self.grid.setContentsMargins(0, 2, 0, 0)
        self.grid.setSpacing(10)
        v.addLayout(self.grid, 1)
        self.slot = 0

    def set_mode(self, m):
        self.mode = m
        self.btn_recall.setChecked(m == "recall")
        self.btn_save.setChecked(m == "save")
        self.reload()

    def reload(self):
        from PySide6.QtWidgets import QSizePolicy, QToolButton  # noqa: F401
        while self.grid.count():
            w = self.grid.takeAt(0).widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        for i in range(16):
            fr = self.frames[i]
            name = fr["name"] if fr else ""
            tip = (f"PTZ {','.join(fr['ptzf'])}") if fr else \
                f"Shot {i + 1} empty"
            card = SlotCard(i + 1, name, self.thumbs.get(i), "empty", tip)
            card.set_selected(i == self.slot)
            card.clicked.connect(lambda n: self.activate(n - 1))
            self.grid.addWidget(card, i // 4, i % 4)
        for i in range(4):
            self.grid.setRowStretch(i, 1)
            self.grid.setColumnStretch(i, 1)
        self.load_thumbs()

    def _apply_selection(self):
        for i in range(self.grid.count()):
            w = self.grid.itemAt(i).widget()
            if isinstance(w, SlotCard):
                w.set_selected((w.num - 1) == self.slot)

    def activate(self, i: int):
        self.slot = i
        self._apply_selection()
        if self.mode == "recall":
            fr = self.frames[i]
            if not fr:
                QMessageBox.information(self, "Shot", f"Slot {i + 1} is empty - switch to Save.")
                return
            p, t, z, f = fr["ptzf"]
            ok, msg = self.api.absolute_ptzf(p, t, z, f)
            self.log(f"[{self.api.ip}] Kadr {i + 1} ({fr['name']}): {'OK' if ok else 'ERROR ' + msg[:100]}")
            if not ok:
                QMessageBox.warning(self, "Shot", msg[:300])
        else:
            ok, pt = self.api.status()
            if not ok or not isinstance(pt, dict) or "," not in pt.get("AbsolutePTZF", ""):
                QMessageBox.warning(self, "Shot", f"Could not read the position: {pt}"[:200])
                return
            cur = pt["AbsolutePTZF"].split(",")[:4]
            name, okd = QInputDialog.getText(self, "Save shot", f"Shot name {i + 1}:",
                                             text=(self.frames[i] or {}).get("name", f"Shot{i + 1}") if isinstance(self.frames[i], dict) else f"Shot{i + 1}")
            if not okd:
                return
            self.frames[i] = {"name": name or f"Shot{i + 1}", "ptzf": cur}
            save_still(self.api, f"frame_{i}.jpg")
            self.on_change()
            self.reload()
            self.log(f"[{self.api.ip}] Shot {i + 1} saved: {name} ({','.join(cur)}).")

    def clear_frame(self):
        if not isinstance(self.frames[self.slot], dict):
            return
        self.frames[self.slot] = None
        try:
            import os, tempfile
            fp = os.path.join(tempfile.gettempdir(), "rmip_thumbs",
                              self.api.ip.replace(".", "_"), f"frame_{self.slot}.jpg")
            if os.path.exists(fp):
                os.remove(fp)
        except Exception:
            pass
        self.on_change()
        self.reload()
        self.log(f"[{self.api.ip}] Shot {self.slot + 1} deleted.")

    def load_thumbs(self):
        jobs = [(i, "frame") for i, fr in enumerate(self.frames)
                if fr and i not in self.thumbs]
        if not jobs:
            return
        if hasattr(self, "_tl") and self._tl.isRunning():
            return
        self._tl = ThumbLoader(self.api, jobs)
        self._tl.done.connect(self.apply_thumbs)
        self._tl.start()

    def apply_thumbs(self, thumbs: dict):
        new = {k: v for k, v in thumbs.items() if k not in self.thumbs}
        if not new:
            return
        self.thumbs.update(new)
        self.reload()


class _StatusPoll(QThread):
    """Odczyt statusu PTZF poza watkiem GUI.

    Kiedy kamera nie odpowiada (np. inna siec), requests czeka nawet 8 s -
    na watku GUI to zamulenie calego okna, wiec polling idzie w tle."""
    done = Signal(bool, dict)

    def __init__(self, api, timeout: float = 2.0, parent=None):
        super().__init__(parent)
        self.api = api
        self.timeout = timeout

    def run(self):
        try:
            ok, pt = self.api.status(timeout=self.timeout)
        except Exception:
            ok, pt = False, {}
        self.done.emit(bool(ok), pt if isinstance(pt, dict) else {})


class CameraTab(QWidget):
    def __init__(self, ip: str, user: str, password: str, http_port: int = 80, log=None,
                 frames=None, save_frames=None, reachable: bool = True):
        super().__init__()
        self.api = CameraAPI(ip, user, password, http_port)
        self.log = log or (lambda t: None)
        self.preset_names: dict[int, str] = {}
        self.frames: list = list(frames or [None] * 16)
        while len(self.frames) < 16:
            self.frames.append(None)
        self.save_frames = save_frames or (lambda: None)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.pages = QTabWidget()
        outer.addWidget(self.pages, 1)
        ctrl = QWidget()
        self._build(ctrl)
        self.pages.addTab(ctrl, "Control")
        self.preset_panel = PresetPanel(self.api, self.log_line)
        self.pages.addTab(self.preset_panel, "Presets")
        self.frame_panel = FramePanel(self.api, self.log_line, self.frames, self.on_frames_changed)
        self.pages.addTab(self.frame_panel, "Shots")
        # dolny pasek: status + szybkie kadry 1-6
        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 12, 0, 0)
        bottom.setSpacing(8)
        outer.addLayout(bottom)
        bottom.addWidget(self.status, 1)
        bottom.addSpacing(16)
        lb_k = QLabel("SHOTS:")
        lb_k.setProperty("sec", "1")
        bottom.addWidget(lb_k)
        bottom.addSpacing(6)
        self.quick_btns: list[QPushButton] = []
        for n in range(1, 7):
            b = QPushButton(str(n))
            b.setMinimumSize(96, 38)
            b.setMaximumWidth(170)
            b.setFocusPolicy(Qt.NoFocus)
            b.clicked.connect(lambda _, nn=n: self.quick_frame(nn))
            bottom.addWidget(b)
            self.quick_btns.append(b)
        # pelny odczyt tylko gdy kamera odpowiada - inaczej kazde zapytanie
        # wisialoby po 8 s na watku GUI; status dociagnie polling w tle
        self._need_full_refresh = not reachable
        if reachable:
            self.refresh_all()
        self._poll: _StatusPoll | None = None
        self._poll_fails = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll_status)
        self.timer.start(2000)

    def log_line(self, t: str):
        self.log(t)

    def on_frames_changed(self):
        self.frames = list(self.frame_panel.frames)
        self.refresh_quick()
        self.save_frames()

    # ---------- budowa ----------
    def _build(self, base: QWidget):
        from PySide6.QtWidgets import QButtonGroup, QGroupBox, QRadioButton, QSizePolicy
        root = QHBoxLayout(base)
        root.setContentsMargins(12, 10, 12, 12)
        root.setSpacing(10)

        # ---- kolumna PTZ: pad + karta "Ruch" ----
        col1 = QVBoxLayout()
        col1.setSpacing(10)
        root.addLayout(col1, 1)
        gb_ptz = QGroupBox("PTZ")
        gb_ptz.setMinimumWidth(300)
        col1.addWidget(gb_ptz)
        left = QVBoxLayout(gb_ptz)
        left.setContentsMargins(10, 8, 10, 10)
        left.setSpacing(8)
        pad = QGridLayout()
        pad.setSpacing(8)
        left.addLayout(pad)
        for direction, label, r, c in DIRS:
            if direction == "home":
                b = QPushButton("HOME")
                f = b.font()
                f.setPointSize(13)
                f.setBold(True)
                b.setFont(f)
                b.setMinimumSize(68, 72)
                b.setFocusPolicy(Qt.NoFocus)
                b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                b.clicked.connect(lambda: self.run(self.api.home(), "Home"))
            else:
                b = PadButton(label, lambda hold, d=direction: self.pad_action(d, hold))
                b.setMinimumSize(68, 72)
                b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            pad.addWidget(b, r, c)
        col1.addStretch(1)
        gb_ruch = QGroupBox("Move")
        col1.addWidget(gb_ruch)
        rl = QVBoxLayout(gb_ruch)
        rl.setContentsMargins(10, 8, 10, 10)
        rl.setSpacing(8)
        mode_row = QHBoxLayout()
        mode_row.setSpacing(8)
        rl.addLayout(mode_row)
        self.rb_drive = QRadioButton("Drive")
        self.rb_drive.setChecked(True)
        self.rb_step = QRadioButton("Step")
        mode_row.addWidget(self.rb_drive)
        mode_row.addWidget(self.rb_step)
        mode_row.addStretch(1)
        row = QHBoxLayout()
        row.setSpacing(8)
        rl.addLayout(row)
        row.addWidget(QLabel("Speed:"))
        self.sl_speed = QSlider(Qt.Horizontal)
        self.sl_speed.setRange(0, 24)
        self.sl_speed.setValue(8)
        self.sl_speed.setTickPosition(QSlider.TicksBelow)
        self.sl_speed.setTickInterval(4)
        self.sl_speed.valueChanged.connect(lambda v: self.lb_speed.setText("auto" if v == 0 else str(v)))
        row.addWidget(self.sl_speed, 1)
        self.lb_speed = QLabel("8")
        self.lb_speed.setMinimumWidth(44)
        f = self.lb_speed.font()
        f.setPointSize(11)
        f.setBold(True)
        self.lb_speed.setFont(f)
        row.addWidget(self.lb_speed)
        row2 = QHBoxLayout()
        row2.setSpacing(8)
        rl.addLayout(row2)
        row2.addWidget(QLabel("Step size:"))
        self.sp_step = QSpinBox()
        self.sp_step.setRange(1, 2000)
        self.sp_step.setValue(80)
        self.sp_step.setMinimumWidth(90)
        row2.addWidget(self.sp_step)
        row2.addStretch(1)
        self.status = QLabel("status...")
        f = self.status.font()
        f.setFamily("Consolas")
        f.setPointSize(10)
        self.status.setFont(f)
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.RichText)
        self.status.setIndent(6)

        # ---- kolumna zoom/focus: karty "Zoom" i "Focus" ----
        col2 = QVBoxLayout()
        col2.setSpacing(10)
        root.addLayout(col2, 1)
        gb_zf = QGroupBox("Zoom")
        gb_zf.setMinimumWidth(280)
        col2.addWidget(gb_zf)
        mid = QVBoxLayout(gb_zf)
        mid.setContentsMargins(10, 8, 10, 10)
        mid.setSpacing(8)
        zr = QHBoxLayout()
        zr.setSpacing(8)
        mid.addLayout(zr)
        for label, direction in (("W−", "wide"), ("T+", "tele")):
            b = HoldButton(label, lambda d=direction: self.zoom_hold(d), lambda: self.zoom_stop())
            b.setMinimumHeight(60)
            f = b.font()
            f.setPointSize(14)
            f.setBold(True)
            b.setFont(f)
            zr.addWidget(b)
        zr2 = QVBoxLayout()
        zr2.setSpacing(8)
        mid.addLayout(zr2)
        zr2.addWidget(QLabel("Zoom speed:"))
        zrow = QHBoxLayout()
        zrow.setSpacing(8)
        zr2.addLayout(zrow)
        self.sl_zspeed = QSlider(Qt.Horizontal)
        self.sl_zspeed.setRange(0, 8)
        self.sl_zspeed.setValue(3)
        self.sl_zspeed.setTickPosition(QSlider.TicksBelow)
        self.sl_zspeed.setTickInterval(2)
        zrow.addWidget(self.sl_zspeed, 1)
        self.lb_zspeed = QLabel("3")
        self.lb_zspeed.setMinimumWidth(30)
        self.sl_zspeed.valueChanged.connect(lambda v: self.lb_zspeed.setText(str(v)))
        zrow.addWidget(self.lb_zspeed)
        col2.addStretch(1)
        gb_foc = QGroupBox("Focus")
        col2.addWidget(gb_foc)
        fl = QVBoxLayout(gb_foc)
        fl.setContentsMargins(10, 8, 10, 10)
        fl.setSpacing(8)
        fr = QHBoxLayout()
        fr.setSpacing(8)
        fl.addLayout(fr)
        for label, direction in (("Near", "near"), ("Far", "far")):
            b = HoldButton(label, lambda d=direction: self.focus_press(d),
                           lambda: self.focus_release())
            b.setMinimumHeight(54)
            fr.addWidget(b)
        self.btn_af1 = QPushButton("One Push AF")
        self.btn_af1.setMinimumHeight(54)
        self.btn_af1.clicked.connect(self.do_onepush_af)
        fl.addWidget(self.btn_af1)
        fr2 = QHBoxLayout()
        fr2.setSpacing(8)
        fl.addLayout(fr2)
        fr2.addWidget(QLabel("Focus mode:"))
        self.cb_focus = QComboBox()
        self.cb_focus.addItems(["auto", "manual"])
        self.cb_focus.setMinimumWidth(110)
        fr2.addWidget(self.cb_focus, 1)
        self.btn_focus = QPushButton("Set")
        self.btn_focus.setMaximumWidth(90)
        self.btn_focus.clicked.connect(lambda: self.run(
            self.api.set_focus_mode(self.cb_focus.currentText()), "FocusMode"))
        fr2.addWidget(self.btn_focus)

        # ---- kolumna obraz: karty "Ekspozycja" i "Balans bieli" ----
        col3 = QVBoxLayout()
        col3.setSpacing(10)
        root.addLayout(col3, 1)
        gb_img = QGroupBox("Exposure")
        col3.addWidget(gb_img)
        right = QVBoxLayout(gb_img)
        right.setContentsMargins(10, 8, 10, 10)
        right.setSpacing(8)
        form = QFormLayout()
        form.setSpacing(6)
        right.addLayout(form)
        self.cb_exp = QComboBox()
        self.cb_exp.addItems(["auto", "shutter", "iris", "manual"])
        form.addRow("Mode:", self.cb_exp)
        self.sl_iris = self._slider(form, "Iris:", 0, 25, lambda v: IRIS_F.get(v, "?"))
        self.sl_gain = self._slider(form, "Gain:", 1, 13, gain_db)
        self.sl_shut = self._slider(form, "Shutter:", 6, 33, lambda v: SHUTTER_50P.get(v, "?"))
        self.sl_comp = self._slider(form, "Comp. (+/-):", 0, 14, expcomp_db)
        self.btn_exp = QPushButton("Apply exposure")
        self.btn_exp.setProperty("kind", "primary")
        self.btn_exp.setMinimumHeight(36)
        self.btn_exp.clicked.connect(self.apply_exposure)
        right.addSpacing(6)
        right.addWidget(self.btn_exp)
        col3.addStretch(1)
        gb_wb = QGroupBox("White balance")
        col3.addWidget(gb_wb)
        wl = QVBoxLayout(gb_wb)
        wl.setContentsMargins(10, 8, 10, 10)
        wl.setSpacing(8)
        form2 = QFormLayout()
        form2.setSpacing(6)
        wl.addLayout(form2)
        self.cb_wb = QComboBox()
        self.cb_wb.addItems(["auto", "indoor", "outdoor", "onepushwb", "atw", "manual"])
        form2.addRow("Mode:", self.cb_wb)
        self.sl_cb = self._slider(form2, "B gain:", 0, 255)
        self.sl_cr = self._slider(form2, "R gain:", 0, 255)
        self.sl_wboff = self._slider(form2, "Offset:", 0, 14)
        wbrow = QHBoxLayout()
        wbrow.setSpacing(8)
        wl.addLayout(wbrow)
        self.btn_wb = QPushButton("Apply WB")
        self.btn_wb.setProperty("kind", "primary")
        self.btn_wb.setMinimumHeight(36)
        self.btn_wb.clicked.connect(self.apply_wb)
        wbrow.addWidget(self.btn_wb)
        self.btn_wb1 = QPushButton("One Push WB")
        self.btn_wb1.setMinimumHeight(36)
        self.btn_wb1.clicked.connect(self.do_onepush_wb)
        wbrow.addWidget(self.btn_wb1)
        self.btn_reload = QPushButton("Read from camera")
        self.btn_reload.clicked.connect(self.refresh_all)
        wl.addWidget(self.btn_reload)

    def _slider(self, form, label, lo, hi, fmt=None):
        row = QHBoxLayout()
        sl = QSlider(Qt.Horizontal)
        sl.setRange(lo, hi)
        lb = QLabel("?")
        lb.setMinimumWidth(64)
        lb.setProperty("val", "1")
        f = lb.font()
        f.setBold(True)
        lb.setFont(f)
        sl._fmt = fmt
        sl._lb = lb
        sl.valueChanged.connect(lambda v, s=sl: self._slider_refresh(s))
        row.addWidget(sl, 1)
        row.addWidget(lb)
        form.addRow(label, row)
        self._slider_refresh(sl)
        return sl

    def _slider_refresh(self, sl):
        lb = getattr(sl, "_lb", None)
        if lb is None:
            return
        v = sl.value()
        fmt = getattr(sl, "_fmt", None)
        lb.setText(str(v) if fmt is None else f"{v} ({fmt(v)})")

    def _slider_cfg(self, sl, lo, hi, fmt=None):
        """Zmiana zakresu/formatowania suwaka w locie (rozne jednostki SRG vs BRC-AM7)."""
        sl.blockSignals(True)
        sl.setRange(lo, hi)
        sl._fmt = fmt
        sl.blockSignals(False)
        self._slider_refresh(sl)

    @staticmethod
    def _parse_range(raw, dlo: int, dhi: int) -> tuple[int, int]:
        """'ExposureGainRange=6,45' -> (6, 45); brak/zle -> wartosci domyslne."""
        try:
            a, b = (int(x) for x in str(raw).split(",")[:2])
            if a < b:
                return a, b
        except (ValueError, TypeError):
            pass
        return dlo, dhi

    # ---------- akcje ----------
    def pt_speed(self) -> int:
        return self.sl_speed.value()

    def run(self, result, what: str):
        ok, msg = result
        self.log(f"[{self.api.ip}] {what}: {'OK' if ok else 'ERROR ' + msg[:120]}")
        if not ok:
            QMessageBox.warning(self, what, msg[:300])

    def pad_action(self, direction: str, hold: bool):
        """"Jazda": press=start, release=stop (klik = min. 0,5 s ruchu).
        "Krok": klik = 1 precyzyjny krok; przytrzymanie = plynny slizg (v1)."""
        if self.rb_step.isChecked():
            if hold:
                self._crawl_dir = direction
                self._gliding = False
                QTimer.singleShot(300, lambda: self._glide_start(direction))
            else:
                if getattr(self, "_gliding", False):
                    self._gliding = False
                    self._crawl_dir = None
                    self.run(self.api.stop("pantilt"), "Stop")
                else:
                    self._crawl_dir = None  # anuluj uzbrojony slizg
                    self.step_move(direction)
            return
        import time as _time
        if hold:
            self._jog_token = getattr(self, "_jog_token", 0) + 1
            self._jog_t0 = _time.monotonic()
            self.run(self.api.move(direction, self.pt_speed()), f"Move {direction}")
        else:
            dt = _time.monotonic() - getattr(self, "_jog_t0", 0.0)
            if dt < 0.5:
                # krotki klik: dojedz do 0,5 s zeby ruch byl odczuwalny
                # (wtedy Slow ON vs OFF widac golym okiem)
                tok = getattr(self, "_jog_token", 0)
                QTimer.singleShot(int((0.5 - dt) * 1000),
                                  lambda: self._stop_if(tok))
            else:
                self.run(self.api.stop("pantilt"), "Stop")

    def _stop_if(self, tok: int):
        if tok == getattr(self, "_jog_token", -1):
            self.run(self.api.stop("pantilt"), "Stop")

    def _glide_start(self, direction: str):
        if getattr(self, "_crawl_dir", None) != direction:
            return
        self._gliding = True
        self.run(self.api.move(direction, 1), f"Glide {direction}")

    def _crawl_tick(self):
        d = getattr(self, "_crawl_dir", None)
        if d:
            self.step_move(d)

    def step_move(self, direction: str):
        step = int(self.sp_step.value())
        fam = self.api.family
        if fam == "am7":
            step = int(round(step * AM7_STEP_SCALE))  # 20-bit, 1 jedn. = 0.001°
        dpan = dtilt = 0
        if "up" in direction:
            dtilt = step
        if "down" in direction:
            dtilt = -step
        if "left" in direction:
            dpan = -step
        if "right" in direction:
            dpan = step
        fmt = rel20 if fam == "am7" else rel16
        self.run(self.api.relative_pt(fmt(dpan), fmt(dtilt), max(1, self.pt_speed() or 5)),
                 f"Step {direction} {step}")

    def zoom_hold(self, direction: str):
        self.run(self.api.zoom_move(direction, self.sl_zspeed.value()), f"Zoom {direction}")

    def zoom_stop(self):
        self.run(self.api.stop("zoom"), "Stop")

    def focus_press(self, direction: str):
        if self.api.family == "am7":
            # AM7: brak ciaglego ruchu focus - krok co ~110 ms, dopoki trzymasz
            self._focus_dir = direction
            self.focus_step()
            if not hasattr(self, "_focus_timer"):
                self._focus_timer = QTimer(self)
                self._focus_timer.setInterval(110)
                self._focus_timer.timeout.connect(self.focus_step)
            self._focus_timer.start()
        else:
            self.run(self.api.focus_move(direction), f"Focus {direction}")

    def focus_step(self):
        d = getattr(self, "_focus_dir", None)
        if not d:
            return
        ok, msg = self.api.focus_step(d)
        if not ok:
            if hasattr(self, "_focus_timer"):
                self._focus_timer.stop()
            self.log(f"[{self.api.ip}] Focus step: ERROR {msg[:100]}")

    def focus_release(self):
        if self.api.family == "am7":
            self._focus_dir = None
            if hasattr(self, "_focus_timer"):
                self._focus_timer.stop()
        else:
            self.run(self.api.stop("focus"), "Stop")

    def do_onepush_af(self):
        if self.api.family == "am7":
            self.run(self.api.one_push_af_press(), "OnePushAF")
            QTimer.singleShot(250, lambda: self.api.one_push_af_release())
        else:
            self.run(self.api.focus_move("onepushaf"), "OnePushAF")

    def do_onepush_wb(self):
        if self.api.family == "am7":
            self.run(self.api.wb_onepush(), "OnePushWB")
            QTimer.singleShot(250, lambda: self.api.wb_onepush_release())
        else:
            self.run(self.api.wb_onepush(), "OnePushWB")

    def apply_exposure(self):
        if self.api.family == "am7":
            self.run(self.api.set_exposure_am7(
                self.cb_exp.currentText(), am7_iris_to_cam(self.sl_iris.value()),
                self.sl_gain.value(), self.sl_shut.value(), self.sl_comp.value()), "Exposure")
            return
        self.run(self.api.set_imaging(
            ExposureMode=self.cb_exp.currentText(),
            ExposureIris=self.sl_iris.value(), ExposureGain=self.sl_gain.value(),
            ExposureExposureTime=self.sl_shut.value(),
            ExposureCompensation=self.sl_comp.value()), "Exposure")

    def apply_wb(self):
        if self.api.family == "am7":
            self.run(self.api.set_wb_am7(
                self.cb_wb.currentText(), self.sl_cb.value(), self.sl_cr.value(),
                self.sl_wboff.value()), "WB")
            return
        self.run(self.api.set_imaging(
            WhiteBalanceMode=self.cb_wb.currentText(),
            WhiteBalanceCbGain=self.sl_cb.value(), WhiteBalanceCrGain=self.sl_cr.value(),
            WhiteBalanceOffset=self.sl_wboff.value()), "WB")

    def status_text(self, pt: dict) -> str:
        abspt = pt.get("AbsolutePTZF", "")
        parts = abspt.split(",")
        st = pt.get("PtzfStatus", "")
        vals = [s.strip() for s in st.split(",") if s.strip()]
        uniq = list(dict.fromkeys(vals))
        st_txt = ", ".join(uniq) if uniq else "-"

        def dim(t):
            return f"<span style='color:#8b9198'>{t}</span>"

        def val(t):
            return f"<span style='color:#ffd9a0'>{t}</span>"

        if len(parts) >= 3:
            if self.api.family == "am7":
                pan_t, tilt_t, z_t = pan_deg20(parts[0]), tilt_deg20(parts[1]), zoom_x_max(parts[2], 25.0)
                if z_t == z_t and z_t > 25.0:
                    z_txt = "~25x+"
                else:
                    z_txt = f"~{z_t:.1f}x"
            else:
                pan_t, tilt_t, z_txt = pan_deg(parts[0]), tilt_deg(parts[1]), f"~{zoom_x(parts[2]):.1f}x"
            txt = (f"{dim('Pan')} {val(fmt_deg(pan_t))}&nbsp;&nbsp;"
                   f"{dim('Tilt')} {val(fmt_deg(tilt_t))}&nbsp;&nbsp;"
                   f"{dim('Zoom')} {val(z_txt)}"
                   f"&nbsp;&nbsp;{dim('|')}&nbsp;&nbsp;{dim(st_txt)}")
        else:
            txt = f"{dim('PTZF')} {val(abspt)}&nbsp;&nbsp;{dim('|')}&nbsp;&nbsp;{dim(st_txt)}"
        return txt

    def quick_frame(self, num: int):
        fr = self.frames[num - 1] if 1 <= num <= len(self.frames) else None
        if not isinstance(fr, dict):
            QMessageBox.information(self, "Shot", f"Shot {num} is empty.")
            return
        p, t, z, f = fr["ptzf"]
        ok, msg = self.api.absolute_ptzf(p, t, z, f)
        self.log(f"[{self.api.ip}] Szybki kadr {num} ({fr['name']}): {'OK' if ok else 'ERROR ' + msg[:100]}")
        if not ok:
            QMessageBox.warning(self, "Shot", msg[:300])

    def quick_recall(self, num: int):
        ok, msg = self.api.preset_recall(num)
        self.log(f"[{self.api.ip}] Szybki preset {num}: {'OK' if ok else 'ERROR ' + msg[:100]}")
        if not ok:
            QMessageBox.warning(self, "Preset", msg[:300])

    def refresh_quick(self):
        for b, n in zip(self.quick_btns, range(1, 7)):
            fr = self.frames[n - 1] if n - 1 < len(self.frames) else None
            nm_ = fr.get("name", "") if isinstance(fr, dict) else ""
            b.setToolTip(f"Kadr {n}" + (f": {nm_}" if nm_ else " (empty)"))
        self._mark_quick()

    def refresh_all(self):
        fam = self.api.family
        ok, pt = self.api.status()
        pt = pt if (ok and isinstance(pt, dict)) else None
        if pt:
            self.status.setText(self.status_text(pt))
        ok, im = self.api.imaging()
        if ok and isinstance(im, dict):
            if fam == "am7":
                self._apply_am7_imaging(im, pt)
            else:
                self._apply_srg_imaging(im)
        ok, names = self.api.preset_list()
        if ok:
            self.preset_names = names
            self.preset_panel.refresh_names(names)
        self.preset_panel.set_max(100 if fam == "am7" else 256, speed=(fam != "am7"))
        self.refresh_quick()

    def _apply_srg_imaging(self, im: dict):
        self._set_combo(self.cb_exp, im.get("ExposureMode", "auto"))
        self._set_slider(self.sl_iris, im.get("ExposureIris"))
        self._set_slider(self.sl_gain, im.get("ExposureGain"))
        self._set_slider(self.sl_shut, im.get("ExposureExposureTime"))
        self._set_slider(self.sl_comp, im.get("ExposureCompensation"))
        self._set_combo(self.cb_wb, im.get("WhiteBalanceMode", "auto"))
        self._set_slider(self.sl_cb, im.get("WhiteBalanceCbGain"))
        self._set_slider(self.sl_cr, im.get("WhiteBalanceCrGain"))
        self._set_slider(self.sl_wboff, im.get("WhiteBalanceOffset"))
        self._set_combo(self.cb_focus, im.get("FocusMode", "auto"))

    def _apply_am7_imaging(self, im: dict, pt: dict | None):
        """BRC-AM7: inne itemy i jednostki - przeliczamy na widgety UI."""
        # tryb ekspozycji odtworzony z przelacznikow auto
        a_shut = (im.get("ExposureAutoShutterEnable", "on") or "on").lower() == "on"
        a_iris = (im.get("ExposureAutoIris", "on") or "on").lower() == "on"
        mode = "auto" if (a_shut and a_iris) else ("iris" if a_shut else ("shutter" if a_iris else "manual"))
        self._set_combo(self.cb_exp, mode)
        # iris: suwak 0..1025 (0=CLOSE, 1025=F2.8)
        self._slider_cfg(self.sl_iris, 0, 1025, am7_iris_label)
        if im.get("ExposureIris") is not None:
            self._set_slider(self.sl_iris, am7_iris_from_cam(im.get("ExposureIris")))
        lo, hi = self._parse_range(im.get("ExposureGainRange"), 6, 45)
        self._slider_cfg(self.sl_gain, lo, hi, gain_db_am7)
        self._set_slider(self.sl_gain, im.get("ExposureGain"))
        lo, hi = self._parse_range(im.get("ExposureExposureTimeRange"), 5, 25)
        self._slider_cfg(self.sl_shut, lo, hi, lambda v: SHUTTER_50P_AM7.get(v, "?"))
        self._set_slider(self.sl_shut, im.get("ExposureExposureTime"))
        self._slider_cfg(self.sl_comp, 0, 24, ae_level_ev)
        self._set_slider(self.sl_comp, im.get("ExposureCompensation"))
        # balans bieli: atw / memory_a / preset
        modes = list(AM7_WB_MODES)
        if [self.cb_wb.itemText(i) for i in range(self.cb_wb.count())] != modes:
            self.cb_wb.clear()
            self.cb_wb.addItems(modes)
        self._set_combo(self.cb_wb, im.get("WhiteBalanceMode", "atw"))
        self._slider_cfg(self.sl_cb, -990, 990)
        self._set_slider(self.sl_cb, im.get("WhiteBalanceCbGain"))
        self._slider_cfg(self.sl_cr, -990, 990)
        self._set_slider(self.sl_cr, im.get("WhiteBalanceCrGain"))
        self._slider_cfg(self.sl_wboff, -99, 99)
        self._set_slider(self.sl_wboff, im.get("WhiteBalanceOffsetColorTemp"))
        # tryb focus siedzi w ptzf na AM7 - moze przyjsc z ktoregos zapytania
        fm = im.get("FocusMode") or (pt or {}).get("FocusMode")
        if fm in ("auto", "manual"):
            self._set_combo(self.cb_focus, fm)

    def _set_combo(self, cb, val):
        i = cb.findText(str(val))
        if i >= 0:
            cb.setCurrentIndex(i)

    def _set_slider(self, sl, val):
        try:
            if val is not None:
                sl.setValue(int(val))
        except (ValueError, TypeError):
            pass

    def poll_status(self):
        if not self.isVisible():
            return
        if self._poll is not None and self._poll.isRunning():
            return
        self._poll = _StatusPoll(self.api, timeout=2.0)
        self._poll.done.connect(self.on_poll_done)
        self._poll.start()

    def on_poll_done(self, ok: bool, pt: dict):
        if ok and pt:
            self._poll_fails = 0
            self.timer.setInterval(2000)
            self.status.setText(self.status_text(pt))
            self.follow_position(pt)
            if self._need_full_refresh:  # kamera wrocila - uzupelnij tryby/sliders
                self._need_full_refresh = False
                self.refresh_all()
            return
        # backoff przy braku lacznosci - nie walimy w kamere co 2 s
        self._poll_fails = min(self._poll_fails + 1, 3)
        self.timer.setInterval((5000, 10000, 20000)[self._poll_fails - 1])
        if self._poll_fails >= 2:
            self.status.setText("no connection")

    def shutdown(self):
        """Domyka polling przed zamknieciem okna (bez blokowania GUI)."""
        self.timer.stop()
        if self._poll is not None and self._poll.isRunning():
            self._poll.wait(2500)

    def follow_position(self, pt: dict):
        """Podswietla kadr zgodny z biezaca pozycja (np. po ruchu z panelu RM-IP500).
        Panelu nie da sie przechwycic (gada z kamera bezposrednio, zwykle po RS-422),
        ale widac efekt - i to wystarczy zeby nadazyc."""
        try:
            cur = pt.get("AbsolutePTZF", "").split(",")[:4]
            if len(cur) < 4:
                return
            curi = [int(x, 16) for x in cur]
        except (ValueError, TypeError):
            return
        match = -1
        am7 = self.api.family == "am7"
        full = 0x100000 if am7 else 0x10000
        thr = 640 if am7 else 40   # ten sam kat fizyczny (0.001° vs 16-bit)
        for i, fr in enumerate(self.frames[:6]):
            if not isinstance(fr, dict):
                continue
            try:
                f = [int(x, 16) for x in fr["ptzf"][:4]]
            except (ValueError, TypeError, KeyError):
                continue
            dp = min(abs(f[0] - curi[0]), full - abs(f[0] - curi[0]))
            dt = min(abs(f[1] - curi[1]), full - abs(f[1] - curi[1]))
            dz = abs(f[2] - curi[2])
            if dp <= thr and dt <= thr and dz <= 80:
                match = i
                break
        if match != getattr(self, "_follow", -2):
            self._follow = match
            self._mark_quick()

    def _mark_quick(self):
        match = getattr(self, "_follow", -1)
        for b, n in zip(self.quick_btns, range(1, 7)):
            fr = self.frames[n - 1] if n - 1 < len(self.frames) else None
            nm_ = fr.get("name", "") if isinstance(fr, dict) else ""
            b.setText(f"{n} {nm_}"[:16] if nm_ else str(n))
            on = (n - 1 == match)
            b.setStyleSheet(
                "QPushButton { border: 2px solid #ff9e2c; background: #3a2c14;"
                " color: #ffb14e; font-weight: bold; }" if on else "")

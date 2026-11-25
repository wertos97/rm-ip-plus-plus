import time

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QInputDialog, QPushButton

import config_store
import theme
import ui_control
import ui_main
from demo_api import DemoCameraAPI
from ui_control import CameraTab, HoldButton, PadButton, PresetPanel, SlotCard


def test_theme_defines_pointer_and_focus_states():
    assert "cursor: pointer" in theme.QSS
    assert "cursor: not-allowed" in theme.QSS
    assert "QPushButton:focus" in theme.QSS
    assert "QSlider:focus" in theme.QSS


def test_tab_ip_uses_widget_property():
    class Widget:
        def property(self, name):
            return "192.168.1.10" if name == "ip" else None

    assert ui_main.tab_ip(Widget(), "fallback") == "192.168.1.10"
    assert ui_main.tab_ip(None, "fallback") == "fallback"


def test_save_frames_finds_tab_by_ip_not_label(monkeypatch):
    class Widget:
        frames = [{"name": "Wide", "ptzf": ["0000", "0000", "0000", "8000"]}]

        def property(self, name):
            return "192.168.1.10" if name == "ip" else None

    class Tabs:
        def count(self):
            return 1

        def widget(self, index):
            return Widget()

    class Window:
        ctrl_tabs = Tabs()
        config = {}
        save_frames = ui_main.MainWindow.save_frames

    saved = []
    monkeypatch.setattr(config_store, "save", saved.append)
    Window().save_frames("192.168.1.10")
    assert saved[0]["frames"]["192.168.1.10"] == Widget.frames


def test_hold_button_supports_keyboard(qapp):
    events = []
    button = HoldButton("W", lambda: events.append("start"), lambda: events.append("stop"), accessible_name="Zoom wide")
    button.show()
    qapp.processEvents()
    QTest.keyPress(button, Qt.Key_Space)
    assert events == ["start"]
    QTest.keyRelease(button, Qt.Key_Space)
    assert events == ["start", "stop"]
    assert button.accessibleName() == "Zoom wide"
    button.close()


def test_pad_button_stops_when_focus_is_lost(qapp):
    events = []
    button = PadButton("↑", lambda held: events.append(held), accessible_name="Move up")
    button.show()
    qapp.processEvents()
    QTest.keyPress(button, Qt.Key_Space)
    button.clearFocus()
    qapp.processEvents()
    assert events == [True, False]
    button.close()


def test_slot_card_is_a_native_accessible_button(qapp):
    card = SlotCard(1, "Wide", tooltip="Preset 1: Wide")
    assert isinstance(card, QPushButton)
    assert card.focusPolicy() == Qt.StrongFocus
    assert card.accessibleName() == "Preset 1: Wide"
    clicked = []
    card.clicked.connect(lambda checked: clicked.append(checked))
    card.show()
    qapp.processEvents()
    QTest.keyClick(card, Qt.Key_Space)
    assert clicked == [False]
    card.close()


def test_initial_camera_refresh_does_not_block_gui(qapp):
    class SlowCamera(DemoCameraAPI):
        def status(self, timeout=8):
            time.sleep(0.15)
            return super().status(timeout=timeout)

        def imaging(self, timeout=8):
            time.sleep(0.15)
            return super().imaging(timeout=timeout)

        def preset_list(self, timeout=8):
            time.sleep(0.15)
            return super().preset_list(timeout=timeout)

    tab = CameraTab("demo", "admin", "admin", api=SlowCamera())
    ticks = [0]
    from PySide6.QtCore import QTimer

    heartbeat = QTimer()
    heartbeat.setInterval(10)
    heartbeat.timeout.connect(lambda: ticks.__setitem__(0, ticks[0] + 1))
    heartbeat.start()
    deadline = time.monotonic() + 3
    while tab._refresh is not None and tab._refresh.isRunning() and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    heartbeat.stop()
    qapp.processEvents()
    assert ticks[0] >= 10
    assert "Pan" in tab.status.text()
    tab.shutdown()


def test_preset_save_keeps_entered_name(qapp, monkeypatch):
    class NoStillCamera(DemoCameraAPI):
        def still(self, timeout=8):
            return None

    api = NoStillCamera()
    panel = PresetPanel(api, lambda message: None)
    panel.mode = "save"
    panel.slot = 3
    monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kwargs: ("New name", True))
    panel.activate(3)
    assert api.preset_list()[1][3] == "New name"
    if hasattr(panel, "_tl"):
        panel._tl.wait(1000)


def test_thumbnail_refresh_does_not_move_or_overwrite_presets(qapp, monkeypatch, tmp_path):
    class RecordingCamera(DemoCameraAPI):
        def __init__(self):
            super().__init__()
            self.calls = []

        def preset_recall(self, num, speed=None):
            self.calls.append(("recall", num))
            return super().preset_recall(num, speed)

        def preset_set(self, num, name="", thumb="on"):
            self.calls.append(("set", num))
            return super().preset_set(num, name, thumb)

    api = RecordingCamera()
    api.preset_set(1, "One")
    api.calls.clear()
    monkeypatch.setattr(ui_control, "thumbnail_dir", lambda: str(tmp_path))
    panel = PresetPanel(api, lambda message: None, names={1: "One"})
    if hasattr(panel, "_tl"):
        panel._tl.wait(1000)
    qapp.processEvents()
    panel.refresh_thumbs()
    if hasattr(panel, "_tl"):
        panel._tl.wait(1000)
    qapp.processEvents()
    assert api.calls == []
    assert 1 in panel.thumbs


def test_am7_iso_mode_disables_gain_slider(qapp):
    class ISOCamera(DemoCameraAPI):
        @property
        def family(self):
            return "am7"

        def imaging(self, timeout=8):
            ok, data = super().imaging(timeout=timeout)
            data["ExposureISOGainMode"] = "iso"
            return ok, data

        def status(self, timeout=8):
            ok, data = super().status(timeout=timeout)
            data["PanTiltSpeedStep"] = "extended"
            return ok, data

    tab = CameraTab("demo", "admin", "Admin123", api=ISOCamera())
    deadline = time.monotonic() + 3
    while tab._refresh is not None and tab._refresh.isRunning() and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    qapp.processEvents()
    assert not tab.sl_gain.isEnabled()
    assert tab.sl_gain._lb.text() == "ISO mode"
    tab.shutdown()


def test_scan_worker_reports_invalid_subnet(qapp):
    errors = []
    worker = ui_main.ScanWorker("full", "not-a-subnet", lambda ip: None)
    worker.error.connect(errors.append)
    worker.run()
    assert errors
    assert "not-a-subnet" in errors[0]

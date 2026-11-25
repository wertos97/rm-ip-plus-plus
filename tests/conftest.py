import os
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(autouse=True)
def isolated_user_data(tmp_path, monkeypatch):
    import config_store
    import net_manager

    app_dir = tmp_path / "AppData" / "Roaming" / "RMIP++"
    monkeypatch.setattr(config_store, "APP_DIR", str(app_dir))
    monkeypatch.setattr(config_store, "CONFIG_FILE", str(app_dir / "config.json"))
    monkeypatch.setattr(net_manager, "STATE_FILE", str(tmp_path / "temp_ips.json"))


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


def wait_until(qapp, predicate, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        qapp.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    qapp.processEvents()
    return predicate()

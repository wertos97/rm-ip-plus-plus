"""Podglad 3 wariantow stylu panelu obrazu (mock, bez kamery). argv: A|B|C"""
import sys, os
os.environ.pop("QT_QPA_PLATFORM", None)
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                               QFormLayout, QLabel, QSlider, QComboBox, QPushButton,
                               QGroupBox)
from PySide6.QtCore import Qt

VAR = sys.argv[1] if len(sys.argv) > 1 else "A"

QSS = {
"A": """
QWidget { background: #101214; color: #e8eaed; font-size: 13px; }
QGroupBox { border: 1px solid #2a2e33; border-radius: 6px; margin-top: 14px; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; color: #0090d4;
  letter-spacing: 2px; font-weight: bold; }
QLabel[sec="1"] { color: #7f868d; letter-spacing: 2px; font-weight: bold; font-size: 11px; }
QSlider::groove:horizontal { height: 3px; background: #2a2e33; }
QSlider::handle:horizontal { width: 14px; height: 14px; background: #0090d4;
  border-radius: 7px; margin: -6px 0; }
QComboBox, QPushButton { background: #1c2024; border: 1px solid #2a2e33;
  border-radius: 4px; padding: 6px; }
QPushButton:hover { border-color: #0090d4; }
QLabel[val="1"] { color: #0090d4; font-weight: bold; font-size: 14px; }
""",
"B": """
QWidget { background: #16181d; color: #f0f0f0; font-size: 13px; }
QGroupBox { border: none; border-top: 2px solid #ff8c00; margin-top: 12px; }
QGroupBox::title { subcontrol-origin: margin; left: 6px; color: #ff8c00;
  font-weight: bold; letter-spacing: 1px; }
QLabel[sec="1"] { color: #ff8c00; font-weight: bold; font-size: 12px; }
QSlider::groove:horizontal { height: 4px; background: #33363d; border-radius: 2px; }
QSlider::handle:horizontal { width: 18px; height: 18px; background: #ff8c00;
  border-radius: 9px; margin: -7px 0; }
QComboBox, QPushButton { background: #22252b; border: 1px solid #3a3e45;
  border-radius: 6px; padding: 7px; }
QLabel[val="1"] { color: #ffb14e; font-weight: bold; font-size: 15px; }
""",
"C": """
QWidget { font-size: 14px; }
QLabel[sec="1"] { font-weight: bold; font-size: 13px; }
QSlider::groove:horizontal { height: 6px; background: #555; border-radius: 3px; }
QSlider::handle:horizontal { width: 20px; height: 20px; background: #2ea043;
  border-radius: 10px; margin: -7px 0; }
QLabel[val="1"] { font-weight: bold; font-size: 15px; }
 QPushButton { padding: 8px; }
QComboBox { padding: 6px; }
""",
}

app = QApplication([])
w = QWidget()
w.setWindowTitle(f"SONY style {VAR}")
w.resize(520, 640)
v = QVBoxLayout(w)
v.addWidget(QLabel("SONY  •  SRG-X400  •  IMAGE"))
for sec, rows in [("EXPOSURE", [("Tryb", "manual"), ("Iris", "20  F3.1"),
                                  ("Gain", "2  +3dB"), ("Shutter", "17  1/30"),
                                  ("Komp.", "7  ±0dB")]),
                   ("WHITE BALANCE", [("Tryb", "auto"), ("B gain", "158"),
                                     ("R gain", "206"), ("Offset", "7")])]:
    g = QGroupBox(sec)
    f = QFormLayout(g)
    for label, val in rows:
        if "Tryb" in label:
            cb = QComboBox()
            cb.addItems([val, "auto", "manual"])
            f.addRow(label + ":", cb)
        else:
            row = QHBoxLayout()
            sl = QSlider(Qt.Horizontal)
            sl.setRange(0, 100)
            sl.setValue(60)
            lb = QLabel(val)
            lb.setProperty("val", "1")
            lb.setMinimumWidth(90)
            row.addWidget(sl, 1)
            row.addWidget(lb)
            f.addRow(label + ":", row)
    v.addWidget(g)
row = QHBoxLayout()
v.addLayout(row)
for t in ("Zastosuj", "OnePush", "Odczytaj"):
    row.addWidget(QPushButton(t))
v.addStretch(1)
w.setStyleSheet(QSS[VAR])
w.show()
app.processEvents()
import time
time.sleep(1)
app.primaryScreen().grabWindow(w.winId()).save(
    f"C:/Users/Mateusz/AppData/Local/Temp/rmip_style{VAR}.png")
print("style", VAR, flush=True)
sys.exit(0)

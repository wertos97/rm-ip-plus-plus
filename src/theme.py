"""Styl Alpha 7: czen, amber, nowa czcionka, biale ikony."""
from __future__ import annotations

from PySide6.QtGui import QFont, QFontDatabase

ACCENT = "#ff9e2c"
ACCENT_DIM = "#b86a12"
BG = "#0b0c0e"
PANEL = "#141619"
FIELD = "#1d2024"
LINE = "#2b2f35"
TEXT = "#f2f2f2"
DIM = "#9aa0a6"

QSS = f"""
QWidget {{ background: {BG}; color: {TEXT}; }}
QMainWindow, QDialog {{ background: {BG}; }}
QGroupBox {{ border: 1px solid {LINE}; border-radius: 6px; margin-top: 16px;
  font-weight: bold; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px;
  color: {ACCENT}; letter-spacing: 2px; }}
QLabel {{ background: transparent; }}
QLabel:disabled {{ color: #5a5e63; }}
QPushButton, QToolButton {{ background: {FIELD}; border: 1px solid {LINE};
  border-radius: 5px; padding: 7px 10px; color: {TEXT}; }}
QPushButton:hover, QToolButton:hover {{ border-color: {ACCENT}; }}
QPushButton:pressed, QToolButton:pressed {{ background: #2a2e33; }}
QPushButton:checked {{ background: #3a2c14; border-color: {ACCENT}; color: {ACCENT}; }}
QPushButton:disabled, QToolButton:disabled {{ color: #5a5e63; }}
QComboBox {{ background: {FIELD}; border: 1px solid {LINE}; border-radius: 4px;
  padding: 6px; }}
QComboBox QAbstractItemView {{ background: {FIELD}; selection-background-color: #3a2c14; }}
QSpinBox, QLineEdit {{ background: {FIELD}; border: 1px solid {LINE};
  border-radius: 4px; padding: 6px; selection-background-color: {ACCENT_DIM}; }}
QSlider::groove:horizontal {{ height: 3px; background: {LINE}; }}
QSlider::handle:horizontal {{ width: 15px; height: 15px; background: {ACCENT};
  border-radius: 7px; margin: -6px 0; }}
QSlider::groove:vertical {{ width: 3px; background: {LINE}; }}
QSlider::handle:vertical {{ width: 15px; height: 15px; background: {ACCENT};
  border-radius: 7px; margin: 0 -6px; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 15px; height: 15px; }}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{ background: {ACCENT}; }}
QTabWidget::pane {{ border: 1px solid {LINE}; border-radius: 4px; }}
QTabBar::tab {{ background: {PANEL}; border: 1px solid {LINE}; padding: 7px 16px;
  border-top-left-radius: 5px; border-top-right-radius: 5px; }}
QTabBar::tab:selected {{ color: {ACCENT}; border-color: {ACCENT}; }}
QTableWidget {{ background: {PANEL}; gridline-color: {LINE}; alternate-background-color: #101215; }}
QTableWidget::item:selected {{ background-color: #3a2c14; color: white; }}
QTableWidget::item:selected:!active {{ background-color: #2a2419; color: white; }}
QHeaderView::section {{ background: {FIELD}; border: none; padding: 6px; font-weight: bold; }}
QProgressBar {{ background: {FIELD}; border: 1px solid {LINE}; border-radius: 4px;
  text-align: center; }}
QProgressBar::chunk {{ background: {ACCENT}; }}
QPlainTextEdit {{ background: {PANEL}; border: 1px solid {LINE}; border-radius: 4px; }}
QLabel[val="1"] {{ color: #ff9e2c; font-weight: bold; }}
QMenu {{ background: {FIELD}; border: 1px solid {LINE}; }}
QMenu::item:selected {{ background: #3a2c14; }}
QToolTip {{ background: #22252a; color: {TEXT}; border: 1px solid {LINE}; }}
QSplitter::handle {{ background: {LINE}; }}
QStatusBar {{ color: {DIM}; }}
QScrollBar:vertical {{ background: {BG}; width: 12px; }}
QScrollBar::handle:vertical {{ background: #33373d; border-radius: 6px; min-height: 30px; }}
"""


def base_font() -> QFont:
    # techniczna, waska - jak w menu aparatow; fallback systemowy
    for fam in ("Bahnschrift", "Segoe UI Variable Text", "Segoe UI"):
        if fam in QFontDatabase.families():
            f = QFont(fam)
            f.setPointSize(10)
            return f
    return QFont()


def apply_theme(app) -> None:
    app.setFont(base_font())
    app.setStyleSheet(QSS)

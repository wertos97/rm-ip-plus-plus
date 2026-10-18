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
  border-radius: 5px; padding: 7px 10px; color: {TEXT}; outline: none; }}
QPushButton:hover, QToolButton:hover {{ border-color: {ACCENT}; }}
QPushButton:pressed, QToolButton:pressed {{ background: #2a2e33; }}
QPushButton:checked {{ background: #3a2c14; border-color: {ACCENT}; color: {ACCENT}; }}
QPushButton:disabled, QToolButton:disabled {{ color: #5a5e63; }}
QComboBox {{ background: {FIELD}; border: 1px solid {LINE}; border-radius: 4px;
  padding: 6px; }}
QComboBox QAbstractItemView {{ background: {FIELD}; selection-background-color: #3a2c14;
  border: 1px solid {LINE}; padding: 4px; outline: none; }}
QComboBox QAbstractItemView::item {{ padding: 6px 10px; border-radius: 4px; }}
QComboBox QAbstractItemView::item:selected {{ background: #3a2c14; color: #ffd9a0; }}
QSpinBox, QLineEdit {{ background: {FIELD}; border: 1px solid {LINE};
  border-radius: 4px; padding: 6px; selection-background-color: {ACCENT_DIM}; outline: none; }}
QSlider {{ outline: none; }}
QSlider::groove:horizontal {{ height: 3px; background: {LINE}; }}
QSlider::handle:horizontal {{ width: 15px; height: 15px; background: {ACCENT};
  border-radius: 7px; margin: -6px 0; }}
QSlider::groove:vertical {{ width: 3px; background: {LINE}; }}
QSlider::handle:vertical {{ width: 15px; height: 15px; background: {ACCENT};
  border-radius: 7px; margin: 0 -6px; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 4px;
  border: 2px solid #4a4f56; background: {FIELD}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
QRadioButton::indicator {{ width: 18px; height: 18px; border: none;
  background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5,
    stop:0 rgba(0,0,0,0), stop:0.6 rgba(0,0,0,0), stop:0.66 #4a4f56,
    stop:0.84 #4a4f56, stop:0.88 rgba(0,0,0,0), stop:1 rgba(0,0,0,0)); }}
QRadioButton::indicator:checked {{ border: none;
  background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5,
    stop:0 {ACCENT}, stop:0.42 {ACCENT}, stop:0.5 {BG}, stop:0.74 {BG},
    stop:0.82 {ACCENT}, stop:0.9 {ACCENT}, stop:0.94 rgba(0,0,0,0),
    stop:1 rgba(0,0,0,0)); }}
QTabWidget::pane {{ border: 1px solid {LINE}; border-radius: 4px; }}
QTabBar::tab {{ background: {PANEL}; border: 1px solid {LINE}; padding: 7px 16px;
  border-top-left-radius: 5px; border-top-right-radius: 5px; outline: none; }}
QTabBar::tab:hover:!selected {{ color: {ACCENT}; border-color: {ACCENT_DIM}; }}
QTabBar::tab:selected {{ color: {ACCENT}; border-color: {ACCENT}; }}
QTableWidget {{ background: {PANEL}; gridline-color: {LINE}; alternate-background-color: #101215;
  border: 1px solid {LINE}; border-radius: 4px; outline: none; }}
QTableCornerButton::section {{ background: {FIELD}; border: none; }}
QTableWidget::item:selected {{ background-color: #41331b; color: #ffd9a0; }}
QTableWidget::item:selected:!active {{ background-color: #2f2717; color: #ffd9a0; }}
QHeaderView::section {{ background: {FIELD}; border: none; padding: 6px; font-weight: bold; }}
QProgressBar {{ background: {FIELD}; border: 1px solid {LINE}; border-radius: 4px;
  text-align: center; }}
QProgressBar::chunk {{ background: {ACCENT}; }}
QPlainTextEdit {{ background: {PANEL}; border: 1px solid {LINE}; border-radius: 4px;
  font-family: Consolas, monospace; font-size: 11px; padding: 6px 8px; outline: none; }}
QLabel[val="1"] {{ color: #ff9e2c; font-weight: bold; }}
QLabel[sec="1"] {{ color: {DIM}; font-weight: bold; letter-spacing: 2px;
  font-size: 11px; padding-top: 2px; }}
QPushButton[kind="primary"] {{ background: #3a2c14; border: 1px solid {ACCENT};
  color: #ffc06a; font-weight: bold; }}
QPushButton[kind="primary"]:hover {{ background: #4a3618; border-color: #ffb14e; }}
QPushButton[kind="primary"]:pressed {{ background: #2a2010; }}
QWidget#adv {{ background: #101216; border: 1px solid {LINE}; border-radius: 6px; }}
QSplitter::handle {{ background: transparent; }}
QSplitter::handle:hover {{ background: {ACCENT_DIM}; }}
QMenu {{ background: {FIELD}; border: 1px solid {LINE}; padding: 6px; }}
QMenu::item {{ padding: 6px 22px; border-radius: 4px; }}
QMenu::item:selected {{ background: #3a2c14; color: #ffd9a0; }}
QToolTip {{ background: #22252a; color: {TEXT}; border: 1px solid {LINE}; }}
QStatusBar {{ color: {DIM}; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #31353b; border-radius: 5px; min-height: 30px; }}
QScrollBar::handle:horizontal {{ background: #31353b; border-radius: 5px; min-width: 30px; }}
QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{ background: {ACCENT_DIM}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; background: none; border: none; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
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

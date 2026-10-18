"""Inspektor UI: zrzuty POJEDYNCZYCH elementow (zbliżenia) do dopracowania detali.

Uzycie:  python tools/inspect_ui.py <katalog> [ip]

Zrzuty per-widget (QWidget.grab), wiec nie zalezy od kompozytora ekranu.
Nie rusza kamery poza odczytami status/imaging/presetow (zero komend ruchu).
"""
import os
import sys
import time
import atexit

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "ui_elements")
IP = sys.argv[2] if len(sys.argv) > 2 else "192.168.4.101"
os.makedirs(OUT, exist_ok=True)

os.environ.pop("QT_QPA_PLATFORM", None)
from PySide6.QtWidgets import QApplication, QGroupBox  # noqa: E402
from PySide6.QtCore import QCoreApplication, QEvent  # noqa: E402

import net_manager as nm  # noqa: E402
from ui_main import MainWindow  # noqa: E402
from theme import apply_theme  # noqa: E402

atexit.unregister(nm.cleanup_all)

app = QApplication(sys.argv[:1])
apply_theme(app)

w = MainWindow()
w.showMaximized()

_i = [0]


def pump(sec: float) -> None:
    t0 = time.time()
    while time.time() - t0 < sec:
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        time.sleep(0.02)


def snap(name: str, widget) -> None:
    if widget is None:
        print(f"[skip] {name} (None)", flush=True)
        return
    if not widget.isVisible():
        print(f"[warn] {name} niewidoczny - i tak zrzut", flush=True)
    _i[0] += 1
    p = os.path.join(OUT, f"{_i[0]:02d}_{name}.png")
    try:
        widget.grab().save(p)
        print(f"[shot] {os.path.basename(p)} {widget.width()}x{widget.height()}", flush=True)
    except Exception as e:
        print(f"[err] {name}: {e}", flush=True)


def find_tab(ip: str) -> int:
    for i in range(w.ctrl_tabs.count()):
        tw = w.ctrl_tabs.widget(i)
        if (tw.property("ip") if tw else None) == ip or w.ctrl_tabs.tabText(i) == ip:
            return i
    return -1


# 1) czekamy na skan startowy
t0 = time.time()
while time.time() - t0 < 45:
    app.processEvents()
    if w.worker is None or not w.worker.isRunning():
        break
    time.sleep(0.05)
pump(1.0)

# 2) karta kamery
if find_tab(IP) < 0:
    w.add_ctrl_tab(IP)
w.ctrl_tabs.setCurrentIndex(find_tab(IP))
pump(5.0)
tab = w.ctrl_tabs.currentWidget()

# ---------- chrom okna / lewy panel ----------
snap("btn_skanuj", w.btn_fast)
snap("lbl_skan_status", w.lbl)
snap("btn_zaawansowane_zamkniety", w.btn_adv)
snap("tabela_urzadzen", w.cam_table)
w.cam_table.selectRow(0)
pump(0.3)
snap("tabela_urzadzen_zaznaczona", w.cam_table)
snap("btn_dodaj_ip", w.btn_addip)
snap("btn_steruj_wszystkimi", w.btn_all)
snap("btn_steruj_zaznaczona", w.btn_add)
snap("btn_otworz_edge", w.btn_web)
snap("pasek_zakladek_kamer", w.ctrl_tabs.tabBar())
snap("log", w.log)

# panel Zaawansowane (otwarty z danymi)
try:
    w.btn_adv.click()
    pump(1.2)
    snap("panel_zaawansowane", w.adv)
    snap("btn_zaawansowane_otwarty", w.btn_adv)
    w.btn_adv.click()
    pump(0.4)
except Exception as e:
    print(f"[warn] zaawansowane: {e}", flush=True)

# ---------- zakladka Sterowanie ----------
snap("pasek_zakladek_wew", tab.pages.tabBar())

groups = tab.pages.widget(0).findChildren(QGroupBox)
for g in groups:
    snap("grupa_" + g.title().replace(" ", "_").replace("/", "-"), g)

snap("radio_jazda", tab.rb_drive)
snap("radio_krok", tab.rb_step)
snap("slider_szybkosc", tab.sl_speed)
snap("spin_wielkosc_kroku", tab.sp_step)
snap("slider_zoom_speed", tab.sl_zspeed)
snap("combo_tryb_focus", tab.cb_focus)
snap("btn_one_push_af", tab.btn_af1)
snap("combo_tryb_ekspozycji", tab.cb_exp)
snap("btn_zastosuj_ekspozycje", tab.btn_exp)
snap("combo_tryb_wb", tab.cb_wb)
snap("btn_zastosuj_wb", tab.btn_wb)
snap("btn_onepush_wb", tab.btn_wb1)
snap("btn_odczytaj_z_kamery", tab.btn_reload)

# popup combo (lista trybow)
try:
    tab.cb_exp.showPopup()
    pump(0.6)
    view = tab.cb_exp.view()
    snap("popup_tryb_ekspozycji", view.window() if view else None)
    tab.cb_exp.hidePopup()
    pump(0.2)
except Exception as e:
    print(f"[warn] popup: {e}", flush=True)

# pasek dolny: status + szybkie kadry
snap("pasek_status_kamery", tab.status)
if getattr(tab, "quick_btns", None):
    snap("szybki_kadr_1", tab.quick_btns[0])
    snap("szybki_kadr_2", tab.quick_btns[1])

# ---------- Presety ----------
tab.pages.setCurrentIndex(1)
pump(4.5)
pp = tab.preset_panel
snap("presety_panel", pp)
snap("presety_spin_szybkosc", pp.sp_speed)
snap("presety_btn_prev", pp.btn_prev)
snap("presety_btn_next", pp.btn_next)
snap("presety_lb_strona", pp.lb_page)

card1 = pp.grid.itemAtPosition(0, 0).widget()
card2 = pp.grid.itemAtPosition(0, 1).widget()
card3 = pp.grid.itemAtPosition(0, 2).widget()
snap("karta_preset_1_thumby", card1)
snap("karta_preset_3_pusty", card3)
if card2 is not None:
    card2.hover = True
    card2.update()
    pump(0.2)
    snap("karta_preset_2_hover", card2)
    card2.hover = False
    card2.update()

# ---------- Kadry PTZ ----------
tab.pages.setCurrentIndex(2)
pump(2.0)
fp = tab.frame_panel
snap("kadry_panel", fp)
fc1 = fp.grid.itemAtPosition(0, 0).widget()
fc3 = fp.grid.itemAtPosition(0, 2).widget()
snap("karta_kadr_1", fc1)
snap("karta_kadr_3_pusty", fc3)

tab.pages.setCurrentIndex(0)
pump(0.5)

print("DONE", flush=True)

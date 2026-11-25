import cam_control
import creds
import human
from demo_api import DemoCameraAPI


def test_relative_values_and_human_units():
    assert cam_control.rel16(-1) == "ffff"
    assert cam_control.rel20(-1) == "fffff"
    assert cam_control.AM7_STEP_SCALE == 19.53125
    assert human.pan_deg20("2ab98") == 175.0
    assert human.pan_deg20("d5468") == -175.0
    assert human.tilt_deg20("33450") == 210.0
    assert abs(human.tilt_deg20("f8bd0") + 29.744) < 1e-6
    assert human.zoom_x_max("4000", 25.0) == 25.0
    assert human.zoom_x("4000") == 20.0
    assert human.zoom_x("2015") == 4.0
    assert human.SHUTTER_50P[31] == "1/3500"
    assert human.SHUTTER_50P[30] == "1/2500"
    assert human.SHUTTER_50P[29] == "1/1750"
    assert human.SHUTTER_50P[28] == "1/1250"
    assert human.gain_db_am7(0) == "-9dB"
    assert human.gain_db_am7(9) == "0dB"
    assert human.gain_db_am7(45) == "36dB"
    assert human.ae_level_ev(12) == "0 EV"
    assert human.ae_level_ev(24) == "+3 EV"
    assert human.ae_level_ev(6) == "-1.5 EV"
    assert human.SHUTTER_50P_AM7[5] == "64F"
    assert human.SHUTTER_50P_AM7[15] == "1/50"
    assert human.SHUTTER_50P_AM7[25] == "1/8000"
    assert human.am7_iris_to_cam(0) == 27366
    assert human.am7_iris_to_cam(1025) == 32000
    assert human.am7_iris_to_cam(1) == 30976
    assert human.am7_iris_from_cam(27366) == 0
    assert human.am7_iris_from_cam(32000) == 1025
    assert human.am7_iris_from_cam(30975) == 1
    assert human.am7_iris_label(0) == "CLOSE"
    assert human.am7_iris_label(1) == "F11"
    assert human.am7_iris_label(1025) == "F2.8"


def test_am7_model_detection_reads_speed_step(monkeypatch):
    api = cam_control.CameraAPI("192.0.2.10", "admin", "Admin123")
    replies = {
        "system": (True, {"ModelName": "BRC-AM7"}),
        "ptzf": (True, {"PanTiltSpeedStep": "extended"}),
    }
    monkeypatch.setattr(api, "inquiry", lambda what, timeout=8: replies[what])
    assert api.family == "am7"
    assert api._speedstep == "extended"


def test_srg_model_detection_does_not_enable_am7_commands(monkeypatch):
    api = cam_control.CameraAPI("192.0.2.10", "admin", "admin123")
    monkeypatch.setattr(api, "inquiry", lambda what, timeout=8: (True, {"ModelName": "SRG-X400"}))
    assert api.family == "srg"
    assert api._speedstep is None


def test_srg_camera_commands():
    api = cam_control.CameraAPI("192.0.2.10", "admin", "admin")
    sent = []
    api.cmd = lambda cgi, query, **kwargs: sent.append((cgi, query)) or (True, "")
    api._family = "srg"

    api.move("up-left", 10)
    assert sent[-1] == ("ptzf.cgi", "Move=up-left,10")
    api.zoom_move("tele", 3)
    assert sent[-1] == ("ptzf.cgi", "Move=tele,3")
    api.focus_move("near")
    assert sent[-1] == ("ptzf.cgi", "Move=near,4")
    api.stop("pantilt")
    assert sent[-1] == ("ptzf.cgi", "Move=stop,pantilt")
    api.slow_mode(True)
    assert sent[-1] == ("camera.cgi", "SlowPanTiltMode=on")
    api.set_focus_mode("manual")
    assert sent[-1] == ("camera.cgi", "FocusMode=manual")
    api.preset_recall(5, 10)
    assert sent[-1] == ("presetposition.cgi", "PresetCall=5,10")
    api.wb_onepush()
    assert sent[-1] == ("imaging.cgi", "WhiteBalanceOnePushTrg=on")


def test_am7_camera_commands_and_stop_fallback():
    api = cam_control.CameraAPI("192.0.2.10", "admin", "admin")
    sent = []
    api.cmd = lambda cgi, query, **kwargs: sent.append((cgi, query)) or (True, "")
    api._family = "am7"
    api._speedstep = "extended"

    api.move("up", 24)
    assert sent[-1] == ("ptzf.cgi", "PanTiltMove=up,127,127")
    api._speedstep = "normal"
    api.move("up", 24)
    assert sent[-1] == ("ptzf.cgi", "PanTiltMove=up,24,24")
    api._speedstep = "extended"
    api.zoom_move("tele", 8)
    assert sent[-1] == ("ptzf.cgi", "ZoomMove=tele,32766")
    api.relative_pt("00320", "ffce0", 5)
    assert sent[-1] == ("ptzf.cgi", "RelativePanTilt=00320,ffce0,26")
    api.preset_recall(5, 10)
    assert sent[-1] == ("presetposition.cgi", "PresetCall=5")
    api.wb_onepush()
    assert sent[-1] == ("cameraoperation.cgi", "WhiteBalanceWBSet=press")
    api.wb_onepush_release()
    assert sent[-1] == ("cameraoperation.cgi", "WhiteBalanceWBSet=release")

    calls = []

    def reject_first(cgi, query, **kwargs):
        calls.append(query)
        return len(calls) > 1, "HTTP 400"

    api.cmd = reject_first
    api.stop("pantilt")
    assert calls == ["PanTiltMove=stop", "PanTiltMove=stop,0,0"]


def test_am7_exposure_and_white_balance():
    api = cam_control.CameraAPI("192.0.2.10", "admin", "admin")
    sent = []
    api.cmd = lambda cgi, query, **kwargs: sent.append((cgi, query)) or (True, "")
    api._family = "am7"

    sent.clear()
    api.set_exposure_am7("manual", 27366, 45, 15, 12)
    assert sent[0][1] == "ExposureAutoShutterEnable=off&ExposureAutoIris=off&ExposureAGCEnable=off"
    assert sent[1][1] == "ExposureCompensation=12&ExposureIris=27366&ExposureGain=45&ExposureExposureTime=15"

    sent.clear()
    api.set_exposure_am7("manual", 28000, 45, 15, 12)
    assert "ExposureIris=30975" in sent[1][1]

    sent.clear()
    api.set_exposure_am7("auto", 32000, 9, 5, 24)
    assert sent[0][1] == "ExposureAutoShutterEnable=on&ExposureAutoIris=on&ExposureAGCEnable=on"
    assert sent[1][1] == "ExposureCompensation=24"

    sent.clear()
    api.set_wb_am7("memory_a", -10, 20, 5)
    assert sent[-1][1] == "WhiteBalanceMode=memory_a&WhiteBalanceCbGain=-10&WhiteBalanceCrGain=20"
    sent.clear()
    api.set_wb_am7("atw", 0, 0, -7)
    assert sent[-1][1] == "WhiteBalanceMode=atw&WhiteBalanceOffsetColorTemp=-7"


def test_am7_manual_exposure_rejects_iso_mode():
    api = cam_control.CameraAPI("192.0.2.10", "admin", "Admin123")
    sent = []
    api.cmd = lambda cgi, query, **kwargs: sent.append((cgi, query)) or (True, "")
    ok, message = api.set_exposure_am7("manual", 32000, 9, 15, 12, gain_mode="iso")
    assert not ok
    assert "ISO mode" in message
    assert not sent


def test_preset_names_reject_query_delimiters_and_long_values():
    api = cam_control.CameraAPI("192.0.2.10", "admin", "admin")
    sent = []
    api.cmd = lambda cgi, query, **kwargs: sent.append((cgi, query)) or (True, "")
    ok, message = api.preset_set(1, "Bad,name")
    assert not ok and "commas" in message
    ok, message = api.preset_rename(1, "x" * 33)
    assert not ok and "32" in message
    assert not sent
    assert api.preset_set(1, "Wide shot")[0]
    assert sent[-1] == ("presetposition.cgi", "PresetSet=1,Wide shot,on")


def test_credentials_resolution_order():
    config = {"user": "admin", "password": "admin"}
    assert creds.candidates(config, "192.168.1.101") == [
        ("admin", "admin123"),
        ("admin", "Admin123"),
        ("admin", "admin"),
    ]
    creds.save_credentials(config, "192.168.1.101", "root", "secret")
    assert creds.candidates(config, "192.168.1.101")[0] == ("root", "secret")
    assert creds.saved_credentials(config, "192.168.1.101") == ("root", "secret")
    custom = {"user": "operator", "password": "pw"}
    assert ("operator", "pw") in creds.candidates(custom, "10.0.0.5")
    assert creds.candidates({}, "10.0.0.6")[0] == ("admin", "admin123")


def test_demo_camera_state_and_presets():
    demo = DemoCameraAPI()
    assert demo.family == "srg"
    ok, status = demo.status()
    assert ok and "," in status["AbsolutePTZF"]
    start = status["AbsolutePTZF"]
    demo.move("right", 10)
    demo.zoom_move("tele", 6)
    assert demo.status()[1]["AbsolutePTZF"] != start
    assert demo.preset_set(3, "Test")[0]
    assert demo.preset_list()[1] == {3: "Test"}
    demo.home()
    assert demo.preset_recall(3)[0]
    assert demo.status()[1]["AbsolutePTZF"] != "0000,0000,0000,8000"
    assert not demo.preset_recall(9)[0]
    assert demo.imaging()[1]["ExposureMode"] == "auto"
    assert demo.set_imaging(ExposureMode="manual")[0]
    assert demo.imaging()[1]["ExposureMode"] == "manual"
    assert demo.set_focus_mode("manual")[0]
    assert demo.still() is None


def test_invalid_relative_value_is_rejected_by_demo():
    demo = DemoCameraAPI()
    ok, message = demo.relative_pt("not-hex", "0000")
    assert not ok
    assert "bad relative value" in message

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from cam_control import CameraAPI


class AM7Server:
    def __init__(self):
        self.requests = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                owner.requests.append(self.path)
                parsed = urlparse(self.path)
                query = parse_qs(parsed.query)
                if parsed.path == "/command/inquiry.cgi":
                    inquiry = query.get("inq", [""])[0]
                    bodies = {
                        "system": "ModelName=BRC-AM7\n",
                        "ptzf": (
                            "AbsolutePTZF=2ab98,10394,2000,2f1a\n"
                            "PtzfStatus=idle\n"
                            "PanTiltSpeedStep=extended\n"
                            "FocusMode=manual\n"
                        ),
                        "imaging": (
                            "ExposureAutoShutterEnable=off\n"
                            "ExposureAutoIris=on\n"
                            "ExposureAGCEnable=on\n"
                            "ExposureIris=32000\n"
                            "ExposureGain=9\n"
                            "ExposureExposureTime=15\n"
                            "ExposureCompensation=12\n"
                            "ExposureGainRange=6,45\n"
                            "ExposureExposureTimeRange=5,25\n"
                            "ExposureISOGainMode=gain\n"
                            "WhiteBalanceMode=atw\n"
                            "WhiteBalanceCbGain=0\n"
                            "WhiteBalanceCrGain=0\n"
                            "WhiteBalanceOffsetColorTemp=-7\n"
                        ),
                        "presetposition": "PresetName=1,Wide,2,Close\n",
                    }
                    body = bodies.get(inquiry, "")
                    status = 200
                elif parsed.path.startswith("/command/"):
                    body = "OK"
                    status = 200
                else:
                    body = "Not found"
                    status = 404
                data = body.encode()
                self.send_response(status)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def port(self):
        return self.server.server_address[1]

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)


def test_am7_http_commands_match_documented_endpoints():
    server = AM7Server()
    try:
        api = CameraAPI("127.0.0.1", "admin", "Admin123", http_port=server.port)
        assert api.family == "am7"
        assert api._speedstep == "extended"
        assert any("inq=system" in path for path in server.requests)

        assert api.move("up", 24)[0]
        assert server.requests[-1] == "/command/ptzf.cgi?PanTiltMove=up,127,127"

        assert api.focus_step("near", step=0x0400)[0]
        assert server.requests[-1] == "/command/ptzf.cgi?AbsoluteFocus=331a"

        assert api.preset_list() == (True, {1: "Wide", 2: "Close"})
        assert api.preset_recall(2)[0]
        assert server.requests[-1] == "/command/presetposition.cgi?PresetCall=2"

        assert api.wb_onepush()[0]
        assert server.requests[-1] == "/command/cameraoperation.cgi?WhiteBalanceWBSet=press"
        assert api.wb_onepush_release()[0]
        assert server.requests[-1] == "/command/cameraoperation.cgi?WhiteBalanceWBSet=release"

        assert api.set_exposure_am7("manual", 32000, 9, 15, 12, gain_mode="gain")[0]
        assert server.requests[-2] == (
            "/command/imaging.cgi?ExposureAutoShutterEnable=off&ExposureAutoIris=off&ExposureAGCEnable=off"
        )
        assert server.requests[-1] == (
            "/command/imaging.cgi?ExposureCompensation=12&ExposureIris=32000&ExposureGain=9&ExposureExposureTime=15"
        )

        count = len(server.requests)
        ok, message = api.set_exposure_am7("manual", 32000, 9, 15, 12, gain_mode="iso")
        assert not ok and "ISO mode" in message
        assert len(server.requests) == count
    finally:
        server.close()

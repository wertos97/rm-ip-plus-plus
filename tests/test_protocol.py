import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

import sony_csv
import sony_udp
from sony_client import SonyCamera

NETWORK_REPLY = (
    b"\x02INFO:network\xffMODEL:SRG-X400\xffSOFTVERSION:1.02\xff"
    b"MAC:00-11-22-33-44-55\xffIPADR:192.168.1.101\xffMASK:255.255.255.0\xff"
    b"GATEWAY:192.168.4.1\xffNAME:CAM2\xff\x03"
)


def test_udp_discovery_frame_and_reply():
    assert sony_udp.build_request() == b"\x02ENQ:network\xff\x03"
    reply = sony_udp.parse_reply(NETWORK_REPLY, "192.168.1.101")
    assert reply is not None
    assert reply["model"] == "SRG-X400"
    assert reply["name"] == "CAM2"
    assert reply["mac_norm"] == "00:11:22:33:44:55"
    assert reply["softversion"] == "1.02"
    assert sony_udp.parse_reply(b"<html>RouterOS</html>", "192.168.88.1") is None


def test_udp_network_set_validation_and_ack():
    message = sony_udp.build_set_network("00:11:22:33:44:55", "192.168.1.101", "255.255.255.0", "192.168.4.1", "CAM2")
    assert message == (
        b"\x02MAC:00-11-22-33-44-55\xffIPADR:192.168.1.101\xff"
        b"MASK:255.255.255.0\xffGATEWAY:192.168.4.1\xffNAME:CAM2\xff\x03"
    )
    with pytest.raises(ValueError):
        sony_udp.build_set_network("bad", "192.168.1.101", "255.255.255.0", "", "CAM2")
    with pytest.raises(ValueError):
        sony_udp.build_set_network("00-11-22-33-44-55", "999.1.1.1", "255.255.255.0", "", "CAM2")

    ack = sony_udp.parse_ack_nak(b'\x02ACK:"00-11-22-33-44-55"\xff\x03')
    assert ack is not None and ack["kind"] == "ACK"
    nak = sony_udp.parse_ack_nak(b'\x02NAK:"00-11-22-33-44-55"\xff\x03')
    assert nak is not None and nak["kind"] == "NAK"
    assert sony_udp.parse_ack_nak(NETWORK_REPLY) is None


def test_camtable_frames_and_entries():
    assert sony_udp.CAMTABLE_SLOTS == 112
    assert sony_udp.build_camtable_query(1) == b"\x02ENQ:camtable1\xff\x03"
    assert sony_udp.build_camtable_query(4) == b"\x02ENQ:camtable4\xff\x03"
    reply = (
        b"\x02MAC:02-00-C0-A8-00-01\xffINFO:camtable1\xff"
        b"CAM001:00-11-22-33-44-55:192.168.1.101:CAM2\xffCAM002:::\xff\x03"
    )
    table = sony_udp.parse_camtable_reply(reply, "192.168.4.50")
    assert table is not None
    assert table["page"] == 1
    assert table["panel_mac"] == "02-00-C0-A8-00-01"
    assert table["entries"] == [
        {"slot": 1, "mac": "00-11-22-33-44-55", "ip": "192.168.1.101", "name": "CAM2"},
        {"slot": 2, "mac": "", "ip": "", "name": ""},
    ]
    assert sony_udp.parse_camtable_reply(NETWORK_REPLY) is None


def test_csv_slot_mapping_and_round_trip():
    assert sony_csv.group_camera_to_slot(1, 1) == 1
    assert sony_csv.group_camera_to_slot(7, 16) == 112
    assert sony_csv.slot_to_group_camera(17) == (2, 1)

    slots = {1: {"name": "CAM2", "mac": "00-11-22-33-44-55", "ip": "192.168.1.101"}}
    text = sony_csv.table_csv_text(slots)
    lines = text.strip().splitlines()
    assert lines[0] == sony_csv.TABLE_HEADER
    assert lines[1] == "Group1-1,CAM2,00-11-22-33-44-55,192.168.1.101,255.255.255.0"
    assert lines[2] == "Group1-2,,,,"
    assert len(lines) == 113
    parsed = sony_csv.parse_table_csv(text)
    assert not parsed["warnings"]
    assert len(parsed["rows"]) == 112
    assert parsed["rows"][0]["slot"] == 1
    assert parsed["rows"][-1]["slot"] == 112

    bad = sony_csv.parse_table_csv("Group9-1,a,b,c,d\nGroup1-1,too,few\n")
    assert not bad["rows"]
    assert len(bad["warnings"]) == 2


def test_camera_csv_round_trip_and_warnings():
    devices = [
        {
            "name": "CAM2",
            "mac": "00-11-22-33-44-55",
            "ip": "192.168.1.101",
            "mask": "255.255.255.0",
            "gateway": "192.168.4.1",
            "version": "1.02",
        }
    ]
    text = sony_csv.camera_csv_text(devices)
    assert text.splitlines()[0] == sony_csv.CAMERA_HEADER
    parsed = sony_csv.parse_camera_csv(text)
    assert not parsed["warnings"]
    assert parsed["rows"][0]["gateway"] == "192.168.4.1"
    bad = sony_csv.parse_camera_csv("too,few\n")
    assert not bad["rows"]
    assert "instead of 6" in bad["warnings"][0]


@contextmanager
def fake_camera_server(body: bytes):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_http_client_reads_model_from_system_inquiry(monkeypatch):
    class Response:
        def __init__(self, text, status_code=200):
            self.text = text
            self.status_code = status_code

    def get(path, timeout=6):
        if "inq=network" in path:
            return Response('IpAddress="192.168.1.101"\nCameraName="CAM1"\n')
        if "inqjs=license" in path:
            return Response("", 404)
        if "inq=system" in path:
            return Response("ModelName=BRC-AM7\n")
        return Response("", 404)

    camera = SonyCamera("127.0.0.1")
    monkeypatch.setattr(camera, "_get", get)
    ok, network = camera.get_network(timeout=1)
    assert ok
    assert network["ModelName"] == "BRC-AM7"


def test_http_client_accepts_sony_fields_and_rejects_router_page():
    with fake_camera_server(
        b'IpAddress="192.168.1.101"\nSubnetmask="255.255.255.0"\nCameraName="CAM2"\nModelName="SRG-X400"\n'
    ) as port:
        ok, network = SonyCamera("127.0.0.1", http_port=port).get_network(timeout=2)
        assert ok
        assert network["CameraName"] == "CAM2"
        assert network["ModelName"] == "SRG-X400"

    with fake_camera_server(b'<html>var ip = "192.168.0.1";</html>') as port:
        ok, _ = SonyCamera("127.0.0.1", http_port=port).get_network(timeout=2)
        assert not ok

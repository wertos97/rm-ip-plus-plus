import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "src"))

import config_store as cs
c0 = cs.load()
assert "user" in c0
print("config_store OK")

import net_manager as nm
assert nm.STATE_FILE.endswith(".json")
assert nm.find_orphans() is not None
print("net_manager OK, admin=", nm.is_admin())

import diagnostics as d
assert isinstance(d.env_report(), str)
assert d.tcp_open("127.0.0.1", 52381) in (True, False)
print("diagnostics OK")

import discovery as disc
assert disc.LIKELY_DEFAULTS[0] == "192.168.0.100"
assert disc.tcp_open("127.0.0.1", 1) is False
merged = disc.merge_udp([], [{"ip": "10.0.0.9", "model": "SRG-X400", "name": "CAM9",
                              "mac": "00-11-22-33-44-55", "src_ip": "10.0.0.9"}])
assert merged and merged[0]["ip"] == "10.0.0.9" and merged[0]["http"] is False
assert "CAM9" in merged[0]["model"] and merged[0].get("note")
print("discovery OK")

import sony_udp as su
assert su.SONY_UDP_PORT == 52380
assert su.build_request() == b"\x02ENQ:network\xff\x03"
demo = (b"\x02INFO:network\xffMODEL:SRG-X400\xffSOFTVERSION:1.02\xff"
        b"MAC:F8-4E-17-DE-30-9F\xffIPADR:192.168.4.101\xffMASK:255.255.255.0\xff"
        b"GATEWAY:192.168.4.1\xffNAME:CAM2\xff\x03")
r = su.parse_reply(demo, "192.168.4.101")
assert r is not None
assert r["model"] == "SRG-X400" and r["name"] == "CAM2" and r["ip"] == "192.168.4.101"
assert r["mac_norm"] == "f8:4e:17:de:30:9f" and r["softversion"] == "1.02"
assert su.parse_reply(b"<html>RouterOS router configuration page</html>",
                      "192.168.88.1") is None
print("sony_udp OK")

# --- nowe: SET sieci (UDP WRITE), ACK/NAK, camtable ---
assert su.CAMTABLE_SLOTS == 112
assert su.normalize_mac("f8:4e:17:de:30:9f") == "F8-4E-17-DE-30-9F"
assert su.normalize_mac("f84e17de309f") == "F8-4E-17-DE-30-9F"
setmsg = su.build_set_network("F8-4E-17-DE-30-9F", "192.168.4.101",
                              "255.255.255.0", "192.168.4.1", "CAM2")
assert setmsg == (b"\x02MAC:F8-4E-17-DE-30-9F\xffIPADR:192.168.4.101\xff"
                  b"MASK:255.255.255.0\xffGATEWAY:192.168.4.1\xffNAME:CAM2\xff\x03"), setmsg
try:
    su.build_set_network("zle", "192.168.4.101", "255.255.255.0", "", "CAM2")
    raise AssertionError("zly MAC powinien rzucic ValueError")
except ValueError:
    pass
try:
    su.build_set_network("F8-4E-17-DE-30-9F", "999.1.1.1", "255.255.255.0", "", "CAM2")
    raise AssertionError("zle IP powinno rzucic ValueError")
except ValueError:
    pass
demo_w = (b"\x02INFO:network\xffMODEL:SRG-X400\xffWRITE:on\xffMAC:F8-4E-17-DE-30-9F\xff"
          b"IPADR:192.168.4.101\xffMASK:255.255.255.0\xffGATEWAY:192.168.4.1\xff"
          b"NAME:CAM2\xff\x03")
rw = su.parse_reply(demo_w, "192.168.4.101")
assert rw is not None and rw["writable"] == "on"
ack = su.parse_ack_nak(b'\x02ACK:"F8-4E-17-DE-30-9F"\xff\x03')
assert ack and ack["kind"] == "ACK" and ack["mac"] == "F8-4E-17-DE-30-9F"
nak = su.parse_ack_nak(b'\x02NAK:"F8-4E-17-DE-30-9F"\xff\x03')
assert nak and nak["kind"] == "NAK" and nak["mac"] == "F8-4E-17-DE-30-9F"
assert su.parse_ack_nak(demo) is None
assert su.build_camtable_query(1) == b"\x02ENQ:camtable1\xff\x03"
assert su.build_camtable_query(4) == b"\x02ENQ:camtable4\xff\x03"
demo_ct = (b"\x02MAC:02-00-C0-A8-00-01\xffINFO:camtable1\xff"
           b"CAM001:F8-4E-17-DE-30-9F:192.168.4.101:CAM2\xffCAM002:::\xff\x03")
ct = su.parse_camtable_reply(demo_ct, "192.168.4.50")
assert ct and ct["page"] == 1 and ct["panel_mac"] == "02-00-C0-A8-00-01"
assert len(ct["entries"]) == 2
assert ct["entries"][0] == {"slot": 1, "mac": "F8-4E-17-DE-30-9F",
                            "ip": "192.168.4.101", "name": "CAM2"}
assert ct["entries"][1]["slot"] == 2 and ct["entries"][1]["mac"] == ""
assert su.parse_camtable_reply(demo) is None
print("sony_udp SET/camtable OK")

import sony_csv as sc
assert sc.group_camera_to_slot(1, 1) == 1
assert sc.group_camera_to_slot(7, 16) == 112
assert sc.slot_to_group_camera(17) == (2, 1)
slots = {1: {"name": "CAM2", "mac": "F8-4E-17-DE-30-9F", "ip": "192.168.4.101"}}
txt = sc.table_csv_text(slots)
lines = txt.strip().splitlines()
assert lines[0] == sc.TABLE_HEADER
assert lines[1] == "Group1-1,CAM2,F8-4E-17-DE-30-9F,192.168.4.101,255.255.255.0"
assert lines[2] == "Group1-2,,,,"
assert len(lines) == 113
pt = sc.parse_table_csv(txt)
assert not pt["warnings"] and len(pt["rows"]) == 112
assert pt["rows"][0]["slot"] == 1 and pt["rows"][0]["mac"] == "F8-4E-17-DE-30-9F"
assert pt["rows"][-1]["slot"] == 112
bad = sc.parse_table_csv("Group9-1,a,b,c,d\nGroup1-1,too,few\n")
assert not bad["rows"] and len(bad["warnings"]) == 2
cam_txt = sc.camera_csv_text([{"name": "CAM2", "mac": "F8-4E-17-DE-30-9F",
                               "ip": "192.168.4.101", "mask": "255.255.255.0",
                               "gateway": "192.168.4.1", "version": "1.02"}])
lines = cam_txt.strip().splitlines()
assert lines[0] == sc.CAMERA_HEADER and len(lines) == 2
pc = sc.parse_camera_csv(cam_txt)
assert pc["rows"][0]["name"] == "CAM2" and pc["rows"][0]["gateway"] == "192.168.4.1"
print("sony_csv OK")

from sony_client import SonyCamera
c = SonyCamera("127.0.0.1")
assert c.web_url() == "http://127.0.0.1:80/"

# --- get_network: HTTP 200 z obcego serwera (router hotelowy / NAS) to NIE kamera ---
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

class _FakePage(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass
    def do_GET(self):
        b = self.server.body  # type: ignore[attr-defined]
        self.send_response(200)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

def _fake_http(body: bytes):
    srv = HTTPServer(("127.0.0.1", 0), _FakePage)
    srv.body = body
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]

# router hotelowy / NAS: HTML z przypadkowymi "k=v" -> musi odpadac
srv, port = _fake_http(b'<html>var ip = "192.168.0.1"; if (port == 443) { }</html>')
try:
    ok_r, net_r = SonyCamera("127.0.0.1", http_port=port).get_network(timeout=2)
    assert ok_r is False, f"router/NAS nie moze przejsc jako kamera: {net_r}"
finally:
    srv.shutdown()

# prawdziwa odpowiedz kamery (IpAddress/Subnetmask/CameraName) -> przechodzi
srv, port = _fake_http(b'IpAddress="192.168.4.101"\nSubnetmask="255.255.255.0"\nCameraName="CAM2"\n')
try:
    ok_c, net_c = SonyCamera("127.0.0.1", http_port=port).get_network(timeout=2)
    assert ok_c is True and net_c.get("CameraName") == "CAM2", net_c
finally:
    srv.shutdown()
print("sony_client OK")

import subnet_bridge as b
assert b.bridge_ip_for("10.5.5.5") == "10.5.5.200"
assert b.bridge_ip_for("192.168.0.200") == "192.168.0.201"  # unik kolizji
assert b.guess_homes([{"ip": "10.5.5.5"}]) == ["10.5.5"]
assert isinstance(b.arp_candidates(None), list)
assert isinstance(b.ssdp_search(timeout=0.5), list)
print("subnet_bridge OK")

assert nm.is_virtual_alias("Polaczenie sieciowe Bluetooth") is True
assert nm.is_virtual_alias("Siec komorkowa") is True
assert nm.is_virtual_alias("Ethernet") is False
assert nm.is_virtual_alias("Wi-Fi") is False
bi = nm.best_bridge_iface()
print("best_bridge_iface:", bi)
assert bi is None or isinstance(bi, str)
print("iface-auto OK")
print("ALL TESTS PASSED")

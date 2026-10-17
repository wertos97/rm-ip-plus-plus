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
print("discovery OK")

from sony_client import SonyCamera
c = SonyCamera("127.0.0.1")
assert c.web_url() == "http://127.0.0.1:80/"
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

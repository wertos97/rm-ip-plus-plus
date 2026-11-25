import json
from pathlib import Path

import config_store
import discovery
import net_manager
import subnet_bridge


def test_config_defaults_are_independent_and_save_is_atomic(tmp_path):
    first = config_store.load()
    first["known_ips"].append("192.168.1.10")
    first["credentials"]["192.168.1.10"] = {"user": "admin", "password": "test"}
    assert config_store.load()["known_ips"] == []

    config_store.save(first)
    assert json.loads(Path(config_store.CONFIG_FILE).read_text(encoding="utf-8")) == first
    assert not list(tmp_path.rglob(".config-*.tmp"))


def test_malformed_config_falls_back_to_defaults():
    config_store.save({"scan_cidr": "10.0.0.0/24"})
    with open(config_store.CONFIG_FILE, "w", encoding="utf-8") as file:
        file.write("{broken")
    config = config_store.load()
    assert config["scan_cidr"] == "192.168.0.0/24"
    assert config["known_ips"] == []


def test_discovery_merge_keeps_foreign_subnet_camera():
    merged = discovery.merge_udp(
        [],
        [
            {
                "ip": "10.0.0.9",
                "model": "SRG-X400",
                "name": "CAM9",
                "mac": "00-11-22-33-44-55",
                "src_ip": "10.0.0.9",
            }
        ],
    )
    assert merged[0]["ip"] == "10.0.0.9"
    assert merged[0]["http"] is False
    assert "CAM9" in merged[0]["model"]
    assert "no HTTP confirmation" in merged[0]["note"]


def test_bridge_helpers_and_virtual_adapter_detection():
    assert subnet_bridge.bridge_ip_for("10.5.5.5") == "10.5.5.200"
    assert subnet_bridge.bridge_ip_for("192.168.0.200") == "192.168.0.201"
    assert subnet_bridge.guess_homes([{"ip": "10.5.5.5"}, {"ip": "10.5.5.6"}]) == ["10.5.5"]
    assert net_manager.is_virtual_alias("Polaczenie sieciowe Bluetooth")
    assert net_manager.is_virtual_alias("Siec komorkowa")
    assert not net_manager.is_virtual_alias("Ethernet")
    assert not net_manager.is_virtual_alias("Wi-Fi")


def test_bridge_interface_prefers_connected_ethernet(monkeypatch):
    adapters = [
        {"alias": "Ethernet", "status": "Disconnected", "mediatype": "802.3", "virtual": False},
        {"alias": "Ethernet 2", "status": "Up", "mediatype": "802.3", "virtual": False},
        {"alias": "Wi-Fi", "status": "Up", "mediatype": "Native 802.11", "virtual": False},
    ]
    monkeypatch.setattr(net_manager, "list_adapters", lambda: adapters)
    assert net_manager.best_bridge_iface() == "Ethernet 2"


def test_temp_ip_state_round_trip(monkeypatch):
    monkeypatch.setattr(net_manager, "list_ipv4_addresses", lambda: [])
    net_manager._save_state([{"interface_alias": "Ethernet", "ip": "192.168.0.200", "prefix": 24}])
    assert net_manager.find_orphans() == [{"interface_alias": "Ethernet", "ip": "192.168.0.200", "prefix": 24}]

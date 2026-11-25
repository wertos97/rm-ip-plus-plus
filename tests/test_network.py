import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

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


def test_non_object_config_falls_back_to_defaults():
    config_store.save({})
    for value in ("null", "[]", '"text"', "42"):
        with open(config_store.CONFIG_FILE, "w", encoding="utf-8") as file:
            file.write(value)
        config = config_store.load()
        assert config["scan_cidr"] == "192.168.0.0/24"


def test_cleanup_runs_again_for_addresses_added_later(monkeypatch):
    removed = []
    monkeypatch.setattr(net_manager, "_load_state", lambda: list(net_manager._test_state))
    monkeypatch.setattr(net_manager, "_save_state", lambda items: setattr(net_manager, "_test_state", list(items)))

    def fake_remove(alias, ip):
        removed.append((alias, ip))
        net_manager._forget(alias, ip)
        return True, f"Removed {ip}"

    monkeypatch.setattr(net_manager, "remove_temp_ip", fake_remove)
    net_manager._test_state = [{"interface_alias": "Ethernet", "ip": "192.168.0.200", "prefix": 24}]
    net_manager.cleanup_all()
    net_manager._test_state.append({"interface_alias": "Ethernet", "ip": "192.168.1.200", "prefix": 24})
    net_manager.cleanup_all()
    assert removed == [("Ethernet", "192.168.0.200"), ("Ethernet", "192.168.1.200")]


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
    monkeypatch.setattr(net_manager, "_query_ipv4_addresses", lambda: [])
    net_manager._save_state([{"interface_alias": "Ethernet", "ip": "192.168.0.200", "prefix": 24}])
    assert net_manager.find_orphans() == [{"interface_alias": "Ethernet", "ip": "192.168.0.200", "prefix": 24}]


def test_windows_thumbnail_cache_keeps_legacy_temp_path(monkeypatch):
    import platform_paths

    monkeypatch.setattr(platform_paths, "IS_WINDOWS", True)
    monkeypatch.setattr(platform_paths, "IS_MACOS", False)
    monkeypatch.setattr(platform_paths.tempfile, "gettempdir", lambda: "C:/Temp")
    assert platform_paths.thumbnail_dir() == platform_paths.os.path.join("C:/Temp", "rmip_thumbs")


def test_windows_removal_does_not_trust_failed_address_query(monkeypatch):
    monkeypatch.setattr(net_manager, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(net_manager, "_query_ipv4_addresses", lambda: None)
    forgotten = []
    monkeypatch.setattr(net_manager, "_forget", lambda alias, ip: forgotten.append((alias, ip)))
    ok, message = net_manager.remove_temp_ip("Ethernet", "192.168.0.200")
    assert not ok
    assert "Could not query" in message
    assert forgotten == []


def test_windows_removal_is_not_reported_before_verification(monkeypatch):
    monkeypatch.setattr(net_manager, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(net_manager, "is_admin", lambda: False)
    monkeypatch.setattr(
        net_manager,
        "_query_ipv4_addresses",
        lambda: [{"alias": "Ethernet", "ip": "192.168.0.200", "prefix": 24}],
    )
    monkeypatch.setattr(
        net_manager,
        "_run_ps",
        lambda *args, **kwargs: subprocess.CompletedProcess([], 0, stdout="", stderr=""),
    )
    forgotten = []
    monkeypatch.setattr(net_manager, "_forget", lambda alias, ip: forgotten.append((alias, ip)))
    ok, message = net_manager.remove_temp_ip("Ethernet", "192.168.0.200")
    assert not ok
    assert "not confirmed" in message
    assert forgotten == []

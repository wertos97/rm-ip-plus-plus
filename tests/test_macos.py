import os
import posixpath
import subprocess
from types import SimpleNamespace

import diagnostics
import edge_view
import net_manager
import platform_paths
import subnet_bridge


def posix_os():
    return SimpleNamespace(
        name="posix",
        path=os.path,
        makedirs=os.makedirs,
        geteuid=lambda: 0,
    )


def completed(stdout="", returncode=0):
    return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr="")


def test_macos_application_paths(monkeypatch):
    monkeypatch.setattr(platform_paths, "IS_WINDOWS", False)
    monkeypatch.setattr(platform_paths, "IS_MACOS", True)
    monkeypatch.setattr(platform_paths, "os", SimpleNamespace(path=posixpath))
    monkeypatch.setattr(posixpath, "expanduser", lambda value: "/Users/test" + value[1:])
    assert platform_paths.app_data_dir() == "/Users/test/Library/Application Support/RMIP++"
    assert platform_paths.cache_dir() == "/Users/test/Library/Caches/RMIP++"
    assert platform_paths.thumbnail_dir().endswith("/Library/Caches/RMIP++/thumbnails")


def test_macos_ifconfig_address_parsing(monkeypatch):
    monkeypatch.setattr(net_manager, "os", posix_os())
    output = (
        "en0: flags=8863<UP,BROADCAST,SMART,RUNNING,SIMPLEX,MULTICAST> mtu 1500\n"
        "    inet 192.168.1.10 netmask 0xffffff00 broadcast 192.168.1.255\n"
        "en1: flags=8963<UP,BROADCAST,SMART,RUNNING,PROMISC,SIMPLEX,MULTICAST> mtu 1500\n"
        "    inet 192.168.0.200 netmask 255.255.255.0 broadcast 192.168.0.255\n"
    )
    monkeypatch.setattr(net_manager, "_run", lambda *args, **kwargs: completed(output))
    assert net_manager.list_ipv4_addresses() == [
        {"alias": "en0", "ip": "192.168.1.10", "prefix": 24},
        {"alias": "en1", "ip": "192.168.0.200", "prefix": 24},
    ]


def test_macos_adapter_selection(monkeypatch):
    monkeypatch.setattr(net_manager, "os", posix_os())
    hardware = (
        "Hardware Port: Ethernet\n"
        "Device: en0\n"
        "Ethernet Address: aa:bb:cc:dd:ee:ff\n\n"
        "Hardware Port: Wi-Fi\n"
        "Device: en1\n"
        "Ethernet Address: 11:22:33:44:55:66\n\n"
    )

    def run(command, **kwargs):
        if command[0] == "networksetup":
            return completed(hardware)
        if command == ["ifconfig", "en0"]:
            return completed("en0: flags=8863<UP,BROADCAST,RUNNING> status: active\n")
        return completed("en1: flags=8823<UP,BROADCAST,RUNNING> status: inactive\n")

    monkeypatch.setattr(net_manager, "_run", run)
    assert net_manager.best_bridge_iface() == "en0"


def test_macos_arp_parsing(monkeypatch):
    monkeypatch.setattr(subnet_bridge, "os", SimpleNamespace(name="posix"))
    output = (
        "? (192.168.1.20) at aa:bb:cc:dd:ee:ff on en0 ifscope [ethernet]\n"
        "? (192.168.1.255) at ff:ff:ff:ff:ff:ff on en0 ifscope [ethernet]\n"
    )
    monkeypatch.setattr(subnet_bridge, "_run", lambda *args, **kwargs: completed(output))
    assert subnet_bridge.arp_candidates() == [
        {
            "ip": "192.168.1.20",
            "mac": "aa:bb:cc:dd:ee:ff",
            "state": "reachable",
            "via": "arp",
            "iface": "en0",
        }
    ]


def test_macos_alias_command(monkeypatch):
    monkeypatch.setattr(net_manager, "os", posix_os())
    calls = []
    monkeypatch.setattr(net_manager, "is_admin", lambda: True)
    monkeypatch.setattr(net_manager, "_run", lambda command, **kwargs: calls.append(command) or completed())
    ok, _ = net_manager.add_temp_ip("en0", "192.168.0.200", 24)
    assert ok
    assert calls == [["/sbin/ifconfig", "en0", "alias", "192.168.0.200", "netmask", "255.255.255.0"]]


def test_macos_bridge_uses_one_admin_prompt(monkeypatch, tmp_path):
    monkeypatch.setattr(net_manager, "os", posix_os())
    monkeypatch.setattr(net_manager, "STATE_FILE", str(tmp_path / "temp_ips.json"))
    addresses = []
    prompts = []

    def current_addresses():
        return list(addresses)

    def admin(command, timeout=90):
        prompts.append(command)
        addresses.extend(
            [
                {"alias": "en0", "ip": "192.168.0.200", "prefix": 24},
                {"alias": "en0", "ip": "192.168.1.200", "prefix": 24},
            ]
        )
        return completed()

    monkeypatch.setattr(net_manager, "list_ipv4_addresses", current_addresses)
    monkeypatch.setattr(net_manager, "is_admin", lambda: False)
    monkeypatch.setattr(net_manager, "_run_admin_macos", admin)
    ok, message = net_manager.ensure_homes_visible("en0", ["192.168.0.10", "192.168.1.10"])
    assert ok
    assert "192.168.0.200" in message and "192.168.1.200" in message
    assert len(prompts) == 1
    assert prompts[0][:2] == ["/bin/sh", "-c"]
    assert "; " in prompts[0][2]


def test_macos_ping_command(monkeypatch):
    monkeypatch.setattr(diagnostics, "os", SimpleNamespace(name="posix"))
    calls = []
    monkeypatch.setattr(diagnostics.subprocess, "run", lambda command, **kwargs: calls.append(command) or completed())
    diagnostics.ping("127.0.0.1", timeout_ms=800)
    assert calls == [["ping", "-c", "1", "-t", "1", "127.0.0.1"]]


def test_macos_browser_detection(monkeypatch):
    monkeypatch.setattr(
        edge_view,
        "os",
        SimpleNamespace(name="posix", path=SimpleNamespace(exists=lambda path: path == edge_view.CHROME_EXE_MACOS)),
    )
    assert edge_view.browser_exe() == edge_view.CHROME_EXE_MACOS

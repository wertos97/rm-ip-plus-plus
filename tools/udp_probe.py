"""Podglad protokolu Sony UDP 52380: wykrywanie, SET sieci, tabela panelu.

To te same mechanizmy, ktorych uzywa oryginalny RM-IP Setup Tool:
  * ENQ:network  -> lista kamer (odpowiada tez kamera z innej podsieci),
  * ENQ:camtable -> tabela kamer z panelu RM-IP (4 strony po 28 slotow),
  * SET sieci    -> zmiana IP/maski/bramy/nazwy kamery po MAC (broadcast L2).

Uzycie:
  python tools/udp_probe.py [--timeout 2.5]
  python tools/udp_probe.py --camtable
  python tools/udp_probe.py --write --mac F8-4E-17-DE-30-9F --ip 192.168.4.101 \
      --mask 255.255.255.0 --gw 192.168.4.1 --name CAM2 [--yes]
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

import sony_udp  # noqa: E402


def _raw(data: bytes) -> str:
    return "".join(ch if 0x20 <= ord(ch) < 0x7F else "."
                   for ch in data.decode("latin-1", "replace"))


def cmd_list(args) -> int:
    ips = sony_udp.local_ipv4s()
    print(f"Local IPv4: {', '.join(ips) if ips else '(none)'}")
    print(f"Sending {sony_udp.build_request()!r} to UDP broadcast "
          f"{sony_udp.SONY_UDP_PORT}...")
    cams = sony_udp.discover(timeout=args.timeout, log=lambda s: print("  " + s))
    if not cams:
        print("No replies (no Sony camera responded).")
        return 0
    print(f"\nFound {len(cams)} cameras:")
    for c in cams:
        print(f"  * {c['ip']:>15}  model={c['model']:<12} name={c['name']:<10} "
              f"MAC={c['mac']:<18} FW={c['softversion']:<6}  "
              f"mask={c['mask']} gateway={c['gateway']} WRITE:{c.get('writable') or '?'}")
    return 0


def cmd_camtable(args) -> int:
    print("Sending ENQ:camtable1..4 to UDP 52380 broadcast...")
    res = sony_udp.query_camtable(timeout=args.timeout + 2.0,
                                  log=lambda s: print("  " + s))
    pages = res["pages"]
    if not pages:
        print("No panel replies (0 pages).")
        return 0
    for p in sorted(pages, key=lambda x: (x["src_ip"], x["page"])):
        print(f"\nPage {p['page']}  panel={p['panel_mac'] or '?'}  from {p['src_ip']}")
        for e in p["entries"]:
            filled = bool(e["mac"] or e["ip"] or e["name"])
            print(f"  {'*' if filled else ' '} CAM{e['slot']:03d}  "
                  f"{e['mac'] or '-':17}  {e['ip'] or '-':15}  {e['name'] or ''}")
    for m in res["misc"]:
        print(f"\nExtra reply from {m['src_ip']}: {m['kind']}  "
              f"{_raw(m.get('raw') or b'')}")
    return 0


def cmd_write(args) -> int:
    try:
        mac = sony_udp.normalize_mac(args.mac)
    except ValueError as e:
        print(f"Blad: {e}")
        return 2
    if not sony_udp.is_ipv4(args.ip):
        print("Error: --ip must be a valid IPv4 address")
        return 2
    print(f"Network SET for {mac}:")
    print(f"  IP={args.ip}  mask={args.mask}  gateway={args.gw or '(empty)'}  "
          f"name={args.name}")
    if not args.yes:
        try:
            ans = input("Send? The camera changes its address right after the ACK [y/N]: ")
        except EOFError:
            ans = ""
        if ans.strip().lower() not in ("t", "tak", "y", "yes"):
            print("Aborted.")
            return 1
    res = sony_udp.set_camera_network(mac, args.ip, args.mask, args.gw, args.name,
                                      timeout=args.timeout + 2.0)
    print(f"Wynik: {res['kind']}  ok={res['ok']}")
    for r in res.get("replies", []):
        print(f"  from {r['src_ip']:>15}  {r['kind']}  mac={r['mac'] or '-'}  "
              f"{_raw(r['raw'])}")
    if not res.get("replies"):
        print("  (0 replies)")
    return 0 if res.get("ok") else 3


def main() -> int:
    ap = argparse.ArgumentParser(description="Sony UDP 52380: discovery/SET/camtable")
    ap.add_argument("--timeout", type=float, default=2.5,
                    help="seconds to wait for replies (default 2.5)")
    ap.add_argument("--camtable", action="store_true",
                    help="read the camera table from the RM-IP panel (ENQ:camtable1..4)")
    ap.add_argument("--write", action="store_true",
                    help="camera network SET (requires --mac, --ip, --name)")
    ap.add_argument("--mac", default="", help="camera MAC, e.g. F8-4E-17-DE-30-9F")
    ap.add_argument("--ip", default="", help="new camera IP address")
    ap.add_argument("--mask", default="255.255.255.0", help="subnet mask")
    ap.add_argument("--gw", default="", help="gateway (may be empty)")
    ap.add_argument("--name", default="", help="camera name (1-16 ASCII characters)")
    ap.add_argument("--yes", action="store_true", help="no confirmation prompt")
    args = ap.parse_args()
    if args.write:
        if not args.mac or not args.ip or not args.name:
            print("Error: --write requires --mac, --ip and --name")
            return 2
        return cmd_write(args)
    if args.camtable:
        return cmd_camtable(args)
    return cmd_list(args)


if __name__ == "__main__":
    raise SystemExit(main())

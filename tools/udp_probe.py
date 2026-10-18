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
    print(f"Lokalne IPv4: {', '.join(ips) if ips else '(brak)'}")
    print(f"Wysylam {sony_udp.build_request()!r} na broadcast UDP "
          f"{sony_udp.SONY_UDP_PORT}...")
    cams = sony_udp.discover(timeout=args.timeout, log=lambda s: print("  " + s))
    if not cams:
        print("Brak odpowiedzi (zadna kamera Sony nie odpowiedziala).")
        return 0
    print(f"\nZnaleziono {len(cams)} kamer:")
    for c in cams:
        print(f"  * {c['ip']:>15}  model={c['model']:<12} nazwa={c['name']:<10} "
              f"MAC={c['mac']:<18} FW={c['softversion']:<6}  "
              f"maska={c['mask']} brama={c['gateway']} WRITE:{c.get('writable') or '?'}")
    return 0


def cmd_camtable(args) -> int:
    print("Wysylam ENQ:camtable1..4 na broadcast UDP 52380...")
    res = sony_udp.query_camtable(timeout=args.timeout + 2.0,
                                  log=lambda s: print("  " + s))
    pages = res["pages"]
    if not pages:
        print("Brak odpowiedzi panelu (0 stron).")
        return 0
    for p in sorted(pages, key=lambda x: (x["src_ip"], x["page"])):
        print(f"\nStrona {p['page']}  panel={p['panel_mac'] or '?'}  z {p['src_ip']}")
        for e in p["entries"]:
            filled = bool(e["mac"] or e["ip"] or e["name"])
            print(f"  {'*' if filled else ' '} CAM{e['slot']:03d}  "
                  f"{e['mac'] or '-':17}  {e['ip'] or '-':15}  {e['name'] or ''}")
    for m in res["misc"]:
        print(f"\nDodatkowa odpowiedz z {m['src_ip']}: {m['kind']}  "
              f"{_raw(m.get('raw') or b'')}")
    return 0


def cmd_write(args) -> int:
    try:
        mac = sony_udp.normalize_mac(args.mac)
    except ValueError as e:
        print(f"Blad: {e}")
        return 2
    if not sony_udp.is_ipv4(args.ip):
        print("Blad: --ip musi byc poprawnym adresem IPv4")
        return 2
    print(f"SET sieci dla {mac}:")
    print(f"  IP={args.ip}  maska={args.mask}  brama={args.gw or '(pusta)'}  "
          f"nazwa={args.name}")
    if not args.yes:
        try:
            ans = input("Wyslac? Kamera zmieni adres od razu po ACK [t/N]: ")
        except EOFError:
            ans = ""
        if ans.strip().lower() not in ("t", "tak", "y", "yes"):
            print("Przerwano.")
            return 1
    res = sony_udp.set_camera_network(mac, args.ip, args.mask, args.gw, args.name,
                                      timeout=args.timeout + 2.0)
    print(f"Wynik: {res['kind']}  ok={res['ok']}")
    for r in res.get("replies", []):
        print(f"  z {r['src_ip']:>15}  {r['kind']}  mac={r['mac'] or '-'}  "
              f"{_raw(r['raw'])}")
    if not res.get("replies"):
        print("  (0 odpowiedzi)")
    return 0 if res.get("ok") else 3


def main() -> int:
    ap = argparse.ArgumentParser(description="Sony UDP 52380: wykrywanie/SET/camtable")
    ap.add_argument("--timeout", type=float, default=2.5,
                    help="ile sekund czekac na odpowiedzi (domyslnie 2.5)")
    ap.add_argument("--camtable", action="store_true",
                    help="odczytaj tabele kamer z panelu RM-IP (ENQ:camtable1..4)")
    ap.add_argument("--write", action="store_true",
                    help="SET sieci kamery (wymaga --mac, --ip, --name)")
    ap.add_argument("--mac", default="", help="MAC kamery, np. F8-4E-17-DE-30-9F")
    ap.add_argument("--ip", default="", help="nowy adres IP kamery")
    ap.add_argument("--mask", default="255.255.255.0", help="maska podsieci")
    ap.add_argument("--gw", default="", help="brama (moze byc pusta)")
    ap.add_argument("--name", default="", help="nazwa kamery (1-16 znakow ASCII)")
    ap.add_argument("--yes", action="store_true", help="bez pytania o potwierdzenie")
    args = ap.parse_args()
    if args.write:
        if not args.mac or not args.ip or not args.name:
            print("Blad: --write wymaga --mac, --ip i --name")
            return 2
        return cmd_write(args)
    if args.camtable:
        return cmd_camtable(args)
    return cmd_list(args)


if __name__ == "__main__":
    raise SystemExit(main())

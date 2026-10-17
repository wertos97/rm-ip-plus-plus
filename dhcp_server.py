"""Mini serwer DHCP na karte od kamer: nadaje X400 znane IP.

Kamera jest klientem DHCP (wyslala DISCOVER, chaddr 96-78-77-89-63-9e) i bez
serwera nie ma w ogole adresu - stad cisza na 192.168.0.100. Ten serwer
oferuje jej 192.168.0.101/24 z server-id 192.168.0.200 (nasz most), BEZ opcji
routera - zeby PC dalej wychodzil do internetu przez WiFi.
"""
import socket
import struct
import time

SERVER_IP = "192.168.0.200"
OFFER_IP = "192.168.0.101"
MASK = "255.255.255.0"
LEASE = 3600


def ipb(ip: str) -> bytes:
    return bytes(int(x) for x in ip.split("."))


def build_reply(req: bytes, msg_type: int, yiaddr: str) -> bytes:
    xid = req[4:8]
    flags = req[10:12]
    chaddr = req[28:44]  # 16 bajtow
    pkt = struct.pack("!BBBBIHH", 2, 1, 6, 0, struct.unpack("!I", xid)[0], 0, struct.unpack("!H", flags)[0])
    pkt += b"\x00" * 4            # ciaddr
    pkt += ipb(yiaddr)            # yiaddr
    pkt += ipb(SERVER_IP)         # siaddr
    pkt += b"\x00" * 4            # giaddr
    pkt += chaddr                 # chaddr 16B
    pkt += b"\x00" * 64           # sname
    pkt += b"\x00" * 128          # file
    pkt += bytes([99, 130, 53, 63])
    opts = bytes([53, 1, msg_type,
                  54, 4]) + ipb(SERVER_IP)
    opts += bytes([1, 4]) + ipb(MASK)
    opts += bytes([51, 4]) + struct.pack("!I", LEASE)
    # BRAK opcji 3 (router) - internet zostaje na WiFi
    opts += bytes([255])
    pkt += opts
    return pkt.ljust(300, b"\x00")


def opt53(data: bytes) -> int | None:
    try:
        i = data.index(bytes([99, 130, 53, 63])) + 4
    except ValueError:
        return None
    while i < len(data):
        c = data[i]
        if c == 255:
            break
        if c == 0:
            i += 1
            continue
        ln = data[i + 1]
        if c == 53 and ln >= 1:
            return data[i + 2]
        i += 2 + ln
    return None


def main(duration: int = 300):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    s.bind(("0.0.0.0", 67))
    s.settimeout(5)
    print(f"DHCP serwer: {OFFER_IP} <- {SERVER_IP} ({duration} s, celuj w kamere)...", flush=True)
    end = time.time() + duration
    acked = False
    while time.time() < end and not acked:
        try:
            data, addr = s.recvfrom(1024)
        except socket.timeout:
            continue
        t = opt53(data)
        mac = data[28:34].hex("-") if len(data) >= 34 else "?"
        if t == 1:
            print(f"DISCOVER od {mac} -> OFFER {OFFER_IP}", flush=True)
            s.sendto(build_reply(data, 2, OFFER_IP), ("255.255.255.255", 68))
        elif t == 3:
            print(f"REQUEST od {mac} -> ACK {OFFER_IP}", flush=True)
            s.sendto(build_reply(data, 5, OFFER_IP), ("255.255.255.255", 68))
            acked = True
        elif t is not None:
            print(f"DHCP typ {t} od {mac}", flush=True)
    if acked:
        print("SUKCES: kamera przyjela", OFFER_IP, flush=True)
    else:
        print("Koniec czasu bez REQUEST.", flush=True)


if __name__ == "__main__":
    import sys
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 300)

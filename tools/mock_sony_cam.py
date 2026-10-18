"""Mock kamery Sony do testow BEZ sprzetu.

Stawia na 127.0.0.1:
  - HTTP 8080: '/' + '/command/inquiry.cgi?inq=network' + '/command/network.cgi?...'
  - TCP 52381: fake VISCA (odpowiada ACK 90 41 FF na kazda ramke)

Uzycie:
  python tools/mock_sony_cam.py
Potem w RM IP++: CIDR/skan reczny 127.0.0.1 albo szybki skan po dopisaniu
127.0.0.1 do LIKELY_DEFAULTS - albo po prostu test E2E ponizej.
"""
from __future__ import annotations

import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

STATE = {"IpAddress": "127.0.0.1", "Subnetmask": "255.255.255.0",
         "DefaultGateway": "127.0.0.1", "Dhcp": "off",
         "CameraName": "MOCK-X400", "ModelName": "SRG-X400-MOCK"}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, body: str, code: int = 200):
        b = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/command/inquiry.cgi":
            lines = "\n".join(f"{k}={v}" for k, v in STATE.items())
            return self._send(lines)
        if u.path == "/command/network.cgi":
            q = parse_qs(u.query)
            for k in ("IpAddress", "Subnetmask", "DefaultGateway", "Dhcp"):
                if k in q:
                    STATE[k] = q[k][0]
            return self._send("OK:network.cgi set\n")
        return self._send("<html><body><h1>MOCK SRG-X400</h1><p>Fake web UI - for testing tabs.</p></body></html>")


def visca_loop():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 52381))
    srv.listen(5)
    while True:
        c, _ = srv.accept()
        try:
            data = c.recv(256)
            if data:
                c.sendall(bytes.fromhex("90 41 FF"))  # ACK
        except Exception:
            pass
        finally:
            c.close()


def main():
    threading.Thread(target=visca_loop, daemon=True).start()
    HTTPServer(("127.0.0.1", 8080), H).serve_forever()


if __name__ == "__main__":
    print("Mock on 127.0.0.1:8080 (HTTP) + 127.0.0.1:52381 (VISCA). Ctrl+C to stop.")
    main()

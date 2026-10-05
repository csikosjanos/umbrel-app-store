#!/usr/bin/env python3
"""CI smoke test: drive the real ttyd + tmux through the web container's
WebSocket proxy, run a command in the shell and wait for its output.

Usage: smoke_ws.py HOST:PORT COMMAND EXPECTED [TIMEOUT]
       smoke_ws.py HOST:PORT --expect-refused
The terminal token is read from the UI page, exactly like the browser does.
The first form exits 0 when EXPECTED appears in the terminal output. The
second exits 0 when upgrades without the token (incl. a foreign Origin plus
cookies) are refused and one with the token is accepted. Stdlib only. Not
shipped in the image; never prints the token.
"""
import base64
import json
import os
import re
import socket
import struct
import sys
import time
import urllib.request


def frame(payload, opcode=2):
    """Client frame (always masked, as the RFC requires)."""
    mask = os.urandom(4)
    n = len(payload)
    head = bytes([0x80 | opcode])
    if n < 126:
        head += bytes([0x80 | n])
    elif n < 65536:
        head += bytes([0x80 | 126]) + struct.pack(">H", n)
    else:
        head += bytes([0x80 | 127]) + struct.pack(">Q", n)
    return head + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload))


class Reader:
    """Frame reader that keeps partial frames across recv timeouts."""

    def __init__(self, sock):
        self.sock, self.buf = sock, b""

    def _parse(self):
        b = self.buf
        if len(b) < 2:
            return None
        n, i = b[1] & 0x7F, 2
        if n == 126:
            if len(b) < 4:
                return None
            n, i = struct.unpack(">H", b[2:4])[0], 4
        elif n == 127:
            if len(b) < 10:
                return None
            n, i = struct.unpack(">Q", b[2:10])[0], 10
        if b[1] & 0x80:
            i += 4  # servers do not mask, but be lenient
        if len(b) < i + n:
            return None
        self.buf = b[i + n:]
        return b[0] & 0x0F, b[i:i + n]

    def message(self):
        while True:
            f = self._parse()
            if f:
                return f
            chunk = self.sock.recv(65536)  # may time out; self.buf stays intact
            if not chunk:
                raise EOFError("connection closed")
            self.buf += chunk


def page_token(hostport):
    with urllib.request.urlopen("http://%s/" % hostport, timeout=10) as r:
        body = r.read().decode()
    m = re.search(r'TERMINAL_URL = "terminal/\?fm_token=([A-Za-z0-9_-]+)"', body)
    if not m:
        sys.exit("no terminal token in the UI page")
    return m.group(1)


def upgrade(hostport, path, origin=None, cookie=None):
    """Send a WebSocket upgrade; return (socket, status line, rest)."""
    host, port = hostport.rsplit(":", 1)
    s = socket.create_connection((host, int(port)), timeout=10)
    key = base64.b64encode(os.urandom(16)).decode()
    extra = ""
    if origin:
        extra += "Origin: %s\r\n" % origin
    if cookie:
        extra += "Cookie: %s\r\n" % cookie
    s.sendall(("GET %s HTTP/1.1\r\nHost: %s\r\n%sUpgrade: websocket\r\nConnection: Upgrade\r\n"
               "Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\nSec-WebSocket-Protocol: tty\r\n\r\n"
               % (path, hostport, extra, key)).encode())
    head = b""
    while b"\r\n\r\n" not in head:
        chunk = s.recv(4096)
        if not chunk:
            break
        head += chunk
    status, _, rest = head.partition(b"\r\n\r\n")
    return s, status.decode("latin-1").split("\r\n")[0], rest


def expect_refused(hostport, token):
    host = hostport.split(":")[0]
    cases = [("no token", "/terminal/ws", None, None),
             ("no token, same Origin", "/terminal/ws", "http://" + hostport, None),
             ("foreign Origin + cookies", "/terminal/ws", "http://%s:2000" % host, "fm_ws=x; UMBREL_PROXY_TOKEN=x"),
             ("wrong token", "/terminal/ws?fm_token=wrong", None, None)]
    for name, path, origin, cookie in cases:
        s, status, _ = upgrade(hostport, path, origin, cookie)
        s.close()
        print("%-26s -> %s" % (name, status))
        if " 403 " not in status + " ":
            sys.exit("expected 403 for: " + name)
    s, status, _ = upgrade(hostport, "/terminal/ws?fm_token=" + token)
    s.close()
    print("%-26s -> %s" % ("token from the page", status))
    if " 101 " not in status + " ":
        sys.exit("upgrade with the page token was not accepted")
    return 0


def main():
    hostport = sys.argv[1]
    token = page_token(hostport)
    if sys.argv[2:] == ["--expect-refused"]:
        return expect_refused(hostport, token)
    command, expected = sys.argv[2:4]
    timeout = float(sys.argv[4]) if len(sys.argv) > 4 else 60
    s, status, rest = upgrade(hostport, "/terminal/ws?fm_token=" + token, origin="http://" + hostport)
    print(status)
    if " 101 " not in status + " ":
        sys.exit("WebSocket upgrade refused")
    r = Reader(s)
    r.buf = rest
    # ttyd protocol: first message = JSON auth/size, then '0'+input.
    s.sendall(frame(json.dumps({"AuthToken": "", "columns": 160, "rows": 40}).encode()))
    deadline = time.time() + timeout
    out = b""
    next_send = time.time() + 3  # give tmux + bash a moment to start
    s.settimeout(1)
    while time.time() < deadline:
        if time.time() >= next_send:
            s.sendall(frame(b"0" + command.encode() + b"\r"))
            next_send = time.time() + 10
        try:
            op, data = r.message()
        except socket.timeout:
            continue
        if op == 8:
            sys.exit("server closed the WebSocket")
        if data[:1] == b"0":
            out += data[1:]
            if expected.encode() in out:
                print("found %r in terminal output" % expected)
                return 0
    tail = out[-2000:].decode("utf-8", "replace")
    sys.exit("timed out waiting for %r; output tail:\n%s" % (expected, tail))


if __name__ == "__main__":
    sys.exit(main())

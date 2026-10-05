"""Tests for server.py with a fake ttyd on a UNIX socket.

Run: python3 -m unittest -v test_server.py   (no root, no Docker, no network)
"""
import json
import os
import socket
import socketserver
import stat
import subprocess
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

TMP = tempfile.mkdtemp()
os.environ.update(SETTINGS_DIR=os.path.join(TMP, "settings"),
                  TTYD_SOCK=os.path.join(TMP, "ttyd.sock"))

import server  # noqa: E402  (env must be set first)

# Deliberately nasty: quotes, $(), backticks, newline, unicode.
SECRET = "sk-ant-TEST'\"$(touch /tmp/pwned)`id`\nline2 é"
LOGS = []
server.log = LOGS.append


class FakeTtyd(socketserver.StreamRequestHandler):
    """Speaks just enough HTTP: a page, a redirect and a WebSocket echo."""
    seen = []

    def handle(self):
        head = b""
        while not head.endswith(b"\r\n\r\n"):
            b = self.rfile.read(1)
            if not b:
                return
            head += b
        req = head.decode("latin-1")
        FakeTtyd.seen.append(req)
        path = req.split(" ")[1]
        if "upgrade: websocket" in req.lower():
            self.wfile.write(b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n"
                             b"Connection: Upgrade\r\nSec-WebSocket-Accept: x\r\n\r\n")
            while True:
                data = self.request.recv(4096)
                if not data:
                    return
                self.request.sendall(b"echo:" + data)
        if path == "/terminal":
            resp = b"HTTP/1.1 301 Moved\r\nLocation: /terminal/\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
        else:
            body = b"<html>fake ttyd</html>"
            resp = (b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: %d\r\n"
                    b"Connection: close\r\n\r\n%s" % (len(body), body))
        self.wfile.write(resp)


class UnixServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True


ttyd = UnixServer(os.environ["TTYD_SOCK"], FakeTtyd)
threading.Thread(target=ttyd.serve_forever, daemon=True).start()

server.Handler.store = server.Store()
ui = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
ui.daemon_threads = True
threading.Thread(target=ui.serve_forever, daemon=True).start()
BASE = "http://127.0.0.1:%d" % ui.server_port


def call(method, path, body=None, header=True, headers=None):
    h = dict(headers or {})
    if header:
        h["X-Firstmate-UI"] = "1"
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        h["Content-Type"] = "application/json"

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None

    opener = urllib.request.build_opener(NoRedirect)
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=h)
    try:
        with opener.open(req, timeout=10) as r:
            return r.status, r.read().decode(), dict(r.headers)
    except urllib.error.HTTPError as e:
        try:
            return e.code, e.read().decode(), dict(e.headers)
        finally:
            e.close()


def env_after_source(var):
    """The value bash sees for $var after sourcing env.sh."""
    out = subprocess.run(["bash", "-c", '. "$1"; printf %s "${!2-<unset>}"', "_", server.ENV_SH, var],
                         capture_output=True, text=True, check=True)
    return out.stdout


def ws_handshake(origin=None, cookie=None, host=None):
    s = socket.create_connection(("127.0.0.1", ui.server_port), timeout=5)
    lines = ["GET /terminal/ws HTTP/1.1", "Host: %s" % (host or "127.0.0.1:%d" % ui.server_port),
             "Upgrade: websocket", "Connection: Upgrade", "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==",
             "Sec-WebSocket-Version: 13", "Sec-WebSocket-Protocol: tty"]
    if origin:
        lines.append("Origin: " + origin)
    if cookie:
        lines.append("Cookie: other=1; " + cookie)
    s.sendall(("\r\n".join(lines) + "\r\n\r\n").encode())
    head = b""
    while b"\r\n\r\n" not in head:
        chunk = s.recv(4096)
        if not chunk:
            break
        head += chunk
    return s, head.decode("latin-1")


class T(unittest.TestCase):
    def tearDown(self):
        server._peers.update(at=0)

    def test_01_index_and_cookie(self):
        code, body, headers = call("GET", "/", header=False)
        self.assertEqual(code, 200)
        self.assertIn("<title>Firstmate</title>", body)
        cookie = headers.get("Set-Cookie", "")
        self.assertIn("fm_ws=", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Strict", cookie)

    def test_02_secret_is_write_only(self):
        code, body, _ = call("PUT", "/api/vars/ANTHROPIC_API_KEY", {"value": SECRET})
        self.assertEqual(code, 200)
        self.assertNotIn("sk-ant-TEST", body)
        code, body, _ = call("GET", "/api/settings", header=False)
        self.assertNotIn("sk-ant-TEST", body)
        v = next(x for x in json.loads(body)["vars"] if x["key"] == "ANTHROPIC_API_KEY")
        self.assertTrue(v["set"])
        self.assertTrue(v["builtin"])
        self.assertTrue(v["updated"])
        self.assertNotIn("value", v)
        self.assertFalse(any("sk-ant-TEST" in line for line in LOGS))

    def test_03_env_file_exact_value_and_modes(self):
        call("PUT", "/api/vars/ANTHROPIC_API_KEY", {"value": SECRET})
        self.assertEqual(env_after_source("ANTHROPIC_API_KEY"), SECRET)
        self.assertFalse(os.path.exists("/tmp/pwned"))
        for p in (server.ENV_SH, server.SETTINGS):
            self.assertEqual(stat.S_IMODE(os.stat(p).st_mode), 0o600, p)
        self.assertEqual(stat.S_IMODE(os.stat(server.SETTINGS_DIR).st_mode), 0o700)

    def test_04_csrf_header_required(self):
        code, _, _ = call("PUT", "/api/vars/CSRF_TEST", {"value": "x"}, header=False)
        self.assertEqual(code, 403)
        self.assertNotIn("CSRF_TEST", server.Handler.store.cfg["vars"])
        code, _, _ = call("DELETE", "/api/vars/ANTHROPIC_API_KEY", header=False)
        self.assertEqual(code, 403)

    def test_05_validation(self):
        for key, value in (("1BAD", "x"), ("BAD-NAME", "x"), ("PATH", "x"), ("BASH_ENV", "x"),
                           ("GIT_AUTHOR_NAME", "x"), ("OK_NAME", ""), ("OK_NAME", "a\x00b"),
                           ("OK_NAME", "x" * (64 * 1024 + 1))):
            code, body, _ = call("PUT", "/api/vars/" + key, {"value": value})
            self.assertEqual(code, 400, key)
            self.assertNotIn("x" * 20, body)
        code, _, _ = call("PUT", "/api/git", {"name": "a", "email": "not an email"})
        self.assertEqual(code, 400)

    def test_06_custom_var_add_remove_unsets(self):
        code, body, _ = call("PUT", "/api/vars/MY_TOOL_TOKEN", {"value": "v1"})
        self.assertEqual(code, 200)
        self.assertIn({"key": "MY_TOOL_TOKEN", "label": "", "builtin": False, "set": True,
                       "updated": server.Handler.store.cfg["vars"]["MY_TOOL_TOKEN"]["updated"]},
                      json.loads(body)["vars"])
        self.assertEqual(env_after_source("MY_TOOL_TOKEN"), "v1")
        code, body, _ = call("DELETE", "/api/vars/MY_TOOL_TOKEN")
        self.assertEqual(code, 200)
        self.assertNotIn("MY_TOOL_TOKEN", body)
        self.assertEqual(env_after_source("MY_TOOL_TOKEN"), "<unset>")
        # A shell that still has it from before drops it on re-source.
        out = subprocess.run(["bash", "-c", 'export MY_TOOL_TOKEN=old; . "$1"; echo "${MY_TOOL_TOKEN-gone}"',
                              "_", server.ENV_SH], capture_output=True, text=True, check=True).stdout
        self.assertEqual(out.strip(), "gone")
        self.assertEqual(call("DELETE", "/api/vars/MY_TOOL_TOKEN")[0], 404)

    def test_07_git_identity(self):
        code, body, _ = call("PUT", "/api/git", {"name": "Jane O'Doe", "email": "jane@example.com"})
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(body)["git"]["name"], "Jane O'Doe")
        self.assertEqual(env_after_source("GIT_AUTHOR_NAME"), "Jane O'Doe")
        self.assertEqual(env_after_source("GIT_COMMITTER_EMAIL"), "jane@example.com")
        call("PUT", "/api/git", {"name": "", "email": ""})
        self.assertEqual(env_after_source("GIT_AUTHOR_NAME"), "<unset>")

    def test_08_reload_from_disk(self):
        call("PUT", "/api/vars/GH_TOKEN", {"value": "ghp_" + "Z" * 36})
        s = server.Store()
        self.assertTrue(next(v for v in s.view()["vars"] if v["key"] == "GH_TOKEN")["set"])
        self.assertNotIn("Z" * 36, json.dumps(s.view()))

    def test_09_terminal_http_proxy(self):
        code, body, headers = call("GET", "/terminal/", header=False)
        self.assertEqual(code, 200)
        self.assertIn("fake ttyd", body)
        self.assertIn("fm_ws=", headers.get("Set-Cookie", ""))
        code, _, headers = call("GET", "/terminal", header=False)
        self.assertEqual(code, 301)
        self.assertEqual(headers.get("Location"), "/terminal/")
        # Browser cookies / auth headers are not passed to ttyd.
        call("GET", "/terminal/", header=False, headers={"Cookie": "UMBREL_PROXY_TOKEN=abc"})
        self.assertNotIn("UMBREL_PROXY_TOKEN", FakeTtyd.seen[-1])

    def test_10_websocket_same_origin(self):
        host = "umbrel.local:3777"
        s, head = ws_handshake(origin="http://" + host, host=host)
        self.assertIn("101 Switching Protocols", head)
        s.sendall(b"hello")
        self.assertEqual(s.recv(100), b"echo:hello")
        s.close()
        self.assertNotIn("Origin", FakeTtyd.seen[-1])

    def test_11_websocket_cross_origin(self):
        s, head = ws_handshake(origin="http://evil.example")
        self.assertIn(" 403 ", head.split("\r\n")[0])
        s.close()
        s, head = ws_handshake(origin="http://evil.example", cookie="fm_ws=wrong")
        self.assertIn(" 403 ", head.split("\r\n")[0])
        s.close()
        # Host rewritten by a proxy: our SameSite=Strict cookie still proves same-site.
        s, head = ws_handshake(origin="http://umbrel.local:3777", cookie="fm_ws=" + server.WS_COOKIE)
        self.assertIn("101", head.split("\r\n")[0])
        s.close()

    def test_12_only_gateway_peers(self):
        server._peers.update(at=float("inf"), ips={"10.9.9.9"})
        orig = server.allowed_peers
        server.allowed_peers = lambda: {"10.9.9.9"}
        try:
            for method, path in (("GET", "/"), ("GET", "/api/settings"), ("GET", "/terminal/"),
                                 ("PUT", "/api/vars/X_PEER")):
                self.assertEqual(call(method, path, {"value": "x"} if method == "PUT" else None)[0], 403, path)
            s, head = ws_handshake()
            self.assertIn(" 403 ", head.split("\r\n")[0])
            s.close()
        finally:
            server.allowed_peers = orig

    def test_13_terminal_down(self):
        orig = server.TTYD_SOCK
        server.TTYD_SOCK = os.path.join(TMP, "missing.sock")
        try:
            self.assertEqual(call("GET", "/terminal/", header=False)[0], 502)
            self.assertEqual(json.loads(call("GET", "/api/status", header=False)[1]), {"terminal": False})
        finally:
            server.TTYD_SOCK = orig
        self.assertEqual(json.loads(call("GET", "/api/status", header=False)[1]), {"terminal": True})

    def test_99_no_secret_in_logs(self):
        self.assertTrue(LOGS)
        joined = "\n".join(LOGS)
        for needle in ("sk-ant-TEST", "Z" * 36, "v1"):
            self.assertNotIn(needle, joined)


if __name__ == "__main__":
    unittest.main()

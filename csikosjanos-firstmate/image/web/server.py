#!/usr/bin/env python3
"""firstmate web UI: settings page + reverse proxy to the ttyd terminal.

Design (see ../../README.md):
- Settings (API keys / tokens for the harnesses, git identity, custom env
  vars) live in SETTINGS_DIR (0700): settings.json (0600) is the store,
  env.sh (0600) is generated from it and sourced by every bash in the fm
  container (BASH_ENV + /etc/bash.bashrc). Values are write-only: the API
  never returns them, the page never renders them, nothing logs them.
- /terminal/... is proxied to ttyd's UNIX socket on a shared volume,
  WebSocket included. ttyd listens on no TCP port at all, so the only way
  to the shell is through this server.
- Only Umbrel's app gateway may connect: loopback + this container's
  default-gateway IPs (+ EXTRA_ALLOWED_PEERS). No DNS-based trust: a name
  like <app>_app_proxy_1 does not exist on umbrelOS 2.x, so another app's
  container could claim it. Mutating requests need the X-Firstmate-UI
  header (CSRF).
- The terminal WebSocket needs TERMINAL_TOKEN, a per-process secret that is
  only embedded in the UI page (same-origin read only; CSP blocks foreign
  scripts). The page opens ttyd at /terminal/?fm_token=..., ttyd's client
  appends location.search to its WebSocket URL, and the proxy compares it
  with hmac.compare_digest. Origin/cookies are not trusted: other Umbrel
  apps on the same host (other port) are same-site.

Python stdlib only.
"""
import hmac
import http.client
import json
import os
import re
import secrets
import select
import signal
import socket
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SETTINGS_DIR = os.environ.get("SETTINGS_DIR", "/settings")
TTYD_SOCK = os.environ.get("TTYD_SOCK", "/run/fm/ttyd.sock")
PORT = int(os.environ.get("PORT", "8080"))
HERE = os.path.dirname(os.path.abspath(__file__))

SETTINGS = os.path.join(SETTINGS_DIR, "settings.json")
ENV_SH = os.path.join(SETTINGS_DIR, "env.sh")

# Shown as fixed rows in the UI; anything else is a custom variable.
BUILTIN = (
    ("GH_TOKEN", "GitHub token, used by gh and by git over HTTPS (github.com)"),
    ("ANTHROPIC_API_KEY", "Anthropic API key"),
    ("OPENAI_API_KEY", "OpenAI API key"),
    ("OPENROUTER_API_KEY", "OpenRouter API key"),
)
GIT_KEYS = ("GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL")
# CLI Proxy API (e.g. the csikosjanos-cliproxyapi app): when enabled, Claude
# Code talks to the proxy (ANTHROPIC_BASE_URL + ANTHROPIC_AUTH_TOKEN) and the
# CLIPROXYAPI_* pair is there for Pi's models.json / OpenCode's config.
PROXY_KEYS = ("ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "CLIPROXYAPI_BASE_URL", "CLIPROXYAPI_API_KEY")
# Not exported while the proxy is on: Claude Code would send it to the proxy
# and complain about two credentials.
PROXY_HIDES = ("ANTHROPIC_API_KEY",)
URL_RE = re.compile(r"^https?://[^\s/?#'\"\\]+(/[^\s?#'\"\\]*)?$")
# Names that would break the shell or the container if set from the UI.
RESERVED = set(GIT_KEYS) | set(PROXY_KEYS) | {
    "BASH_ENV", "ENV", "HOME", "PATH", "SHELL", "USER", "PWD", "OLDPWD", "IFS", "PS1", "PS2",
    "PS4", "PROMPT_COMMAND", "SHELLOPTS", "BASHOPTS", "TERM", "TMUX", "TMUX_PANE", "LANG",
    "LD_PRELOAD", "LD_LIBRARY_PATH", "NPM_CONFIG_PREFIX", "HOSTNAME",
}
KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
MAX_VALUE = 64 * 1024
TOKEN_PARAM = "fm_token"
TERMINAL_TOKEN = secrets.token_urlsafe(32)  # rotates when the web container restarts
TOKEN_PLACEHOLDER = b"__FM_TERMINAL_TOKEN__"
# ttyd's HTTP endpoints under --base-path /terminal (all read-only). Anything
# else is refused rather than passed through.
TTYD_HTTP_PATHS = ("/terminal", "/terminal/", "/terminal/token")
FORWARD_WS_HEADERS = ("Upgrade", "Connection", "Sec-WebSocket-Key", "Sec-WebSocket-Version",
                      "Sec-WebSocket-Protocol", "Sec-WebSocket-Extensions", "User-Agent")


def log(msg):
    # Only ever called with metadata (key names, paths, errors); never values.
    print(msg, flush=True)


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def write_private(path, text):
    """Write a file atomically with mode 0600."""
    tmp = path + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(text)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def shell_quote(value):
    return "'" + value.replace("'", "'\\''") + "'"


# ---------------------------------------------------------------- settings

def validate_key(key):
    if not KEY_RE.match(key or ""):
        raise ValueError("name: letters, digits and _, not starting with a digit (max 128)")
    if key in RESERVED:
        raise ValueError("name: %s is reserved" % key)
    return key


def validate_value(value):
    if not isinstance(value, str) or value == "":
        raise ValueError("value: required (use Remove to unset)")
    if len(value) > MAX_VALUE or "\x00" in value:
        raise ValueError("value: at most 64 KiB, no NUL bytes")
    return value


def validate_proxy(data):
    enabled = data.get("enabled")
    if not isinstance(enabled, bool):
        raise ValueError("enabled: true or false")
    url = str(data.get("url") or "").strip()
    if url:
        if len(url) > 2048 or not URL_RE.match(url):
            raise ValueError("url: expected http(s)://host[:port][/path]")
        # Claude Code appends /v1/messages itself, so the base has no /v1.
        url = url.rstrip("/")
        if url.endswith("/v1"):
            url = url[:-3]
    key = data.get("key")
    if key is not None and key != "":
        validate_value(key)
    return enabled, url, key or None


def validate_git(data):
    name = str(data.get("name") or "").strip()
    email = str(data.get("email") or "").strip()
    if len(name) > 200 or any(ord(c) < 32 for c in name):
        raise ValueError("name: at most 200 printable chars")
    if email and (len(email) > 254 or any(c.isspace() or ord(c) < 32 for c in email) or "@" not in email):
        raise ValueError("email: expected an email address")
    return name, email


class Store:
    """settings.json + generated env.sh. All writes hold Store.lock."""

    def __init__(self):
        self.lock = threading.Lock()
        os.makedirs(SETTINGS_DIR, exist_ok=True)
        os.chmod(SETTINGS_DIR, 0o700)
        self.cfg = {"vars": {}, "git": {}, "proxy": {}, "managed": []}
        if os.path.exists(SETTINGS):
            with open(SETTINGS) as f:
                self.cfg.update(json.load(f))
        with self.lock:
            self._save()  # (re)generate env.sh and fix modes on every start

    def _save(self):
        write_private(SETTINGS, json.dumps(self.cfg, indent=2))
        write_private(ENV_SH, self.render_env())

    def exported(self):
        """KEY -> value of everything env.sh exports."""
        out = {k: v["value"] for k, v in self.cfg["vars"].items()}
        git = self.cfg["git"]
        if git.get("name"):
            out["GIT_AUTHOR_NAME"] = out["GIT_COMMITTER_NAME"] = git["name"]
        if git.get("email"):
            out["GIT_AUTHOR_EMAIL"] = out["GIT_COMMITTER_EMAIL"] = git["email"]
        proxy = self.cfg["proxy"]
        if self.proxy_active():
            for k in PROXY_HIDES:
                out.pop(k, None)
            out["ANTHROPIC_BASE_URL"] = out["CLIPROXYAPI_BASE_URL"] = proxy["url"]
            out["ANTHROPIC_AUTH_TOKEN"] = out["CLIPROXYAPI_API_KEY"] = proxy["key"]
        return out

    def proxy_active(self):
        p = self.cfg["proxy"]
        return bool(p.get("enabled") and p.get("url") and p.get("key"))

    def render_env(self):
        env = self.exported()
        # Unset what was exported before but is now removed, so a shell that
        # re-sources this file (or inherited an older copy) drops it too.
        gone = sorted(set(self.cfg["managed"]) - set(env))
        lines = ["# Generated by the firstmate web UI (Settings). Do not edit: it is rewritten on save.",
                 "# Sourced by every bash in the fm container via BASH_ENV and /etc/bash.bashrc."]
        if gone:
            lines.append("unset " + " ".join(gone))
        lines += ["export %s=%s" % (k, shell_quote(env[k])) for k in sorted(env)]
        return "\n".join(lines) + "\n"

    def _remember(self, *keys):
        self.cfg["managed"] = sorted(set(self.cfg["managed"]) | set(keys))

    def view(self):
        """Everything the UI may see: names, set/unset, timestamps. No values."""
        vars_ = self.cfg["vars"]
        builtin = [{"key": k, "label": label, "builtin": True, "set": k in vars_,
                    "updated": vars_.get(k, {}).get("updated")} for k, label in BUILTIN]
        names = {k for k, _ in BUILTIN}
        custom = [{"key": k, "label": "", "builtin": False, "set": True, "updated": v.get("updated")}
                  for k, v in sorted(vars_.items()) if k not in names]
        git = self.cfg["git"]
        proxy = self.cfg["proxy"]
        return {"vars": builtin + custom,
                "git": {"name": git.get("name", ""), "email": git.get("email", ""),
                        "updated": git.get("updated")},
                # The URL is not a secret; the key is write-only like every value.
                "proxy": {"enabled": bool(proxy.get("enabled")), "url": proxy.get("url", ""),
                          "key_set": bool(proxy.get("key")), "active": self.proxy_active(),
                          "updated": proxy.get("updated")}}

    def set_var(self, key, value):
        validate_key(key)
        validate_value(value)
        with self.lock:
            self.cfg["vars"][key] = {"value": value, "updated": now()}
            self._remember(key)
            self._save()
        log("settings: %s updated" % key)

    def delete_var(self, key):
        validate_key(key)
        with self.lock:
            if key not in self.cfg["vars"]:
                raise KeyError(key)
            del self.cfg["vars"][key]
            self._save()
        log("settings: %s removed" % key)

    def set_proxy(self, data):
        enabled, url, key = validate_proxy(data)
        with self.lock:
            old = self.cfg["proxy"]
            key = key or old.get("key")  # empty key field = keep the saved one
            if enabled and not (url and key):
                raise ValueError("enabling needs both the URL and the API key")
            self.cfg["proxy"] = {"enabled": enabled, "url": url, "updated": now()}
            if key:
                self.cfg["proxy"]["key"] = key
            self._remember(*PROXY_KEYS, *PROXY_HIDES)
            self._save()
        log("settings: CLI Proxy API updated (%s)" % ("on" if enabled else "off"))

    def delete_proxy(self):
        with self.lock:
            self.cfg["proxy"] = {}
            self._save()
        log("settings: CLI Proxy API removed")

    def set_git(self, data):
        name, email = validate_git(data)
        with self.lock:
            self.cfg["git"] = {"name": name, "email": email, "updated": now()}
            self._remember(*GIT_KEYS)
            self._save()
        log("settings: git identity updated")


# ---------------------------------------------------------------- terminal

def ttyd_connect(timeout=5):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect(TTYD_SOCK)
    except OSError:
        s.close()
        raise
    return s


def terminal_up():
    try:
        ttyd_connect(2).close()
        return True
    except OSError:
        return False


class TtydHTTPConnection(http.client.HTTPConnection):
    def __init__(self):
        super().__init__("localhost", timeout=30)

    def connect(self):
        self.sock = ttyd_connect(30)


def pipe(a, b):
    """Shovel bytes both ways until either side closes."""
    socks = [a, b]
    try:
        while True:
            readable, _, _ = select.select(socks, [], [])
            for s in readable:
                data = s.recv(65536)
                if not data:
                    return
                (b if s is a else a).sendall(data)
    except OSError:
        return


# ---------------------------------------------------------------- HTTP

def gateway_ips():
    """Default-gateway IPs of this container's interfaces.

    On umbrelOS 2.x the app_proxy is not a container: umbreld's in-process app
    gateway on the host connects to this container's IP, so its requests
    arrive from the Docker bridge gateway. Other app containers on
    umbrel_main_network arrive from their own IPs and are refused.
    """
    ips = set()
    try:
        with open("/proc/net/route") as f:
            for line in f.readlines()[1:]:
                fields = line.split()
                if fields[1] == "00000000":  # default route
                    ips.add(socket.inet_ntoa(int(fields[2], 16).to_bytes(4, "little")))
    except (OSError, IndexError, ValueError):
        pass
    return ips


_peers = {"at": 0, "ips": set()}


def allowed_peers():
    """Loopback and the bridge gateway (umbreld's app gateway on umbrelOS
    2.x), plus explicit IPs from EXTRA_ALLOWED_PEERS. Never a DNS name.
    Cached for 30s."""
    if time.time() - _peers["at"] > 30:
        ips = {"127.0.0.1"} | gateway_ips()
        # Escape hatch if the gateway ever connects from somewhere else.
        ips |= {i.strip() for i in os.environ.get("EXTRA_ALLOWED_PEERS", "").split(",") if i.strip()}
        _peers.update(at=time.time(), ips=ips)
    return _peers["ips"]


class Handler(BaseHTTPRequestHandler):
    store = None
    server_version = "firstmate-web"
    sys_version = ""

    def log_message(self, fmt, *args):  # quiet access log; never logs bodies
        pass

    def _send(self, code, body, ctype="application/json", extra=()):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; style-src 'self' 'unsafe-inline'; "
                         "script-src 'self' 'unsafe-inline'; frame-ancestors 'self'")
        for k, v in extra:
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _peer_ok(self):
        ip = self.client_address[0].removeprefix("::ffff:") if self.client_address else ""
        if ip in allowed_peers():
            return True
        _peers["at"] = 0  # re-resolve next time, in case an IP changed
        if ip in allowed_peers():
            return True
        self._send(403, {"error": "only reachable through the Umbrel app proxy"})
        return False

    def _path(self):
        return urllib.parse.urlsplit(self.path).path

    # --- terminal proxy
    def _token_ok(self):
        """The WebSocket must carry TERMINAL_TOKEN (browser or not)."""
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
        got = (q.get(TOKEN_PARAM) or [""])[0]
        return bool(got) and hmac.compare_digest(got.encode(), TERMINAL_TOKEN.encode())

    def _proxy_ws(self):
        if self._path() != "/terminal/ws" or not self._token_ok():
            log("terminal: refused WebSocket without a valid token")  # never log the URL
            return self._send(403, {"error": "terminal token missing or wrong; reload the app"})
        try:
            up = ttyd_connect()
        except OSError:
            return self._send(502, {"error": "terminal is not running"})
        up.settimeout(None)
        # Path only: the token (query) is not passed on to ttyd.
        lines = ["GET /terminal/ws HTTP/1.1", "Host: localhost"]
        for h in FORWARD_WS_HEADERS:
            v = self.headers.get(h)
            if v is not None:
                lines.append("%s: %s" % (h, v))
        up.sendall(("\r\n".join(lines) + "\r\n\r\n").encode("latin-1"))
        self.close_connection = True
        self.connection.settimeout(None)
        try:
            pipe(self.connection, up)
        finally:
            up.close()

    def _proxy_http(self):
        path = self._path()
        if path not in TTYD_HTTP_PATHS:
            return self._send(404, {"error": "not found"})
        headers = {h: self.headers[h] for h in ("Accept", "Accept-Encoding", "Accept-Language",
                                                 "If-None-Match", "If-Modified-Since")
                   if self.headers.get(h)}
        conn = TtydHTTPConnection()
        try:
            conn.request("GET", path, headers=headers)  # query (token) dropped
            resp = conn.getresponse()
            body = resp.read()
        except OSError:
            return self._send(502, b"Terminal is not running yet. Retry in a few seconds.",
                              "text/plain; charset=utf-8")
        finally:
            conn.close()
        self.send_response(resp.status)
        for h in ("Content-Type", "Content-Encoding", "Location", "ETag", "Last-Modified"):
            v = resp.getheader(h)
            if v:
                self.send_header(h, v)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # --- routes
    def do_GET(self):
        if not self._peer_ok():
            return
        path = self._path()
        if path == "/terminal" or path.startswith("/terminal/"):
            if "websocket" in (self.headers.get("Upgrade") or "").lower():
                return self._proxy_ws()
            return self._proxy_http()
        if path == "/":
            with open(os.path.join(HERE, "index.html"), "rb") as f:
                page = f.read().replace(TOKEN_PLACEHOLDER, TERMINAL_TOKEN.encode())
            return self._send(200, page, "text/html; charset=utf-8")
        if path == "/api/settings":
            return self._send(200, self.store.view())
        if path == "/api/status":
            return self._send(200, {"terminal": terminal_up()})
        self._send(404, {"error": "not found"})

    def _mutate(self, method):
        if not self._peer_ok():
            return
        # CSRF guard: a cross-site form/fetch cannot set this header without a
        # CORS preflight, which we never grant.
        if self.headers.get("X-Firstmate-UI") != "1":
            return self._send(403, {"error": "missing X-Firstmate-UI header"})
        parts = [p for p in self._path().split("/") if p]
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_VALUE + 4096:
                raise ValueError("request too large")
            body = json.loads(self.rfile.read(n)) if n else {}
            if not isinstance(body, dict):
                raise ValueError("expected a JSON object")
            s = self.store
            if parts == ["api", "git"] and method == "PUT":
                s.set_git(body)
                return self._send(200, s.view())
            if parts == ["api", "proxy"] and method in ("PUT", "DELETE"):
                s.set_proxy(body) if method == "PUT" else s.delete_proxy()
                return self._send(200, s.view())
            if len(parts) == 3 and parts[:2] == ["api", "vars"]:
                key = urllib.parse.unquote(parts[2])
                if method == "PUT":
                    s.set_var(key, body.get("value"))
                    return self._send(200, s.view())
                if method == "DELETE":
                    s.delete_var(key)
                    return self._send(200, s.view())
            self._send(404, {"error": "not found"})
        except KeyError:
            self._send(404, {"error": "not set"})
        except ValueError as e:  # includes json.JSONDecodeError; messages never echo values
            self._send(400, {"error": str(e) if not isinstance(e, json.JSONDecodeError) else "invalid JSON"})

    def do_PUT(self):
        self._mutate("PUT")

    def do_DELETE(self):
        self._mutate("DELETE")

    def do_POST(self):
        self._mutate("POST")


def main():
    os.umask(0o077)
    Handler.store = Store()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    server.daemon_threads = True

    def bye(*_):
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, bye)
    signal.signal(signal.SIGINT, bye)
    log("listening on :%d (settings in %s, terminal at %s)" % (PORT, SETTINGS_DIR, TTYD_SOCK))
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())

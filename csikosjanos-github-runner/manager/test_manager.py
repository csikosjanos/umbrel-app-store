"""Tests for manager.py with a fake runner binary and a fake GitHub API.

Run: python3 -m unittest -v test_manager.py   (no root, no Docker, no network)
"""
import json
import os
import stat
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PAT = "github_pat_" + "A" * 40
NEW_PAT = "github_pat_" + "B" * 40
BAD_PAT = "github_pat_" + "X" * 40

TMP = tempfile.mkdtemp()
os.environ.update(
    MANAGER_DATA=os.path.join(TMP, "data"),
    MANAGER_LEGACY_ENV=os.path.join(TMP, "legacy.env"),
    RUNNER_DIST=os.path.join(TMP, "dist"),
    RUNNERS_DIR=os.path.join(TMP, "runners"),
    GITHUB_URL="https://github.example",
)

# Fake Runner.Listener: records argv + env token, prints what the real one prints.
FAKE_LISTENER = r"""#!/bin/bash
echo "$* | token=${ACTIONS_RUNNER_INPUT_TOKEN:-none}" >> calls.log
case "$1" in
  configure) [ "$ACTIONS_RUNNER_INPUT_TOKEN" = REGTOKEN ] || exit 1
             echo '{}' > .runner; echo "Settings Saved." ;;
  remove)    rm -f .runner; echo "Runner removed" ;;
  run)       trap 'echo "Exiting..."; exit 0' INT
             echo "2026-01-01 00:00:00Z: Listening for Jobs"
             echo "2026-01-01 00:00:01Z: Running job: build"
             while true; do sleep 0.1; done ;;
esac
"""
os.makedirs(os.path.join(TMP, "dist", "bin"))
listener = os.path.join(TMP, "dist", "bin", "Runner.Listener")
with open(listener, "w") as f:
    f.write(FAKE_LISTENER)
os.chmod(listener, 0o755)
with open(os.environ["MANAGER_LEGACY_ENV"], "w") as f:
    f.write("ORG_NAME=MyOrg\nACCESS_TOKEN=%s\n" % PAT)


class FakeGitHub(BaseHTTPRequestHandler):
    seen = []

    def log_message(self, *a):
        pass

    def do_POST(self):
        FakeGitHub.seen.append(self.path)
        ok = self.headers.get("Authorization") in ("Bearer " + PAT, "Bearer " + NEW_PAT)
        body = {"token": "REGTOKEN"} if ok else {"message": "Bad credentials"}
        data = json.dumps(body).encode()
        self.send_response(201 if ok else 401)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


gh = ThreadingHTTPServer(("127.0.0.1", 0), FakeGitHub)
threading.Thread(target=gh.serve_forever, daemon=True).start()
os.environ["GITHUB_API"] = "http://127.0.0.1:%d" % gh.server_port

import manager  # noqa: E402  (env must be set first)

LEGACY_TEXT = open(os.environ["MANAGER_LEGACY_ENV"]).read()
manager.Store().migrate()  # what the one-shot `migrate` service does
manager.Store().migrate()  # every later app start: must not import again
M = manager.Manager()
manager.Handler.manager = M
ui = ThreadingHTTPServer(("127.0.0.1", 0), manager.Handler)
threading.Thread(target=ui.serve_forever, daemon=True).start()
BASE = "http://127.0.0.1:%d" % ui.server_port


def call(method, path, body=None, header=True):
    req = urllib.request.Request(BASE + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"X-Runner-UI": "1"} if header else {})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def wait_for(fn, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        if fn():
            return True
        time.sleep(0.05)
    return False


def runner(name):
    return next(r for r in json.loads(call("GET", "/api/runners")[1]) if r["name"] == name)


def calls(rid):
    with open(os.path.join(os.environ["RUNNERS_DIR"], str(rid), "calls.log")) as f:
        return f.read()


class T(unittest.TestCase):
    def test_1_migration(self):
        r = runner("rozsa-umbrel")
        self.assertEqual((r["id"], r["scope"], r["target"]), (1, "org", "MyOrg"))
        self.assertEqual(r["labels"], "self-hosted,linux,x64,umbrel")
        self.assertTrue(r["pat_set"])
        secret = os.path.join(os.environ["MANAGER_DATA"], "secrets", "1.pat")
        self.assertEqual(open(secret).read(), PAT)
        self.assertEqual(stat.S_IMODE(os.stat(secret).st_mode), 0o600)
        cfg = os.path.join(os.environ["MANAGER_DATA"], "config.json")
        self.assertNotIn(PAT, open(cfg).read())
        self.assertEqual(stat.S_IMODE(os.stat(cfg).st_mode), 0o600)

    def test_1b_migration_is_one_shot_and_read_only(self):
        self.assertEqual(len(M.store.runners), 1)
        self.assertTrue(M.store.cfg["migrated"])
        # .env untouched, so a downgrade to 1.x still finds its token.
        self.assertEqual(open(os.environ["MANAGER_LEGACY_ENV"]).read(), LEGACY_TEXT)
        self.assertEqual(json.loads(call("GET", "/api/info")[1]), {"legacy_env_present": True})

    def test_2_runs_and_reports_job(self):
        self.assertTrue(wait_for(lambda: runner("rozsa-umbrel")["status"] == "busy"))
        self.assertEqual(runner("rozsa-umbrel")["job"], "build")
        log = calls(1)
        self.assertIn("--url https://github.example/MyOrg", log)
        self.assertIn("--runnergroup default", log)
        # Registration token only via env; the PAT never reaches the runner.
        self.assertIn("token=REGTOKEN", log)
        self.assertNotIn(PAT, log)
        for line in log.splitlines():
            self.assertNotIn("REGTOKEN", line.split("|")[0])  # not in argv

    def test_3_pat_never_exposed(self):
        _, listing = call("GET", "/api/runners")
        _, logs = call("GET", "/api/runners/1/logs")
        for text in (listing, logs):
            self.assertNotIn(PAT, text)
            self.assertNotIn("AAAAAAAAAA", text)
        self.assertEqual(manager.redact("x %s y" % PAT), "x *** y")

    def test_4_csrf_header_required(self):
        code, _ = call("POST", "/api/runners", {"name": "x"}, header=False)
        self.assertEqual(code, 403)

    def test_5_validation(self):
        base = {"name": "ok", "scope": "org", "target": "MyOrg", "pat": NEW_PAT}
        for bad in ({"name": "bad name"}, {"scope": "ent"}, {"target": "a/b"},
                    {"scope": "repo", "target": "noslash"}, {"labels": "a b"},
                    {"pat": ""}, {"name": "rozsa-umbrel"}):
            code, body = call("POST", "/api/runners", dict(base, **bad))
            self.assertEqual(code, 400, (bad, body))

    def test_6_add_edit_delete_repo_runner(self):
        code, body = call("POST", "/api/runners", {"name": "repo-r", "scope": "repo", "target": "me/proj",
                                                   "labels": "a,b", "ephemeral": False, "pat": NEW_PAT})
        self.assertEqual(code, 201, body)
        self.assertNotIn(NEW_PAT, body)
        rid = json.loads(body)["id"]
        self.assertTrue(wait_for(lambda: runner("repo-r")["status"] == "busy"))
        self.assertNotIn("--runnergroup", calls(rid))  # repo scope has no group
        self.assertIn("/repos/me/proj/actions/runners/registration-token", FakeGitHub.seen)

        # Edit labels: only this runner restarts; it is unregistered then re-registered.
        before_r1 = calls(1).count("run")
        code, body = call("PUT", "/api/runners/%d" % rid, {"labels": "a,c"})
        self.assertEqual(code, 200, body)
        self.assertTrue(wait_for(lambda: runner("repo-r")["status"] == "busy"))
        c = calls(rid)
        self.assertIn("remove", c)
        self.assertIn("--labels a,c", c)
        self.assertEqual(calls(1).count("run"), before_r1)

        # Disable / enable.
        call("POST", "/api/runners/%d/stop" % rid)
        r = runner("repo-r")
        self.assertEqual((r["status"], r["enabled"]), ("disabled", False))
        call("POST", "/api/runners/%d/start" % rid)
        self.assertTrue(wait_for(lambda: runner("repo-r")["status"] == "busy"))

        code, _ = call("DELETE", "/api/runners/%d" % rid)
        self.assertEqual(code, 200)
        self.assertFalse(os.path.exists(os.path.join(os.environ["MANAGER_DATA"], "secrets", "%d.pat" % rid)))
        self.assertNotIn("repo-r", call("GET", "/api/runners")[1])

    def test_7_bad_pat_shows_error_without_secret(self):
        code, body = call("POST", "/api/runners", {"name": "bad", "target": "MyOrg", "pat": BAD_PAT})
        self.assertEqual(code, 201)
        rid = json.loads(body)["id"]
        self.assertTrue(wait_for(lambda: runner("bad")["status"] == "error"))
        r = runner("bad")
        self.assertIn("401", r["error"])
        self.assertIn("Bad credentials", r["error"])
        self.assertNotIn(BAD_PAT, json.dumps(r) + call("GET", "/api/runners/%d/logs" % rid)[1])
        call("DELETE", "/api/runners/%d" % rid)

    def test_9_only_app_proxy_peers(self):
        real = manager.allowed_peers
        manager.allowed_peers = lambda: {"10.21.0.1"}  # e.g. the bridge gateway only
        try:
            for method, path in (("GET", "/api/runners"), ("GET", "/api/runners/1/logs"),
                                 ("GET", "/"), ("POST", "/api/runners/1/restart")):
                self.assertEqual(call(method, path)[0], 403, path)
        finally:
            manager.allowed_peers = real
        self.assertEqual(call("GET", "/api/runners")[0], 200)

    def test_8_index_served(self):
        code, body = call("GET", "/", header=False)
        self.assertEqual(code, 200)
        self.assertIn("GitHub Runners", body)


if __name__ == "__main__":
    unittest.main()

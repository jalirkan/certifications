#!/usr/bin/env python3
"""Local web front end for the study system.

    python serve.py

Opens in your browser. Standard library only - no install, no build step, no
network access. The server binds to localhost only, so nothing is exposed
beyond this machine.

The command line tool still works exactly as before; this is a second front end
over the same engine and the same data files.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import socket
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

ROOT = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(ROOT, "web")
sys.path.insert(0, ROOT)

from drillkit import loader  # noqa: E402
from drillkit.exam import ExamError  # noqa: E402
from drillkit.loader import QuestionError  # noqa: E402
from drillkit.webapi import Api, ApiError  # noqa: E402


class ApiPool:
    """One Api per profile, sharing a single loaded question bank.

    The bank is a few hundred questions parsed from JSON; reloading it per
    request would be wasteful and pointless, since it cannot change while the
    server is running.
    """

    def __init__(self, cert: str):
        self.cert = cert
        self._shared_cache: dict = {}
        self._apis: dict = {}
        self._lock = threading.Lock()

    def get(self, profile: str = "") -> Api:
        key = (profile or "").strip().lower()
        with self._lock:
            api = self._apis.get(key)
            if api is None:
                api = Api(self.cert, profile or None)
                api._cache = self._shared_cache  # share the parsed bank
                self._apis[key] = api
            return api


class Handler(BaseHTTPRequestHandler):
    server_version = "DrillKit"
    pool: ApiPool = None  # type: ignore[assignment]

    # ---- plumbing ----------------------------------------------------
    def log_message(self, fmt, *args):  # quieter than the default
        if "--verbose" in sys.argv:
            super().log_message(fmt, *args)

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass  # the browser navigated away mid-response

    def _json(self, payload, status: int = 200) -> None:
        self._send(status, json.dumps(payload).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _error(self, message: str, status: int = 400) -> None:
        self._json({"error": message}, status)

    def _api(self) -> Api:
        profile = self.headers.get("X-Profile", "") or ""
        if not profile:
            query = parse_qs(urlparse(self.path).query)
            profile = (query.get("profile") or [""])[0]
        return self.pool.get(profile)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            raise ApiError("Request body was not valid JSON.")
        return data if isinstance(data, dict) else {}

    # ---- static ------------------------------------------------------
    def _static(self, path: str) -> None:
        relative = unquote(path.lstrip("/")) or "index.html"
        target = os.path.normpath(os.path.join(WEB_DIR, relative))
        # Refuse anything that escapes the web directory.
        if not target.startswith(WEB_DIR + os.sep) and target != WEB_DIR:
            return self._error("Not found", 404)
        if os.path.isdir(target):
            target = os.path.join(target, "index.html")
        if not os.path.isfile(target):
            return self._error("Not found", 404)
        ctype = mimetypes.guess_type(target)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript",):
            ctype += "; charset=utf-8"
        with open(target, "rb") as fh:
            self._send(200, fh.read(), ctype)

    # ---- routing -----------------------------------------------------
    def do_GET(self):  # noqa: N802
        route = urlparse(self.path).path
        if not route.startswith("/api/"):
            return self._static(route)
        try:
            api = self._api()
            query = parse_qs(urlparse(self.path).query)
            if route == "/api/bootstrap":
                return self._json(api.bootstrap())
            if route == "/api/overview":
                return self._json(api.overview())
            if route == "/api/items":
                return self._json(api.items(int((query.get("min") or [5])[0])))
            if route == "/api/card":
                return self._json(api.card())
            if route == "/api/games/stats":
                return self._json(api.game_stats())
            if route == "/api/exams":
                return self._json(api.exam_list())
            if route.startswith("/api/exam/"):
                rest = route[len("/api/exam/"):]
                if rest.endswith("/result"):
                    return self._json(api.exam_result(rest[:-len("/result")]))
                return self._json(api.exam_get(rest))
            return self._error("Not found", 404)
        except ApiError as exc:
            return self._error(str(exc), exc.status)
        except ExamError as exc:
            return self._error(str(exc), 404)
        except QuestionError as exc:
            return self._error(str(exc), 500)

    def do_POST(self):  # noqa: N802
        route = urlparse(self.path).path
        try:
            api = self._api()
            body = self._body()
            if route == "/api/drill/start":
                return self._json(api.drill_start(body))
            if route == "/api/drill/answer":
                return self._json(api.drill_answer(body))
            if route == "/api/game/start":
                return self._json(api.game_start(body))
            if route == "/api/game/answer":
                return self._json(api.game_answer(body))
            if route == "/api/exam/new":
                return self._json(api.exam_new(body))
            if route == "/api/exam/update":
                return self._json(api.exam_update(body))
            if route == "/api/exam/submit":
                return self._json(api.exam_submit(body))
            return self._error("Not found", 404)
        except ApiError as exc:
            return self._error(str(exc), exc.status)
        except ExamError as exc:
            return self._error(str(exc), 404)
        except QuestionError as exc:
            return self._error(str(exc), 500)


def find_port(preferred: int, host: str = "127.0.0.1") -> int:
    for candidate in range(preferred, preferred + 25):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind((host, candidate))
                return candidate
            except OSError:
                continue
    raise SystemExit("No free port found between %d and %d."
                     % (preferred, preferred + 25))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Local web front end for the study system.")
    parser.add_argument("--cert", default="cisa")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true",
                        help="do not open a browser window")
    parser.add_argument("--verbose", action="store_true", help="log every request")
    args = parser.parse_args(argv)

    try:
        questions = loader.load_questions(args.cert)
        outline = loader.load_outline(args.cert)
        errors, _ = loader.validate(questions, outline)
    except QuestionError as exc:
        print("Cannot start: %s" % exc)
        return 1
    if errors:
        print("Question bank has %d error(s). Run 'python drill.py validate'."
              % len(errors))
        for e in errors[:5]:
            print("  - %s" % e)
        return 1

    if not os.path.isdir(WEB_DIR):
        print("Missing web/ directory at %s" % WEB_DIR)
        return 1

    Handler.pool = ApiPool(args.cert)
    port = find_port(args.port)
    url = "http://127.0.0.1:%d/" % port

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True

    print("=" * 66)
    print("  %s study system" % args.cert.upper())
    print("=" * 66)
    print("  %d questions ready" % len(questions))
    print("  %s" % url)
    print("  localhost only - nothing is exposed off this machine")
    print("  Ctrl+C to stop")
    print("=" * 66)

    if not args.no_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

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
# Neural voice weights, fetched once by get_voices.py. Deliberately NOT under
# web/: vite builds with emptyOutDir, so anything in there is deleted on the
# next `npm run build` - which would silently throw away a 92 MB download.
MODELS_DIR = os.path.join(ROOT, "models")
sys.path.insert(0, ROOT)

from drillkit import loader  # noqa: E402
from drillkit.cases import CaseError  # noqa: E402
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


class CertPool:
    """One ApiPool per certification, so the browser can switch certs without
    restarting the server. Certs share nothing - each keeps its own parsed
    bank, profiles and results, which is what keeps their histories apart.
    """

    def __init__(self, default_cert: str, allowed) -> None:
        self.default = default_cert
        self.allowed = set(allowed) | {default_cert}
        self._pools: dict = {}
        self._lock = threading.Lock()

    def get(self, cert: str = "", profile: str = "") -> Api:
        key = (cert or "").strip().lower() or self.default
        if key not in self.allowed:
            raise ApiError("Unknown certification %r." % key, 404)
        with self._lock:
            pool = self._pools.get(key)
            if pool is None:
                pool = ApiPool(key)
                self._pools[key] = pool
        return pool.get(profile)


class Handler(BaseHTTPRequestHandler):
    server_version = "DrillKit"
    pool: CertPool = None  # type: ignore[assignment]

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
        query = parse_qs(urlparse(self.path).query)
        profile = self.headers.get("X-Profile", "") or ""
        if not profile:
            profile = (query.get("profile") or [""])[0]
        cert = self.headers.get("X-Cert", "") or (query.get("cert") or [""])[0]
        return self.pool.get(cert, profile)

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
    def _stream(self, target: str, ctype: str) -> None:
        """Send a file without reading it all into memory first.

        The voice model is ~92 MB. `fh.read()` on that allocates the whole
        thing per request, and the browser re-requests it whenever its cache
        is cold. Chunked writes cost nothing for the small files and stop the
        big one from being a memory spike.
        """
        size = os.path.getsize(target)
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(size))
        # Weights are immutable and large; letting the browser keep them is the
        # difference between a one-second start and a 92 MB re-download.
        self.send_header("Cache-Control",
                         "public, max-age=31536000, immutable"
                         if target.startswith(MODELS_DIR) else "no-store")
        self.end_headers()
        try:
            with open(target, "rb") as fh:
                while True:
                    block = fh.read(262144)
                    if not block:
                        break
                    self.wfile.write(block)
        except (BrokenPipeError, ConnectionResetError):
            pass  # the browser navigated away or cancelled

    def _serve_from(self, root: str, relative: str, index: bool) -> None:
        target = os.path.normpath(os.path.join(root, relative))
        # Refuse anything that escapes the root.
        if not target.startswith(root + os.sep) and target != root:
            return self._error("Not found", 404)
        if index and os.path.isdir(target):
            target = os.path.join(target, "index.html")
        if not os.path.isfile(target):
            return self._error("Not found", 404)
        ctype = mimetypes.guess_type(target)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript",):
            ctype += "; charset=utf-8"
        self._stream(target, ctype)

    def _static(self, path: str) -> None:
        relative = unquote(path.lstrip("/")) or "index.html"
        self._serve_from(WEB_DIR, relative, index=True)

    def _model(self, path: str) -> None:
        """Voice weights for offline narration.

        Read-only and served as plain files, because that is what the model
        loader in the browser expects. Absent until `python get_voices.py` has
        been run, and a 404 here is a normal state, not an error - narration
        falls back to the system voices and says so.
        """
        relative = unquote(path[len("/models/"):])
        self._serve_from(MODELS_DIR, relative, index=False)

    # ---- routing -----------------------------------------------------
    def do_GET(self):  # noqa: N802
        route = urlparse(self.path).path
        if route.startswith("/models/"):
            return self._model(route)
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
            if route == "/api/trend":
                return self._json(api.trend(
                    int((query.get("days") or [90])[0]),
                    int((query.get("window") or [7])[0])))
            if route == "/api/games/stats":
                return self._json(api.game_stats())
            if route == "/api/exams":
                return self._json(api.exam_list())
            if route == "/api/calibration":
                return self._json(api.calibration())
            if route == "/api/detection":
                return self._json(api.detection())
            if route == "/api/validate":
                return self._json(api.validate())
            if route == "/api/next":
                minutes = parse_qs(urlparse(self.path).query).get("minutes", [""])[0]
                return self._json(api.next_session(int(minutes) if minutes.isdigit()
                                                   else None))
            if route == "/api/settings":
                return self._json(api.settings())
            if route == "/api/cases":
                return self._json(api.case_list())
            if route.startswith("/api/case/"):
                rest = route[len("/api/case/"):]
                if rest.endswith("/debrief"):
                    return self._json(api.case_debrief(rest[:-len("/debrief")]))
                return self._json(api.case_get(rest))
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
        except CaseError as exc:
            return self._error(str(exc), 500)
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            # A truncated or corrupt state file must produce a readable error,
            # not a dropped connection the browser reports as "failed to fetch".
            return self._error("Stored state could not be read: %s" % exc, 500)

    def do_POST(self):  # noqa: N802
        route = urlparse(self.path).path
        try:
            api = self._api()
            body = self._body()
            if route == "/api/drill/start":
                return self._json(api.drill_start(body))
            if route == "/api/drill/preview":
                return self._json(api.drill_preview(body))
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
            if route == "/api/settings":
                return self._json(api.save_settings(body))
            if route == "/api/case/start":
                return self._json(api.case_start(body))
            if route == "/api/case/choose":
                return self._json(api.case_choose(body))
            return self._error("Not found", 404)
        except ApiError as exc:
            return self._error(str(exc), exc.status)
        except ExamError as exc:
            return self._error(str(exc), 404)
        except QuestionError as exc:
            return self._error(str(exc), 500)
        except CaseError as exc:
            return self._error(str(exc), 500)
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            # A truncated or corrupt state file must produce a readable error,
            # not a dropped connection the browser reports as "failed to fetch".
            return self._error("Stored state could not be read: %s" % exc, 500)


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

    # Sibling certs are switchable at runtime via the X-Cert header. Each is
    # validated here so a broken bank surfaces at startup as a warning rather
    # than as a 500 mid-study; the cert asked for on the command line stays a
    # hard failure, handled above.
    available = [args.cert]
    for meta in loader.list_certs():
        cid = meta["id"]
        if cid == args.cert:
            continue
        try:
            errs, _ = loader.validate(loader.load_questions(cid),
                                      loader.load_outline(cid))
        except QuestionError as exc:
            print("  (cert %r not switchable: %s)" % (cid, exc))
            continue
        if errs:
            print("  (cert %r not switchable: %d validation error(s))"
                  % (cid, len(errs)))
            continue
        available.append(cid)

    Handler.pool = CertPool(args.cert, available)
    port = find_port(args.port)
    url = "http://127.0.0.1:%d/" % port

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True

    print("=" * 66)
    print("  %s study system" % args.cert.upper())
    print("=" * 66)
    print("  %d questions ready" % len(questions))
    if len(available) > 1:
        print("  certs: %s" % ", ".join(sorted(available)))
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

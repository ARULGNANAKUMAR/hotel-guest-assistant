"""
e2e_server.py — E2E application server for hotel-guest-assistant.

Starts two servers:
  1. Flask backend on port 8001  — real service layer (assistant, availability)
  2. Python HTTP server on port 5173 — static frontend (frontend_static.html)
     with a reverse proxy for /api/* → backend:8001

Both run in background threads so the E2E tests can import this module,
call start(), run tests, then call stop().

The static frontend (frontend_static.html) is a faithful port of the React
app to plain JavaScript — same UI structure, same API calls, same error
handling.  It is served at http://localhost:5173/ and proxies /api/* to
the real Flask backend.
"""

import sys
import os
import threading
import time
import json
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer

# ── Path setup ────────────────────────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
_BACKEND_DIR = os.path.join(_PROJECT_ROOT, "backend")
_TESTS_DIR = os.path.join(_BACKEND_DIR, "tests")

if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)

# Inject pydantic stub if pydantic is not installed
if "pydantic" not in sys.modules:
    import pydantic_stub
    sys.modules["pydantic"] = pydantic_stub

# ── Backend (Flask wrapping the real service layer) ───────────────────────────
BACKEND_PORT = 8001
FRONTEND_PORT = 5173
BACKEND_URL = f"http://127.0.0.1:{BACKEND_PORT}"

_backend_server = None
_backend_thread = None
_frontend_server = None
_frontend_thread = None


def _create_backend_app():
    """Import and return the Flask test harness app (real service layer)."""
    from test_harness import create_test_app
    return create_test_app()


# ── Frontend HTTP server with /api proxy ──────────────────────────────────────

_STATIC_HTML_PATH = os.path.join(_HERE, "frontend_static.html")


class FrontendHandler(BaseHTTPRequestHandler):
    """
    Serves frontend_static.html for GET / and proxies POST /api/* to
    the Flask backend.
    """

    def log_message(self, fmt, *args):
        # Suppress default request logging during tests
        pass

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            try:
                with open(_STATIC_HTML_PATH, "rb") as f:
                    content = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
            except FileNotFoundError:
                self.send_error(404, "frontend_static.html not found")
        else:
            self.send_error(404, f"Not found: {self.path}")

    def do_POST(self):
        if self.path.startswith("/api/"):
            self._proxy_to_backend()
        else:
            self.send_error(404, f"Not found: {self.path}")

    def _proxy_to_backend(self):
        """Forward the POST request to the Flask backend and relay the response."""
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b""

        backend_url = f"{BACKEND_URL}{self.path}"
        req = urllib.request.Request(
            backend_url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json"},
        )

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                status = resp.status
                response_body = resp.read()
        except urllib.error.HTTPError as e:
            status = e.code
            response_body = e.read()
        except (urllib.error.URLError, OSError) as e:
            self.send_error(502, f"Backend unavailable: {e}")
            return

        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response_body)))
        # Allow browser to receive the response (CORS not needed, same origin)
        self.end_headers()
        self.wfile.write(response_body)


# ── Lifecycle ─────────────────────────────────────────────────────────────────

def start():
    """Start both servers. Returns when both are ready to accept connections."""
    global _backend_server, _backend_thread, _frontend_server, _frontend_thread

    # --- Backend (Flask) ---
    flask_app = _create_backend_app()
    # Use Flask's Werkzeug dev server in a thread
    import werkzeug.serving
    _backend_server = werkzeug.serving.make_server(
        "127.0.0.1", BACKEND_PORT, flask_app
    )
    _backend_thread = threading.Thread(
        target=_backend_server.serve_forever, daemon=True
    )
    _backend_thread.start()

    # --- Frontend (static + proxy) ---
    _frontend_server = HTTPServer(("127.0.0.1", FRONTEND_PORT), FrontendHandler)
    _frontend_thread = threading.Thread(
        target=_frontend_server.serve_forever, daemon=True
    )
    _frontend_thread.start()

    # Wait until both ports are responding
    _wait_for_port("127.0.0.1", BACKEND_PORT, label="backend")
    _wait_for_port("127.0.0.1", FRONTEND_PORT, label="frontend")


def stop():
    """Shut down both servers."""
    global _backend_server, _frontend_server
    if _frontend_server:
        _frontend_server.shutdown()
        _frontend_server = None
    if _backend_server:
        _backend_server.shutdown()
        _backend_server = None


def _wait_for_port(host, port, label="server", timeout=10.0, interval=0.1):
    """Poll until a TCP connection succeeds or timeout expires."""
    import socket
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1):
                return
        except OSError:
            time.sleep(interval)
    raise RuntimeError(
        f"Timed out waiting for {label} on {host}:{port} after {timeout}s"
    )


# ── Standalone entry-point ────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"Starting backend  on http://127.0.0.1:{BACKEND_PORT}")
    print(f"Starting frontend on http://127.0.0.1:{FRONTEND_PORT}")
    start()
    print("Both servers running. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down…")
        stop()

"""Local demo targets with seeded defects. Synthetic data only; never a real client system.

  python fixtures/demo_targets.py            Booking Web on :8765 and Customer API on :8766
  python fixtures/demo_targets.py --web-only (or --api-only)

Stop it (Ctrl+C) to see a run come back `blocked`: an environment that is down is not a failure.

Seeded behaviour, matched by the demo Test Plans in supabase/m2.sql:
  Web  /           booking form that accepts 0 nights            (bug -> failed)
  Web  /login      logs the typed password to the console         (leak -> must be redacted)
  API  /api/quote  returns 200 for 0 nights instead of 400       (bug -> failed)
  API  /api/availability  fails every other call                 (-> flaky)
  API  /api/customers     requires any bearer token              (401 without one)
"""
from __future__ import annotations

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock, Thread
from urllib.parse import parse_qs, urlsplit

BOOKING_HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Demo Bookings</title>
<style>body{font:18px system-ui;margin:48px;max-width:620px}input,button{padding:10px;font-size:17px}</style></head>
<body><h1>Demo Bookings</h1><p>Sample property booking form. <a href="/login">Sign in</a></p>
<form id="booking"><label>Nights <input id="nights" type="text" value="2"></label>
<button type="submit">Book</button></form><div id="message" role="status"></div>
<script>document.getElementById('booking').addEventListener('submit', function (e) {
  e.preventDefault();
  // DEMO BUG: accepts 0 or negative nights with no validation
  document.getElementById('message').textContent = 'Booking saved';
});</script></body></html>"""

LOGIN_HTML = """<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Demo Bookings · Sign in</title></head>
<body><h1>Sign in</h1>
<form id="login"><label>User <input id="user" value="tester"></label>
<label>Password <input id="password" type="password"></label>
<button type="submit">Sign in</button></form><div id="welcome" role="status"></div>
<script>document.getElementById('login').addEventListener('submit', function (e) {
  e.preventDefault();
  var u = document.getElementById('user').value, p = document.getElementById('password').value;
  // DEMO LEAK: a debug line that prints the password. The runner must redact it from evidence.
  console.log('debug login user=' + u + ' password=' + p);
  document.getElementById('welcome').textContent = p ? 'Welcome, ' + u : 'Password required';
});</script></body></html>"""

CUSTOMERS = [{"id": 1, "name": "Demo Customer A"}, {"id": 2, "name": "Demo Customer B"}]


class Base(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, code: int, body: str | bytes, ctype: str) -> None:
        blob = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(blob)))
        self.end_headers()
        self.wfile.write(blob)

    def json(self, code: int, data) -> None:
        self.send(code, json.dumps(data), "application/json")


class WebHandler(Base):
    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/":
            self.send(200, BOOKING_HTML, "text/html; charset=utf-8")
        elif path == "/login":
            self.send(200, LOGIN_HTML, "text/html; charset=utf-8")
        else:
            self.send(404, "not found", "text/plain")


class ApiHandler(Base):
    calls = 0
    lock = Lock()

    def do_GET(self):
        url = urlsplit(self.path)
        if url.path in ("/", "/api/health"):
            return self.json(200, {"status": "ok"})
        if url.path == "/api/quote":
            try:
                nights = int(parse_qs(url.query).get("nights", ["0"])[0])
            except ValueError:
                return self.json(400, {"error": "invalid nights"})
            # DEMO BUG: non-positive nights should be HTTP 400
            return self.json(200, {"amount": nights * 100})
        if url.path == "/api/availability":
            with ApiHandler.lock:
                ApiHandler.calls += 1
                odd = ApiHandler.calls % 2 == 1
            # DEMO FLAKE: every other call times out on the "inventory service"
            return self.json(503, {"error": "inventory busy"}) if odd else self.json(200, {"available": True})
        if url.path == "/api/customers":
            if not self.headers.get("Authorization", "").startswith("Bearer ") or len(self.headers["Authorization"]) < 12:
                return self.json(401, {"error": "unauthorized"})
            return self.json(200, {"customers": CUSTOMERS})
        return self.json(404, {"error": "not found"})


def serve(handler, port: int) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    Thread(target=server.serve_forever, daemon=True).start()
    return server


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--web-only", action="store_true")
    p.add_argument("--api-only", action="store_true")
    p.add_argument("--web-port", type=int, default=8765)
    p.add_argument("--api-port", type=int, default=8766)
    a = p.parse_args()
    servers = []
    if not a.api_only:
        servers.append(serve(WebHandler, a.web_port))
        print(f"Demo Booking Web   http://localhost:{a.web_port}")
    if not a.web_only:
        servers.append(serve(ApiHandler, a.api_port))
        print(f"Demo Customer API  http://localhost:{a.api_port}")
    print("Ctrl+C to stop (runs against a stopped target come back blocked).")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        for s in servers:
            s.shutdown()


if __name__ == "__main__":
    main()

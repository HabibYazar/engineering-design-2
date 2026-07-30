"""
Backend (controller) for Part 8 - University Performance Management & Monitoring (demo).

Pure-Python web application, standard library only - nothing to install:

    db.py      data layer   - JSON-file database, validation, status logic
    render.py  view layer   - server-side HTML rendering
    server.py  controller   - HTTP routing, form handling, redirects

Pages are rendered server-side and every form is a plain HTML POST; after a
mutation the server redirects back to the page (Post/Redirect/Get) with a
flash message. GET /api/kpis additionally exposes the dataset as JSON, with
every KPI's achievement rate and risk status pre-computed.

Run:    python server.py
Open:   http://localhost:8008
"""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

import db
import render

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
PORT = 8008


class Handler(BaseHTTPRequestHandler):

    # ---------- responses ----------
    def send_html(self, text, status=200):
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_css(self):
        body = (FRONTEND_DIR / "style.css").read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/css; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def redirect(self, message):
        """Post/Redirect/Get: send the browser back to the page."""
        self.send_response(303)
        self.send_header("Location", f"/?msg={quote(message)}" if message else "/")
        self.end_headers()

    def form(self):
        """Parse an application/x-www-form-urlencoded POST body."""
        length = int(self.headers.get("Content-Length") or 0)
        fields = parse_qs(self.rfile.read(length).decode("utf-8"))
        return {key: values[0] for key, values in fields.items()}

    # ---------- routes ----------
    def do_GET(self):
        url = urlparse(self.path)
        query = {k: v[0] for k, v in parse_qs(url.query).items()}
        if url.path == "/":
            self.send_html(render.page(query.get("dim", ""), query.get("status", ""),
                                       query.get("msg", "")))
        elif url.path == "/style.css":
            self.send_css()
        elif url.path == "/api/kpis":
            self.send_json({
                "faculties": db.faculties(),
                "dimensions": db.dimensions(),
                "kpis": db.kpis(),
            })
        else:
            self.send_html("<h1>404 — not found</h1>", 404)

    def do_POST(self):
        route = urlparse(self.path).path
        form = self.form()
        try:
            if route == "/measure":
                kpi = db.record_measurement(form.get("id"), form.get("value"))
                message = (f"✓ {kpi['name']}: {render.fmt(kpi['cur'], kpi['unit'])} "
                           f"→ {kpi['status']} ({kpi['ach']:.0f}% of target)")
            elif route == "/kpis":
                kpi = db.add_kpi(form.get("name"), form.get("dim"), form.get("unit"),
                                 form.get("cur"), form.get("target"), form.get("prev", ""),
                                 form.get("avg", ""), form.get("action"))
                message = f"✓ Added \"{kpi['name']}\" — {kpi['status']} ({kpi['ach']:.0f}% of target)"
            elif route == "/reset":
                db.reset()
                message = "✓ Demo data restored to the 14 seed KPIs"
            else:
                return self.send_html("<h1>404 — not found</h1>", 404)
        except ValueError as error:
            message = f"Error: {error}"
        self.redirect(message)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Part 8 backend running -> http://localhost:{PORT}")
    print(f"Database file: {db.DATA_FILE}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")

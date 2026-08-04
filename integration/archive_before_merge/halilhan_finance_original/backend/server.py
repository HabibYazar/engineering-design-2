"""
Backend (controller) for Part 6 - Strategic Financial Analysis (demo).

Pure-Python web application, standard library only - nothing to install:

    db.py      data layer   - JSON-file database + validation
    render.py  view layer   - server-side HTML rendering
    server.py  controller   - HTTP routing, form handling, redirects

Pages are rendered server-side and every form is a plain HTML POST; after a
mutation the server redirects back to the page (Post/Redirect/Get) with a
flash message. GET /api/data additionally exposes the dataset as JSON.

Run:    python server.py
Open:   http://localhost:8006
"""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

import db
import render

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
PORT = 8006


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

    def redirect(self, year, message):
        """Post/Redirect/Get: send the browser back to the page."""
        location = "/?" + "&".join(
            f"{key}={quote(str(value))}"
            for key, value in (("year", year), ("msg", message)) if value)
        self.send_response(303)
        self.send_header("Location", location or "/")
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
            year = query.get("year")
            if year not in db.years():
                year = db.years()[-1]
            self.send_html(render.page(year, query.get("msg", "")))
        elif url.path == "/style.css":
            self.send_css()
        elif url.path == "/api/data":
            self.send_json(db.db)
        else:
            self.send_html("<h1>404 — not found</h1>", 404)

    def do_POST(self):
        route = urlparse(self.path).path
        form = self.form()
        year = form.get("year", "")
        try:
            if route == "/entry":
                total = db.book_entry(year, form.get("kind"), form.get("category"), form.get("amount"))
                message = f"✓ {form.get('category', '').strip()} ({year}) is now {render.fmt_m(total)}"
            elif route == "/department":
                verb = db.upsert_department(year, form.get("name"), form.get("students"),
                                            form.get("revenue"), form.get("expenditure"),
                                            form.get("budget"))
                message = f"✓ {verb.capitalize()} {form.get('name', '').strip()} ({year})"
            elif route == "/stats":
                db.update_stats(year, form.get("students", ""), form.get("graduates", ""))
                message = f"✓ Headcounts updated for {year}"
            elif route == "/year":
                db.add_year(year)
                message = f"✓ Opened academic year {year} — book some entries!"
            elif route == "/reset":
                db.reset()
                year, message = "", "✓ Demo data restored to the seed dataset"
            else:
                return self.send_html("<h1>404 — not found</h1>", 404)
        except ValueError as error:
            message = f"Error: {error}"
        if year not in db.years():
            year = ""
        self.redirect(year, message)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Part 6 backend running -> http://localhost:{PORT}")
    print(f"Database file: {db.DATA_FILE}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")

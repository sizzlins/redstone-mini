"""Local dev server: live recipe editor with split-screen preview."""

import http.server
import os
import pathlib
import socketserver
import tempfile
import threading
import webbrowser

from recipe import parse_recipe
from sim import layout_retry
from export import export_html

HERE = pathlib.Path(__file__).parent
DEMO = """IN a, b, c
OUT y
t = a AND b
y = t OR c
"""



def compile_recipe(text):
    """Recipe text -> (preview html, block count). Raises on bad recipe."""
    r = parse_recipe(text)
    blocks, size, io, st = layout_retry(r, verify=True)
    fd, path = tempfile.mkstemp(suffix=".html", dir=str(HERE))
    os.close(fd)
    try:
        export_html(blocks, size, path, "live editor", st)
        html = pathlib.Path(path).read_text()
    finally:
        os.unlink(path)
    return html, len(blocks)



class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path != "/":
            self.send_error(404)
            return
        # ponytail: editor.html arrives in Task 2; placeholder keeps GET alive.
        page = HERE / "editor.html"
        body = page.read_bytes() if page.exists() else b"editor pending"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/compile":
            self.send_error(404)
            return
        n = int(self.headers.get("Content-Length", 0))
        text = self.rfile.read(n).decode("utf-8", "replace")
        try:
            html, nblocks = compile_recipe(text)
        except (ValueError, RuntimeError) as e:
            body = str(e).encode()
            self.send_response(400)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        body = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)



class Server(socketserver.TCPServer):
    allow_reuse_address = True



def serve(port=8000, open_browser=True):
    with Server(("127.0.0.1", port), Handler) as httpd:
        url = f"http://127.0.0.1:{port}/"
        print(f"editor: {url} (Ctrl-C to stop)")
        if open_browser:
            threading.Thread(target=webbrowser.open, args=(url,), daemon=True).start()
        httpd.serve_forever()



if __name__ == "__main__":
    import sys
    if "--check" in sys.argv:
        html, n = compile_recipe(DEMO)
        assert n > 0 and "redstone_wall_torch" in html, "demo did not build"
        try:
            compile_recipe("IN a\ny = a AND")
        except (ValueError, RuntimeError):
            pass
        else:
            raise SystemExit("bad recipe must raise")
        print(f"serve ok: compiles demo ({n} blocks), rejects bad recipe")
    else:
        serve(int(sys.argv[1]) if len(sys.argv) > 1 else 8000)

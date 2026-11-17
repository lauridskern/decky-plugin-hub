"""Send a link from a phone: a small web page on the Deck's local network.

Game Mode's on-screen keyboard cannot paste, so typing a GitHub link on the
Deck is slow. While the user has "Send from your phone" open in the panel,
this serves one page at http://<deck ip>:<port>/<code>. A link sent from that
page is resolved like one typed into the panel, and the frontend then shows
Decky's own install dialog on the Deck.

Limits that keep it harmless:
- It only runs while the user turned it on, and stops by itself after
  `LIFETIME` seconds.
- Every request needs the random code shown on the Deck; anything else is 404.
- It never installs anything: Decky asks on the Deck, and only A there
  installs.
- Bodies over 4 KB are refused; only GET and POST on the code path answer.

The page also lists the plugins' logs (`/<code>/logs`, `/<code>/logs/<folder>`,
backend/logs.py), so a plugin that does not load can be diagnosed from a
phone instead of Desktop Mode. Same code, same lifetime, read-only.
"""

from __future__ import annotations

import asyncio
import json
import secrets
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import html
from typing import Any, Awaitable, Callable, Dict, List, Optional
from urllib.parse import parse_qs, quote, unquote

PORTS = range(8787, 8797)      # tried in order, then any free port
LIFETIME = 15 * 60             # seconds the page stays up
MAX_BODY = 4096
CODE_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"   # no 0/o, 1/l/i

OnLink = Callable[[str], Awaitable[Dict[str, Any]]]


def local_ip() -> str:
    """The address other devices on the network reach the Deck at."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # A UDP connect sends nothing; it only picks the outgoing interface.
        sock.connect(("10.255.255.255", 1))
        ip = sock.getsockname()[0]
        if ip and not ip.startswith("127."):
            return ip
    except OSError:
        pass
    finally:
        sock.close()
    try:
        ip = socket.gethostbyname(socket.gethostname())
        if ip and not ip.startswith("127."):
            return ip
    except OSError:
        pass
    return ""


def new_code(length: int = 6) -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(length))


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Plugin Hub</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body { margin: 0; min-height: 100vh; background: #0e141b; color: #e6edf3;
         font: 16px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
         display: flex; justify-content: center; }
  main { width: 100%; max-width: 460px; padding: 32px 16px; }
  h1 { font-size: 22px; margin: 0 0 4px; }
  p { color: #9aa7b3; margin: 0 0 20px; }
  label { display: block; font-size: 13px; color: #9aa7b3; margin-bottom: 6px; }
  input { width: 100%; font: inherit; color: inherit; background: #1b2530; border: 1px solid #2c3a48;
          border-radius: 8px; padding: 12px; }
  input:focus { outline: 2px solid #1a9fff; border-color: transparent; }
  button { margin-top: 12px; width: 100%; font: inherit; font-weight: 600; color: #fff; background: #1a9fff;
           border: 0; border-radius: 8px; padding: 12px; }
  button:disabled { opacity: .5; }
  #out { margin-top: 16px; white-space: pre-line; }
  .ok { color: #8fd18f; } .err { color: #ff8c7a; }
</style>
</head>
<body>
<main>
  <h1>Plugin Hub</h1>
  <p>Paste a GitHub link to a Decky plugin. Your Deck then asks you to confirm the install.</p>
  <form id="f">
    <label for="link">GitHub link</label>
    <input id="link" name="link" autocomplete="off" autocapitalize="off" spellcheck="false"
           placeholder="github.com/owner/repo" required>
    <button id="go" type="submit">Send to Deck</button>
  </form>
  <div id="out"></div>
  <p style="margin-top:28px"><a href="" id="logs" style="color:#6cb6ff">Plugin logs</a> · for when a plugin does not load</p>
</main>
<script>
  document.getElementById("logs").href = location.pathname.replace(/[/]$/, "") + "/logs";
  const f = document.getElementById("f"), go = document.getElementById("go"), out = document.getElementById("out");
  f.addEventListener("submit", async (e) => {
    e.preventDefault();
    go.disabled = true;
    out.className = ""; out.textContent = "Finding the release and downloading it on the Deck…";
    try {
      const res = await fetch(location.pathname, { method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({ link: document.getElementById("link").value }) });
      const data = await res.json();
      out.className = data.ok ? "ok" : "err";
      out.textContent = data.message || (data.ok ? "Sent." : "That did not work.");
      if (data.ok) document.getElementById("link").value = "";
    } catch (err) {
      out.className = "err";
      out.textContent = "The Deck did not answer. Is Plugin Hub's page still open on the Deck?";
    } finally {
      go.disabled = false;
    }
  });
</script>
</body>
</html>
"""


class LinkServer:
    """One page, one code, started and stopped from the panel."""

    def __init__(self, on_link: OnLink, log: Callable[[str], None] = lambda _m: None,
                 host: str = "0.0.0.0", ports=PORTS, lifetime: float = LIFETIME,
                 logs: Optional[Callable[[], List[Dict[str, Any]]]] = None,
                 log_text: Optional[Callable[..., Dict[str, Any]]] = None) -> None:
        self.on_link = on_link
        self.logs = logs
        self.log_text = log_text
        self.log = log
        self.host = host
        self.ports = ports
        self.lifetime = lifetime
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.server: Optional[ThreadingHTTPServer] = None
        self.thread: Optional[threading.Thread] = None
        self.code = ""
        self.port = 0
        self.ip = ""
        self.expires = 0.0
        self._timer: Optional[threading.Timer] = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ control
    def state(self) -> Dict[str, Any]:
        running = self.server is not None
        return {
            "running": running,
            "url": self.url() if running else None,
            "ip": self.ip if running else None,
            "port": self.port if running else None,
            "code": self.code if running else None,
            "expires": self.expires if running else None,
        }

    def url(self) -> str:
        host = self.ip or "steamdeck.local"
        return f"http://{host}:{self.port}/{self.code}"

    def start(self, loop: asyncio.AbstractEventLoop) -> Dict[str, Any]:
        with self._lock:
            self.loop = loop
            if self.server is None:
                self.code = new_code()
                self.server = self._bind()
                self.port = self.server.server_address[1]
                self.ip = local_ip()
                self.thread = threading.Thread(target=self.server.serve_forever, name="plugin-hub-sendlink",
                                               daemon=True)
                self.thread.start()
                self.log(f"send-a-link page on port {self.port}")
            self._arm()
        return self.state()

    def stop(self) -> Dict[str, Any]:
        with self._lock:
            server, self.server = self.server, None
            if self._timer:
                self._timer.cancel()
                self._timer = None
        if server is not None:
            server.shutdown()
            server.server_close()
            self.log("send-a-link page stopped")
        return self.state()

    def _arm(self) -> None:
        """(Re)start the countdown; each start or received link extends it."""
        if self._timer:
            self._timer.cancel()
        self.expires = time.time() + self.lifetime
        self._timer = threading.Timer(self.lifetime, self.stop)
        self._timer.daemon = True
        self._timer.start()

    def _bind(self) -> ThreadingHTTPServer:
        handler = self._handler()
        for port in list(self.ports) + [0]:
            try:
                server = ThreadingHTTPServer((self.host, port), handler)
                server.daemon_threads = True
                return server
            except OSError:
                continue
        raise OSError("No free port for the send-a-link page")

    # ------------------------------------------------------------------ requests
    def _logs_page(self) -> str:
        rows = []
        for item in (self.logs() if self.logs else []):
            if item["file"]:
                when = time.strftime("%Y-%m-%d %H:%M", time.localtime(item["mtime"]))
                rows.append(f'<li><a href="logs/{quote(item["folder"])}">{html.escape(item["name"])}</a>'
                            f' <span class="dim">{when} · {item["size"] // 1024 + 1} KB</span></li>')
            else:
                rows.append(f'<li>{html.escape(item["name"])} <span class="dim">no log yet</span></li>')
        body = "\n".join(rows) or "<li>No plugins found.</li>"
        return (
            '<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1"><title>Plugin logs</title>'
            "<style>:root{color-scheme:dark}body{margin:0;background:#0e141b;color:#e6edf3;"
            "font:16px/1.5 -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif}"
            "main{max-width:460px;margin:0 auto;padding:32px 16px}a{color:#6cb6ff}"
            "li{margin:10px 0}.dim{color:#9aa7b3;font-size:13px}</style></head><body><main>"
            "<h1 style='font-size:22px'>Plugin logs</h1>"
            "<p class='dim'>The newest log of each plugin on the Deck, newest first. Open one, select all and copy it.</p>"
            f"<ul style='padding-left:18px'>{body}</ul></main></body></html>"
        )

    def _receive(self, link: str) -> Dict[str, Any]:
        """Runs on a request thread; the work happens on the plugin's loop."""
        if not self.loop:
            return {"ok": False, "message": "Plugin Hub is not ready."}
        future = asyncio.run_coroutine_threadsafe(self.on_link(link), self.loop)
        try:
            result = future.result(timeout=180)
        except Exception as exc:
            future.cancel()
            return {"ok": False, "message": f"The Deck could not get that plugin: {exc}"}
        with self._lock:
            if self.server is not None:
                self._arm()
        return result

    def _handler(self):
        outer = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "PluginHub"
            sys_version = ""

            def log_message(self, *_args: Any) -> None:  # keep the plugin log quiet
                pass

            def _route(self) -> Optional[str]:
                """What follows the code ("" for the page), or None without it."""
                path = self.path.split("?", 1)[0].rstrip("/")
                if not outer.code:
                    return None
                head, _, rest = path.lstrip("/").partition("/")
                if not secrets.compare_digest(head, outer.code):
                    return None
                return rest

            def _path_ok(self) -> bool:
                return self._route() == ""

            def _send(self, status: int, body: bytes, kind: str) -> None:
                self.send_response(status)
                self.send_header("Content-Type", kind)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "no-referrer")
                self.end_headers()
                self.wfile.write(body)

            def _json(self, status: int, data: Dict[str, Any]) -> None:
                self._send(status, json.dumps(data).encode("utf-8"), "application/json")

            def do_GET(self) -> None:  # noqa: N802
                route = self._route()
                if route == "":
                    return self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
                if route == "logs" and outer.logs:
                    return self._send(200, outer._logs_page().encode("utf-8"), "text/html; charset=utf-8")
                if route is not None and route.startswith("logs/") and outer.log_text:
                    result = outer.log_text(unquote(route[5:]), 500)
                    text = result.get("text") if result.get("ok") else result.get("error", "No log.")
                    header = f"{result.get('file', '')}\n\n" if result.get("ok") else ""
                    return self._send(200 if result.get("ok") else 404, (header + text).encode("utf-8"),
                                      "text/plain; charset=utf-8")
                return self._send(404, b"Not found", "text/plain; charset=utf-8")

            def do_POST(self) -> None:  # noqa: N802
                if not self._path_ok():
                    return self._send(404, b"Not found", "text/plain; charset=utf-8")
                try:
                    length = int(self.headers.get("Content-Length") or 0)
                except ValueError:
                    length = -1
                if length < 0 or length > MAX_BODY:
                    return self._json(413, {"ok": False, "message": "That is too long for a link."})
                raw = self.rfile.read(length).decode("utf-8", "replace")
                kind = (self.headers.get("Content-Type") or "").split(";")[0].strip()
                if kind == "application/json":
                    try:
                        link = str(json.loads(raw).get("link") or "")
                    except (ValueError, AttributeError):
                        link = ""
                else:
                    link = (parse_qs(raw).get("link") or [""])[0]
                link = link.strip()
                if not link:
                    return self._json(400, {"ok": False, "message": "Paste a GitHub link first."})
                result = outer._receive(link)
                self._json(200, result)

        return Handler

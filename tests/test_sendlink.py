"""The send-a-link page (backend/sendlink.py) against a real local socket."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.sendlink import CODE_ALPHABET, LinkServer, new_code  # noqa: E402


class SendLinkTest(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, daemon=True)
        self.thread.start()
        self.received = []

        async def on_link(link):
            self.received.append(link)
            if "bad" in link:
                return {"ok": False, "message": "no plugin there"}
            return {"ok": True, "message": f"Install {link}: confirm on your Deck."}

        self.server = LinkServer(on_link, host="127.0.0.1", ports=[0])
        self.state = self.server.start(self.loop)
        self.base = f"http://127.0.0.1:{self.state['port']}"

    def tearDown(self):
        self.server.stop()
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(2)
        self.loop.close()

    def get(self, path):
        with urllib.request.urlopen(self.base + path, timeout=5) as res:
            return res.status, res.read().decode()

    def post(self, path, body, kind="application/x-www-form-urlencoded"):
        req = urllib.request.Request(self.base + path, data=body, method="POST", headers={"Content-Type": kind})
        with urllib.request.urlopen(req, timeout=5) as res:
            return res.status, json.loads(res.read())

    def test_state_and_code(self):
        self.assertTrue(self.state["running"])
        code = self.state["code"]
        self.assertEqual(len(code), 6)
        self.assertTrue(all(c in CODE_ALPHABET for c in code))
        self.assertTrue(self.state["url"].endswith(f":{self.state['port']}/{code}"))
        self.assertNotEqual(new_code(), new_code())

    def test_page_needs_the_code(self):
        status, html = self.get("/" + self.state["code"])
        self.assertEqual(status, 200)
        self.assertIn("Send to Deck", html)
        for path in ("/", "/wrong1", "/" + self.state["code"] + "x"):
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                self.get(path)
            self.assertEqual(ctx.exception.code, 404)
        with self.assertRaises(urllib.error.HTTPError):
            self.post("/nope", b"link=a/b")
        self.assertEqual(self.received, [])

    def test_link_is_handed_over(self):
        path = "/" + self.state["code"]
        status, data = self.post(path, urllib.parse.urlencode({"link": " lauridskern/decky-emu-hub "}).encode())
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(self.received, ["lauridskern/decky-emu-hub"])
        status, data = self.post(path, json.dumps({"link": "bad/repo"}).encode(), "application/json")
        self.assertFalse(data["ok"])
        self.assertEqual(data["message"], "no plugin there")

    def test_empty_and_oversized(self):
        path = "/" + self.state["code"]
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.post(path, b"link=")
        self.assertEqual(ctx.exception.code, 400)
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.post(path, b"link=" + b"a" * 5000)
        self.assertEqual(ctx.exception.code, 413)
        self.assertEqual(self.received, [])

    def test_stop_closes_the_port(self):
        self.assertFalse(self.server.stop()["running"])
        with self.assertRaises(urllib.error.URLError):
            self.get("/" + self.state["code"])

    def test_expires_by_itself(self):
        self.server.stop()
        server = LinkServer(lambda _l: None, host="127.0.0.1", ports=[0], lifetime=0.2)
        server.start(self.loop)
        self.assertTrue(server.state()["running"])
        threading.Event().wait(0.6)
        self.assertFalse(server.state()["running"])


if __name__ == "__main__":
    unittest.main()

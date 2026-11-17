"""Plugin logs for Game Mode (backend/logs.py)."""

from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import logs  # noqa: E402


class LogsTest(unittest.TestCase):
    def setUp(self):
        home = tempfile.mkdtemp()
        self.plugins_dir = os.path.join(home, "homebrew", "plugins")
        self.logs = os.path.join(home, "homebrew", "logs")
        os.makedirs(self.plugins_dir)
        self.plugins = [{"name": "ROM-Store", "folder": "rom-store-decky"}, {"name": "Quiet", "folder": "quiet"}]
        folder = os.path.join(self.logs, "rom-store-decky")
        os.makedirs(folder)
        old = os.path.join(folder, "2026-11-17 10.00.00.log")
        with open(old, "w") as handle:
            handle.write("old start\n")
        os.utime(old, (time.time() - 3600, time.time() - 3600))
        with open(os.path.join(folder, "2026-11-18 09.00.00.log"), "w") as handle:
            handle.write("\n".join(f"line {i}" for i in range(1000)) + "\nTraceback: boom\n")
        with open(os.path.join(folder, "notes.txt"), "w") as handle:
            handle.write("not a log")

    def test_newest_log_tail(self):
        result = logs.plugin_log(self.plugins_dir, self.plugins, "ROM-Store", 50)
        self.assertTrue(result["ok"])
        self.assertTrue(result["file"].endswith("2026-11-18 09.00.00.log"))
        lines = result["text"].splitlines()
        self.assertEqual(len(lines), 50)
        self.assertEqual(lines[-1], "Traceback: boom")
        self.assertEqual(logs.plugin_log(self.plugins_dir, self.plugins, "rom-store-decky", 20)["name"], "ROM-Store")

    def test_only_installed_plugins(self):
        self.assertFalse(logs.plugin_log(self.plugins_dir, self.plugins, "../../etc", 20)["ok"])
        self.assertFalse(logs.plugin_log(self.plugins_dir, self.plugins, "Nope", 20)["ok"])
        quiet = logs.plugin_log(self.plugins_dir, self.plugins, "Quiet", 20)
        self.assertFalse(quiet["ok"])
        self.assertIn("no log yet", quiet["error"])

    def test_summary_and_big_files(self):
        summary = logs.summary(self.plugins_dir, self.plugins)
        self.assertEqual(summary[0]["name"], "ROM-Store")
        self.assertIsNone(summary[1]["file"])
        path = os.path.join(self.logs, "quiet")
        os.makedirs(path)
        with open(os.path.join(path, "big.log"), "w") as handle:
            handle.write("x" * 400_000 + "\nlast\n")
        text = logs.tail(os.path.join(path, "big.log"), 10, 1000)
        self.assertEqual(text.splitlines()[-1], "last")
        self.assertLessEqual(len(text), 1000)


if __name__ == "__main__":
    unittest.main()

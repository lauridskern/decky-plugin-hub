"""Offline tests: links, versions, release zips, links to repos, the hub.

python3 -m unittest discover -s tests
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from backend import package as pkg  # noqa: E402
from backend.github import GitHubError, RateLimited, notes_excerpt, parse_link  # noqa: E402
from backend.hub import Hub  # noqa: E402
from backend.installed import detect_repo, list_plugins  # noqa: E402
from backend.settings import SELF_NAME, SELF_REPO, Store  # noqa: E402
from backend.versions import compare, install_type, is_update  # noqa: E402


def make_zip(path: str, files: dict) -> str:
    with zipfile.ZipFile(path, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content if isinstance(content, (bytes, str)) else json.dumps(content))
    return path


def plugin_files(folder: str, name: str, version: str = "1.0.0", extra: dict = None) -> dict:
    files = {
        f"{folder}/plugin.json": {"name": name, "author": "someone", "flags": [], "api_version": 1},
        f"{folder}/package.json": {"name": folder, "version": version},
        f"{folder}/dist/index.js": "export default 1;",
        f"{folder}/main.py": "class Plugin: pass\n",
    }
    files.update(extra or {})
    return files


class LinkTests(unittest.TestCase):
    def check(self, text, full, tag=None, asset=None):
        ref = parse_link(text)
        self.assertEqual((ref.full, ref.tag, ref.asset), (full, tag, asset), text)

    def test_shapes(self):
        self.check("https://github.com/lauridskern/decky-rom-store", "lauridskern/decky-rom-store")
        self.check("github.com/lauridskern/decky-rom-store/", "lauridskern/decky-rom-store")
        self.check("http://www.github.com/o/r.git", "o/r")
        self.check("o/r", "o/r")
        self.check("  <https://github.com/o/r>  ", "o/r")
        self.check("git@github.com:o/r.git", "o/r")
        self.check("https://github.com/o/r/tree/main/src", "o/r")
        self.check("https://github.com/o/r/releases", "o/r")
        self.check("https://github.com/o/r/releases/latest", "o/r")
        self.check("https://github.com/o/r/releases/tag/v1.2.3", "o/r", tag="v1.2.3")
        self.check("https://github.com/o/r/releases/download/v1.2.3/ROM-Store.zip", "o/r", "v1.2.3", "ROM-Store.zip")
        self.check("https://github.com/o/r/releases/latest/download/ROM-Store.zip", "o/r", None, "ROM-Store.zip")
        self.check("https://api.github.com/repos/o/r/releases/latest", "o/r")

    def test_rejects(self):
        for bad in ("", "   ", "https://gitlab.com/o/r", "https://github.com/onlyowner", "example.com/o/r", "not a link"):
            with self.assertRaises(GitHubError, msg=bad):
                parse_link(bad)


class VersionTests(unittest.TestCase):
    def test_compare(self):
        self.assertEqual(compare("v1.2.3", "1.2.3"), 0)
        self.assertEqual(compare("1.2", "1.2.0"), 0)
        self.assertEqual(compare("1.9.0", "1.10.0"), -1)
        self.assertEqual(compare("v2.0.0", "1.99"), 1)
        self.assertEqual(compare("1.0.0-beta.2", "1.0.0"), -1)
        self.assertEqual(compare("1.0.0-beta.2", "1.0.0-beta.10"), -1)
        self.assertEqual(compare("release-4", "release-5"), -1)
        self.assertIsNone(compare("nightly", "1.0"))

    def test_is_update(self):
        self.assertTrue(is_update("1.16.0", "v1.16.2"))
        self.assertFalse(is_update("1.16.2", "v1.16.2"))
        self.assertFalse(is_update("1.17.0", "v1.16.2"))
        self.assertTrue(is_update("nightly-a", "nightly-b"))
        self.assertTrue(is_update(None, "v1"))
        self.assertFalse(is_update("1.0", None))

    def test_install_type(self):
        self.assertEqual(install_type(None, "v1"), 0)
        self.assertEqual(install_type("1.0.0", "v1.0.0"), 1)
        self.assertEqual(install_type("1.0.0", "v1.1.0"), 2)
        self.assertEqual(install_type("2.0.0", "v1.1.0"), 3)


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_good_zip(self):
        path = make_zip(os.path.join(self.tmp, "a.zip"), plugin_files("my-plugin", "My-Plugin", "2.1.0"))
        info = pkg.inspect_zip(path)
        self.assertEqual((info.folder, info.name, info.version), ("my-plugin", "My-Plugin", "2.1.0"))
        self.assertEqual(len(info.sha256), 64)
        self.assertEqual(info.to_dict()["file_url"], "file://" + os.path.abspath(path))

    def test_bad_zips(self):
        cases = {
            "flat": {"plugin.json": {"name": "X"}, "dist/index.js": ""},
            "none": {"x/readme.md": "hi"},
            "two": {**plugin_files("a", "A"), **plugin_files("b", "B")},
            "unbuilt": {"x/plugin.json": {"name": "X"}},
            "noname": {"x/plugin.json": {"author": "a"}, "x/dist/index.js": ""},
            "escape": {**plugin_files("x", "X"), "../evil.sh": "rm -rf"},
        }
        for label, files in cases.items():
            path = make_zip(os.path.join(self.tmp, f"{label}.zip"), files)
            with self.assertRaises(pkg.PackageError, msg=label):
                pkg.inspect_zip(path)
        junk = os.path.join(self.tmp, "junk.zip")
        with open(junk, "wb") as fh:
            fh.write(b"<html>not a zip</html>")
        with self.assertRaises(pkg.PackageError):
            pkg.inspect_zip(junk)

    def test_order_assets(self):
        assets = [{"name": n} for n in ("source-code.zip", "rom-store-decky.zip", "ROM-Store.zip", "other.zip")]
        order = [a["name"] for a in pkg.order_assets(assets, "lauridskern/decky-rom-store")]
        self.assertEqual(order[:2], ["rom-store-decky.zip", "ROM-Store.zip"])  # both match the repo, release order
        counted = [dict(a, download_count=c) for a, c in zip(assets, (0, 1, 5, 9))]
        order = [a["name"] for a in pkg.order_assets(counted, "lauridskern/decky-rom-store")]
        self.assertEqual(order[:2], ["ROM-Store.zip", "rom-store-decky.zip"])  # the one people download
        self.assertEqual(order[-1], "source-code.zip")
        order = [a["name"] for a in pkg.order_assets(assets, "lauridskern/decky-rom-store", want_name="ROM-Store")]
        self.assertEqual(order[0], "ROM-Store.zip")
        order = [a["name"] for a in pkg.order_assets(assets, "o/r", want_asset="other.zip")]
        self.assertEqual(order, ["other.zip"])

    def test_prune(self):
        old = os.path.join(self.tmp, "old.zip")
        new = os.path.join(self.tmp, "new.zip")
        kept = os.path.join(self.tmp, "kept.zip")
        for p in (old, new, kept):
            open(p, "wb").close()
        past = time.time() - pkg.KEEP_SECONDS - 10
        os.utime(old, (past, past))
        os.utime(kept, (past, past))
        self.assertEqual(pkg.prune(self.tmp, keep=[kept]), 1)
        self.assertEqual(sorted(os.listdir(self.tmp)), ["kept.zip", "new.zip"])


class InstalledTests(unittest.TestCase):
    def test_detect_repo(self):
        self.assertEqual(detect_repo({}, {"repository": {"url": "git+https://github.com/a/b.git"}}), "a/b")
        self.assertEqual(detect_repo({}, {"repository": "https://github.com/a/b"}), "a/b")
        self.assertEqual(detect_repo({}, {"bugs": {"url": "https://github.com/a/b/issues"}}), "a/b")
        self.assertEqual(detect_repo({"homepage": "https://github.com/c/d"}, None), "c/d")
        # The template's link left in a plugin's package.json is not its repo.
        self.assertIsNone(detect_repo({}, {"repository": "https://github.com/SteamDeckHomebrew/decky-plugin-template"}))
        self.assertIsNone(detect_repo({"publish": {"image": "https://raw.githubusercontent.com/x/y/a.png"}}, {}))
        self.assertIsNone(detect_repo({}, {"repository": "https://gitlab.com/a/b"}))

    def test_list(self):
        tmp = tempfile.mkdtemp()
        try:
            for folder, files in (("one", plugin_files("one", "One", "1.0")), ("two", plugin_files("two", "Two"))):
                for name, content in files.items():
                    path = os.path.join(tmp, name)
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    with open(path, "w") as fh:
                        fh.write(content if isinstance(content, str) else json.dumps(content))
            os.makedirs(os.path.join(tmp, "broken"))
            plugins = list_plugins(tmp)
            self.assertEqual([p["name"] for p in plugins], ["One", "Two"])
            self.assertEqual(plugins[0]["version"], "1.0")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class StoreTests(unittest.TestCase):
    def test_persistence(self):
        tmp = tempfile.mkdtemp()
        try:
            path = os.path.join(tmp, "s", "hub.json")
            store = Store(path)
            self.assertEqual(store.data["links"][SELF_NAME]["repo"], SELF_REPO)
            store.update_settings({"include_prereleases": 1, "github_token": " ghp_abcdefgh1234 ", "nonsense": 5})
            store.link("X", "a/b")
            store.unlink("Y")
            again = Store(path)
            self.assertTrue(again.settings["include_prereleases"])
            self.assertEqual(again.settings["github_token"], "ghp_abcdefgh1234")
            self.assertNotIn("nonsense", again.settings)
            self.assertEqual(again.data["links"]["X"]["repo"], "a/b")
            self.assertIn("Y", again.data["ignored"])
            public = again.public_settings()
            self.assertNotIn("github_token", public)
            self.assertEqual(public["token_hint"], "…1234")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class FakeGitHub:
    """Stands in for backend.github.GitHub: releases and files from memory."""

    def __init__(self, releases: dict, files: dict) -> None:
        self.releases = releases  # "o/r" -> release dict, or an exception
        self.files = files        # url -> path of a zip
        self.rate = {}
        self.token = ""
        self.ca_source = "test"

    def release(self, ref, prereleases=False):
        value = self.releases.get(ref.full)
        if isinstance(value, Exception):
            raise value
        if value is None:
            raise GitHubError(f"{ref.full} has no releases yet.", "no_release")
        return value

    def open_asset(self, url):
        return open(self.files[url], "rb")


class HubTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.plugins_dir = os.path.join(self.tmp, "plugins")
        os.makedirs(self.plugins_dir)
        self.emitted = []

        async def emit(event, payload):
            self.emitted.append((event, payload))

        self.hub = Hub(os.path.join(self.tmp, "settings"), os.path.join(self.tmp, "data"),
                       self.plugins_dir, emit=emit)
        zips = os.path.join(self.tmp, "zips")
        os.makedirs(zips)
        good = make_zip(os.path.join(zips, "Cool.zip"), plugin_files("cool-plugin", "Cool", "0.0.0"))
        legacy = make_zip(os.path.join(zips, "cool-legacy.zip"), plugin_files("cool-legacy", "cool-plugin"))
        notes = "## What's new\n- **Faster** startup\n- [Docs](https://x)\n"
        self.hub.github = FakeGitHub(
            {
                "o/cool-plugin": {
                    "tag_name": "v2.0.0", "name": "Cool 2", "body": notes, "html_url": "https://github.com/o/cool-plugin/releases/tag/v2.0.0",
                    "assets": [
                        {"name": "cool-legacy.zip", "browser_download_url": "u://legacy", "size": 100},
                        {"name": "Cool.zip", "browser_download_url": "u://good", "size": 100},
                    ],
                },
                "o/source-only": {"tag_name": "v1", "assets": []},
                "o/limited": RateLimited(int(time.time()) + 600),
            },
            {"u://good": good, "u://legacy": legacy},
        )

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_async(self, coro):
        return asyncio.run(coro)

    def install_folder(self, folder, name, version):
        for path, content in plugin_files(folder, name, version).items():
            full = os.path.join(self.plugins_dir, path)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w") as fh:
                fh.write(content if isinstance(content, str) else json.dumps(content))

    def test_resolve_install_and_update_cycle(self):
        res = self.run_async(self.hub.resolve("https://github.com/o/cool-plugin"))
        self.assertTrue(res["ok"], res)
        # "Cool" wins over the first asset because its name matches the repo.
        self.assertEqual((res["name"], res["version"], res["install_type"]), ("Cool", "v2.0.0", 0))
        self.assertTrue(os.path.isfile(res["package"]["path"]))
        self.assertIn("• Faster startup", res["notes"])
        self.assertIn("Cool", self.hub.store.data["pending"])

        # Decky installs it (extracts fresh files): the pending request becomes a record.
        time.sleep(0.01)
        self.install_folder("cool-plugin", "Cool", "0.0.0")
        state = self.hub.state()
        cool = next(p for p in state["plugins"] if p["name"] == "Cool")
        self.assertEqual((cool["version"], cool["repo"], cool["link"]), ("v2.0.0", "o/cool-plugin", "install"))
        self.assertEqual(cool["status"], "current")
        self.assertFalse(cool["update"])

        # A newer release shows up.
        self.hub.github.releases["o/cool-plugin"]["tag_name"] = "v2.1.0"
        state = self.run_async(self.hub.check(force=True))
        cool = next(p for p in state["plugins"] if p["name"] == "Cool")
        self.assertTrue(cool["update"])
        self.assertEqual(state["updates"], 1)
        self.assertEqual(self.emitted[0][0], "plugin_hub_updates")
        self.assertEqual(self.emitted[0][1]["updates"][0]["to"], "v2.1.0")
        # Told once, not on every check.
        self.run_async(self.hub.check(force=True))
        self.assertEqual(len(self.emitted), 1)

        upd = self.run_async(self.hub.prepare_update("Cool"))
        self.assertTrue(upd["ok"], upd)
        self.assertEqual(upd["install_type"], 2)

        # Replaced by something else (another installer): the record goes.
        time.sleep(0.01)
        later = time.time() + 30
        os.utime(os.path.join(self.plugins_dir, "cool-plugin", "plugin.json"), (later, later))
        self.hub.store.data["pending"].clear()
        cool = next(p for p in self.hub.state()["plugins"] if p["name"] == "Cool")
        self.assertEqual(cool["version"], "0.0.0")

    def test_installed_copy_is_updated_not_duplicated(self):
        self.install_folder("cool-legacy", "cool-plugin", "1.0.0")
        self.hub.link("cool-plugin", "o/cool-plugin")
        res = self.run_async(self.hub.resolve("https://github.com/o/cool-plugin"))
        self.assertTrue(res["ok"], res)
        self.assertEqual((res["name"], res["install_type"]), ("cool-plugin", 2))

    def test_want_name_picks_the_matching_asset(self):
        res = self.run_async(self.hub.resolve("o/cool-plugin", want_name="cool-plugin"))
        self.assertTrue(res["ok"], res)
        self.assertEqual(res["package"]["folder"], "cool-legacy")

    def test_errors(self):
        res = self.run_async(self.hub.resolve("o/source-only"))
        self.assertEqual(res["kind"], "no_zip")
        res = self.run_async(self.hub.resolve("o/limited"))
        self.assertEqual(res["kind"], "rate_limited")
        self.assertIn("rate limit", res["error"])
        res = self.run_async(self.hub.resolve("o/missing"))
        self.assertFalse(res["ok"])
        res = self.run_async(self.hub.resolve("https://gitlab.com/o/r"))
        self.assertEqual(res["kind"], "bad_link")
        res = self.run_async(self.hub.resolve("https://github.com/o/cool-plugin/releases/download/v2.0.0/nope.zip"))
        self.assertEqual(res["kind"], "no_zip")

    def test_unlink_and_auto_detect(self):
        self.install_folder("auto", "Auto", "1.0.0")
        with open(os.path.join(self.plugins_dir, "auto", "package.json"), "w") as fh:
            json.dump({"version": "1.0.0", "repository": "https://github.com/o/cool-plugin"}, fh)
        view = next(p for p in self.hub.state()["plugins"] if p["name"] == "Auto")
        self.assertEqual((view["repo"], view["link"]), ("o/cool-plugin", "auto"))
        self.hub.unlink("Auto")
        view = next(p for p in self.hub.state()["plugins"] if p["name"] == "Auto")
        self.assertIsNone(view["repo"])
        self.assertEqual(self.hub.link("Auto", "github.com/a/b")["repo"], "a/b")
        view = next(p for p in self.hub.state()["plugins"] if p["name"] == "Auto")
        self.assertEqual((view["repo"], view["link"]), ("a/b", "manual"))

    def test_rate_limit_during_check(self):
        self.install_folder("lim", "Lim", "1.0.0")
        self.hub.link("Lim", "o/limited")
        state = self.run_async(self.hub.check(force=True))
        self.assertEqual(state["error"]["kind"], "rate_limited")
        self.assertIsNone(state["checked_at"])  # a failed check is retried next time


class NotesTests(unittest.TestCase):
    def test_excerpt(self):
        text = notes_excerpt("<!-- hidden -->\n# Title\n\n* one\n* two\n" + "x" * 900)
        self.assertTrue(text.startswith("Title\n• one\n• two"))
        self.assertLessEqual(len(text), 400)


if __name__ == "__main__":
    unittest.main()

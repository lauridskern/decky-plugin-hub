#!/usr/bin/env python3
"""Verify a release zip against Decky Loader's real install logic.

Decky (backend/decky_loader/browser.py) does:

    zip_file.extractall(self.plugin_path)
    plugin_folder = self.find_plugin_folder(name)

and "Install from URL" takes the name from the URL (frontend/src/store.tsx):

    splitURL[splitURL.length - 1].replace('.zip', '')

So the zip must hold one top level folder with plugin.json, and plugin.json's
name must equal the asset's file name. (The hub itself passes the name it
reads from the zip, but people install the hub with "Install from URL".)

Usage:  python3 tools/verify_package.py [path/to/Plugin-Hub.zip]
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from urllib.parse import urlparse

DEFAULT_ASSET = "Plugin-Hub.zip"
URL = f"https://github.com/lauridskern/decky-plugin-hub/releases/latest/download/{DEFAULT_ASSET}"


def find_plugin_folder(plugin_path: str, name: str):
    """Copy of Decky's PluginBrowser.find_plugin_folder."""
    for folder in os.listdir(plugin_path):
        try:
            with open(os.path.join(plugin_path, folder, "plugin.json"), "r", encoding="utf-8") as fh:
                plugin = json.load(fh)
            if plugin["name"] == name:
                return folder
        except Exception:
            continue
    return None


def main() -> int:
    archive = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_ASSET
    if not os.path.isfile(archive):
        print(f"FAIL  {archive} not found")
        return 1

    name = urlparse(URL).path.rsplit("/", 1)[-1].replace(".zip", "")
    print(f"URL               : {URL}")
    print(f"derived name      : {name!r}")

    with zipfile.ZipFile(archive) as zf:
        names = zf.namelist()
        plugin_jsons = [n for n in names if n.endswith("/plugin.json") and n.count("/") == 1]
        print(f"plugin.json in zip: {plugin_jsons}")
        if len(plugin_jsons) != 1:
            print("FAIL  the zip must contain exactly one <folder>/plugin.json")
            return 1
        plugin = json.loads(zf.read(plugin_jsons[0]).decode("utf-8"))
        print(f"plugin.json name  : {plugin.get('name')!r}")
        if plugin.get("name") != name:
            print(f"FAIL  plugin.json name {plugin.get('name')!r} != derived name {name!r}")
            return 1
        if "root" in (plugin.get("flags") or []):
            print("FAIL  the hub must not run as root")
            return 1

        plugins_path = tempfile.mkdtemp(prefix="decky-plugins-")
        zf.extractall(plugins_path)
        print(f"extracted into    : {sorted(os.listdir(plugins_path))}")
        folder = find_plugin_folder(plugins_path, name)
        if folder is None:
            print("FAIL  find_plugin_folder() found no matching plugin folder")
            return 1
        print(f"plugin folder     : {folder}")
        for required in ("plugin.json", "package.json", "main.py", "dist/index.js",
                         "backend/hub.py", "backend/cacert.pem", "LICENSE"):
            ok = os.path.isfile(os.path.join(plugins_path, folder, required))
            print(f"  {'OK  ' if ok else 'FAIL'} {required}")
            if not ok:
                return 1
        for unwanted in ("tests", "src", "node_modules", "tools"):
            if os.path.exists(os.path.join(plugins_path, folder, unwanted)):
                print(f"FAIL  {unwanted}/ should not be in the package")
                return 1

        check = subprocess.run(
            [sys.executable, "-c",
             "import sys; sys.path.insert(0, '.'); import main; p = main.Plugin.instance(); "
             "print('backend import OK, api_version =', __import__('json').load(open('plugin.json'))['api_version'])"],
            cwd=os.path.join(plugins_path, folder),
            capture_output=True,
            text=True,
            env={**os.environ, "HOME": plugins_path},
        )
        print(check.stdout.strip() or check.stderr.strip()[-500:])
        shutil.rmtree(plugins_path, ignore_errors=True)
        if check.returncode != 0:
            print("FAIL  the backend could not be imported from the package")
            return 1

    print("\nPASS  the package installs with Decky's own logic")
    return 0


if __name__ == "__main__":
    sys.exit(main())

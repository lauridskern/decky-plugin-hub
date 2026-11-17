"""Plugin logs, readable in Game Mode.

Decky writes each plugin's log to ~/homebrew/logs/<plugin folder>/, one file
per start. Reading one otherwise means Desktop Mode or SSH. The hub shows the
newest file's last lines in a plugin's dialog and on the phone page
(backend/sendlink.py), so a broken plugin can be diagnosed from the couch.

Only folders of installed plugins are read (the caller passes the installed
list; a name is never turned into a path by itself), only `*.log` files, and
only the last part of a file.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

TAIL_LINES = 300
TAIL_BYTES = 256 * 1024


def logs_root(plugins_dir: str) -> str:
    return os.path.join(os.path.dirname(os.path.abspath(plugins_dir)), "logs")


def newest(folder: str) -> Optional[str]:
    try:
        files = [os.path.join(folder, n) for n in os.listdir(folder) if n.endswith(".log")]
    except OSError:
        return None
    files = [f for f in files if os.path.isfile(f)]
    return max(files, key=os.path.getmtime) if files else None


def tail(path: str, lines: int = TAIL_LINES, max_bytes: int = TAIL_BYTES) -> str:
    with open(path, "rb") as handle:
        handle.seek(0, os.SEEK_END)
        size = handle.tell()
        handle.seek(max(0, size - max_bytes))
        data = handle.read()
    text = data.decode("utf-8", "replace")
    if size > max_bytes:
        text = text.split("\n", 1)[-1]  # drop the partial first line
    return "\n".join(text.splitlines()[-lines:])


def summary(plugins_dir: str, plugins: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Each installed plugin with its newest log file, newest first."""
    root = logs_root(plugins_dir)
    out = []
    for plugin in plugins:
        path = newest(os.path.join(root, plugin["folder"]))
        out.append({
            "name": plugin["name"],
            "folder": plugin["folder"],
            "file": os.path.basename(path) if path else None,
            "mtime": os.path.getmtime(path) if path else None,
            "size": os.path.getsize(path) if path else 0,
        })
    out.sort(key=lambda item: -(item["mtime"] or 0))
    return out


def plugin_log(plugins_dir: str, plugins: List[Dict[str, Any]], name: str,
               lines: int = TAIL_LINES) -> Dict[str, Any]:
    """The last lines of an installed plugin's newest log, by name or folder."""
    plugin = next((p for p in plugins if p["name"] == name or p["folder"] == name), None)
    if not plugin:
        return {"ok": False, "error": f"{name} is not installed."}
    folder = os.path.join(logs_root(plugins_dir), plugin["folder"])
    path = newest(folder)
    if not path:
        return {"ok": False, "name": plugin["name"], "error": f"{plugin['name']} has no log yet ({folder})."}
    try:
        text = tail(path, max(20, min(int(lines or TAIL_LINES), 2000)))
    except OSError as error:
        return {"ok": False, "name": plugin["name"], "error": f"Could not read {path} ({error})."}
    return {
        "ok": True,
        "name": plugin["name"],
        "folder": plugin["folder"],
        "file": path,
        "mtime": os.path.getmtime(path),
        "size": os.path.getsize(path),
        "text": text,
    }

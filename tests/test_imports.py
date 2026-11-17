"""Every import in the backend must exist in Decky Loader's own Python.

Decky runs plugin backends with the Python frozen into its PluginLoader
binary (PyInstaller). That Python only has the standard-library modules
Decky itself uses: `xml.etree`, for one, is missing, and a single import of
it stopped Emu Hub's whole backend from loading (every call failed, so the
page waited forever). tests/decky_modules.txt is the list read out of
PluginLoader v3.3.1; regenerate it after a Decky update (AGENTS.md).
"""

from __future__ import annotations

import ast
import glob
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# Compiled into the interpreter itself, so never in the bundle's module lists.
BUILTIN = {"sys", "time", "builtins", "errno", "gc", "itertools", "marshal", "posix", "pwd", "_thread",
           "_io", "_signal", "_stat", "_string", "_weakref", "atexit", "faulthandler"}
# Provided by Decky at run time, or our own code.
PROVIDED = {"decky", "decky_plugin", "backend", "__future__"}


def bundled() -> set:
    with open(os.path.join(HERE, "decky_modules.txt"), encoding="utf-8") as fh:
        return {line.strip() for line in fh if line.strip() and not line.startswith("#")}


def imports(path: str):
    with open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), path)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.lineno, node.module


class DeckyImportsTest(unittest.TestCase):
    def test_backend_only_imports_what_decky_ships(self):
        have = bundled()
        files = [os.path.join(ROOT, "main.py")] + sorted(glob.glob(os.path.join(ROOT, "backend", "**", "*.py"), recursive=True))
        missing = []
        for path in files:
            for line, module in imports(path):
                top = module.split(".")[0]
                if top in PROVIDED or module in BUILTIN or top in BUILTIN or module in have:
                    continue
                missing.append(f"{os.path.relpath(path, ROOT)}:{line} imports {module}")
        self.assertEqual(missing, [], "not in Decky Loader's Python:\n" + "\n".join(missing))


if __name__ == "__main__":
    unittest.main()

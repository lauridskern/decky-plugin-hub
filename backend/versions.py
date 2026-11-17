"""Comparing a release tag with an installed version.

Tags come in every shape ("v1.2.3", "1.2", "release-4", "2024.11.02",
"v1.0.0-beta.2"). Two versions are compared by their numbers when both have
any; anything else only tells "same" from "different", and different counts
as an update (the tag is what the author published last).
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

_PREFIX = re.compile(r"^(?:version|release|rel|ver|v)[-_ .]*", re.IGNORECASE)
_PRE = re.compile(r"(alpha|beta|rc|pre|preview|dev)", re.IGNORECASE)


def normalize(version: Optional[str]) -> str:
    """'v1.2.3' -> '1.2.3'; surrounding noise removed, case folded."""
    text = (version or "").strip()
    text = _PREFIX.sub("", text)
    return text.lower()


def _parts(version: str) -> Optional[Tuple[List[int], bool, List[int]]]:
    """(release numbers, is prerelease, prerelease numbers), or None."""
    text = normalize(version)
    if not text:
        return None
    # Build metadata never orders versions.
    text = text.split("+", 1)[0]
    match = re.match(r"^(\d+(?:\.\d+)*)(.*)$", text)
    if not match:
        return None
    numbers = [int(n) for n in match.group(1).split(".")]
    rest = match.group(2)
    pre = bool(_PRE.search(rest))
    pre_numbers = [int(n) for n in re.findall(r"\d+", rest)] if pre else []
    return numbers, pre, pre_numbers


def compare(a: Optional[str], b: Optional[str]) -> Optional[int]:
    """-1, 0 or 1 like cmp(a, b); None when the two cannot be ordered."""
    if normalize(a) == normalize(b):
        return 0
    pa, pb = _parts(a or ""), _parts(b or "")
    if pa is None or pb is None:
        return None
    na, nb = list(pa[0]), list(pb[0])
    width = max(len(na), len(nb))
    na += [0] * (width - len(na))
    nb += [0] * (width - len(nb))
    if na != nb:
        return -1 if na < nb else 1
    # 1.0.0-beta < 1.0.0
    if pa[1] != pb[1]:
        return -1 if pa[1] else 1
    if pa[2] != pb[2]:
        return -1 if pa[2] < pb[2] else 1
    return 0


def is_update(installed: Optional[str], latest: Optional[str]) -> bool:
    """True when `latest` should replace `installed`."""
    if not latest:
        return False
    if not installed:
        return True
    order = compare(installed, latest)
    if order is None:
        return normalize(installed) != normalize(latest)
    return order < 0


def install_type(installed: Optional[str], target: Optional[str]) -> int:
    """Decky's InstallType: 0 install, 1 reinstall, 2 update, 3 downgrade."""
    if installed is None:
        return 0
    order = compare(installed, target)
    if order == 0:
        return 1
    if order is not None and order > 0:
        return 3
    return 2

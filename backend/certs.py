"""TLS trust store.

SteamOS ships an outdated ca-certificates bundle, so the plugin carries its
own (cacert.pem, the Mozilla bundle). Unlike a catalogue reader, an installer
never falls back to an unverified connection: what it downloads becomes code
that Decky runs.
"""

from __future__ import annotations

import os
import ssl
from typing import List, Tuple

BUNDLED_CA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cacert.pem")

SYSTEM_CA_PATHS = (
    "/etc/ssl/certs/ca-certificates.crt",
    "/etc/pki/tls/certs/ca-bundle.crt",
    "/etc/ssl/cert.pem",
)


def ca_candidates() -> List[str]:
    candidates: List[str] = []
    try:
        import certifi  # type: ignore

        candidates.append(certifi.where())
    except Exception:
        pass
    if os.path.isfile(BUNDLED_CA):
        candidates.append(BUNDLED_CA)
    candidates.extend(path for path in SYSTEM_CA_PATHS if os.path.isfile(path))
    return candidates


def ssl_context() -> Tuple[ssl.SSLContext, str]:
    """The best verifying context available, and where its roots came from."""
    for path in ca_candidates():
        try:
            return ssl.create_default_context(cafile=path), path
        except Exception:
            continue
    return ssl.create_default_context(), "system default"

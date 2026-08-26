"""Per-store StoreLink credential loading.

Keys are issued by Korral IT, scoped to a single store, and rotated
weekly. They are read fresh from their source on every request so a
rotation is picked up without restarting the server. Sources, in order:

1. Environment variable ``KORRAL_STORE_KEY_<store_id>``
2. File ``<KORRAL_STORE_KEYS_DIR>/store_<store_id>.key`` — e.g. a
   Kubernetes secret volume backed by GCP Secret Manager, which updates
   in place when IT rotates the key.

Key values are never logged; use :func:`key_fingerprint` when a trace
needs to show *which* key was used.
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path


class MissingStoreCredentialError(Exception):
    """No StoreLink key is configured for the requested store."""

    def __init__(self, store_id: int, available: list[int]):
        self.store_id = store_id
        self.available = available
        stores = ", ".join(str(s) for s in available) if available else "none"
        super().__init__(
            f"This server has no StoreLink key for store {store_id}, so it cannot "
            f"act on that store. Stores it can act on: {stores}. Korral IT issues "
            f"keys per store; to add this store, provision KORRAL_STORE_KEY_{store_id} "
            f"(or store_{store_id}.key in the keys directory) and no restart is needed."
        )


ENV_PREFIX = "KORRAL_STORE_KEY_"
_KEY_FILE_PATTERN = re.compile(r"store_(\d+)\.key")


def key_fingerprint(key: str) -> str:
    """Short non-reversible identifier for a key, safe to log."""
    return hashlib.sha256(key.encode()).hexdigest()[:8]


class StoreKeyProvider:
    def __init__(self, keys_dir: str | None = None):
        self._keys_dir_override = keys_dir

    def _keys_dir(self) -> Path | None:
        path = self._keys_dir_override or os.environ.get("KORRAL_STORE_KEYS_DIR")
        return Path(path) if path else None

    def get_key(self, store_id: int) -> str:
        """Read the current key for a store. Never cached: a weekly rotation
        that lands in the environment or the keys directory takes effect on
        the next call."""
        env_value = os.environ.get(f"{ENV_PREFIX}{store_id}", "").strip()
        if env_value:
            return env_value
        directory = self._keys_dir()
        if directory is not None:
            key_file = directory / f"store_{store_id}.key"
            if key_file.is_file():
                file_value = key_file.read_text().strip()
                if file_value:
                    return file_value
        raise MissingStoreCredentialError(store_id, self.available_store_ids())

    def available_store_ids(self) -> list[int]:
        """Stores for which a non-empty key is currently present."""
        found: set[int] = set()
        for name, value in os.environ.items():
            if name.startswith(ENV_PREFIX) and value.strip():
                suffix = name[len(ENV_PREFIX):]
                if suffix.isdigit():
                    found.add(int(suffix))
        directory = self._keys_dir()
        if directory is not None and directory.is_dir():
            for key_file in directory.glob("store_*.key"):
                match = _KEY_FILE_PATTERN.fullmatch(key_file.name)
                if match and key_file.read_text().strip():
                    found.add(int(match.group(1)))
        return sorted(found)

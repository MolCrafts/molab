"""Application-owned molq connection, explicitly bound to every remote path."""

from __future__ import annotations

import atexit
import threading

from molq import Molq, MolqError

_lock = threading.RLock()
_client: Molq | None = None
_registry_id: str | None = None


def get_client(registry_id: str | None = None) -> Molq:
    """Return this process's stdio client and verify the destination identity."""
    global _client, _registry_id
    with _lock:
        if _client is None:
            client = Molq(timeout=3610)
            try:
                hello = client.rpc("molq.hello")
            except BaseException:
                client.close()
                raise
            _client, _registry_id = client, hello["registry_id"]
        if registry_id is not None and registry_id != _registry_id:
            raise MolqError("REGISTRY_MISMATCH", "Destination belongs to another molq registry")
        return _client


def close_client() -> None:
    """Release the service connection without cancelling accepted jobs."""
    global _client, _registry_id
    with _lock:
        if _client is not None:
            _client.close()
        _client = None
        _registry_id = None


atexit.register(close_client)

"""Re-export shim — the typed OKF edge vocabulary moved to :mod:`molab.knowledge.edges`.

Edge roles belong to the Open Knowledge Format library, not to workspace
storage. Re-exported here so workspace-internal callers keep working against
the *same* objects.
"""

from molab.knowledge.edges import (
    DEFAULT_EDGE_ROLE,
    Edge,
    EdgeRole,
    encode_label,
    parse_role,
    validate_role,
)

__all__ = [
    "DEFAULT_EDGE_ROLE",
    "Edge",
    "EdgeRole",
    "encode_label",
    "parse_role",
    "validate_role",
]

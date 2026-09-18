"""Re-export shim — the OKF Concept types moved to :mod:`molab.knowledge.concepts`.

Notes and literature are Open Knowledge Format Concepts: directories whose path
is their identity, usable with or without a molab workspace. They live in the
OKF library now.

These re-export the **same class objects**, so the many ``isinstance(x, Note)``
sites across the server, CLI and harness keep agreeing no matter which import
path a caller used. Re-exporting is load-bearing: re-*declaring* the classes
here would hit ``register_concept_type``'s collision check and fail ``import
molab`` outright.
"""

from molab.knowledge.concepts import NOTE_KIND, REFERENCE_KIND, Note, ReferenceConcept

__all__ = ["NOTE_KIND", "REFERENCE_KIND", "Note", "ReferenceConcept"]

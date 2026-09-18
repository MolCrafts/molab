"""Re-export shim — the Zotero reader moved to :mod:`molab.knowledge.zotero`.

It only ever needed ``sqlite3`` + ``pydantic``, and it produces OKF
``ReferenceConcept`` records — so it belongs with the OKF library.
"""

from molab.knowledge.zotero import ZoteroItem, read_zotero_items

__all__ = ["ZoteroItem", "read_zotero_items"]

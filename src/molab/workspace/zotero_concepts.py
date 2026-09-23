"""Re-export shim — the Zotero reader moved to :mod:`molab.knowledge.zotero`.

It only ever needed ``sqlite3`` + ``pydantic``, and it produces OKF
``Literature`` records — so it belongs with the knowledge library.
"""

from molab.knowledge.zotero import ZoteroItem, read_zotero_items

__all__ = ["ZoteroItem", "read_zotero_items"]

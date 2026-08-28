"""Every ``__all__`` entry of every public molexp package must resolve.

Regression gate for the class of bug where a section comment (or any other
non-symbol string) lands inside ``__all__`` — ``from <pkg> import *`` then
raises for every user, but nothing else in the suite notices.
"""

from __future__ import annotations

import importlib

import pytest

PUBLIC_PACKAGES = [
    "molexp",
    "molexp.knowledge",
    "molexp.workspace",
    "molexp.workflow",
    "molexp.agent",
    "molexp.harness",
    "molexp.services",
]


@pytest.mark.parametrize("package", PUBLIC_PACKAGES)
def test_all_entries_resolve(package: str) -> None:
    module = importlib.import_module(package)
    exported = getattr(module, "__all__", [])
    assert exported, f"{package} declares no __all__"
    unresolved = [name for name in exported if not hasattr(module, name)]
    assert not unresolved, (
        f"{package}.__all__ contains entries that do not resolve on the module: "
        f"{unresolved} — star-import of the package is broken."
    )
    non_identifiers = [name for name in exported if not name.isidentifier()]
    assert not non_identifiers, (
        f"{package}.__all__ contains non-identifier strings (stray comments?): {non_identifiers}"
    )

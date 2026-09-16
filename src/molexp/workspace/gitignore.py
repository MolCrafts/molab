"""Re-export shim — the ``.gitignore`` matcher moved to :mod:`molexp.gitignore`.

It is a cross-layer primitive now: both the workspace file browser and the
``molexp.knowledge`` bundle walk skip the same paths git would.
"""

from molexp.gitignore import (
    DEFAULT_IGNORE_LINES,
    GitIgnoreMatcher,
    load_gitignore_matcher,
)

__all__ = ["DEFAULT_IGNORE_LINES", "GitIgnoreMatcher", "load_gitignore_matcher"]

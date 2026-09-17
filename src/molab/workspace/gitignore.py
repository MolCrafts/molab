"""Re-export shim — the ``.gitignore`` matcher moved to :mod:`molab.gitignore`.

It is a cross-layer primitive now: both the workspace file browser and the
``molab.knowledge`` bundle walk skip the same paths git would.
"""

from molab.gitignore import (
    DEFAULT_IGNORE_LINES,
    GitIgnoreMatcher,
    load_gitignore_matcher,
)

__all__ = ["DEFAULT_IGNORE_LINES", "GitIgnoreMatcher", "load_gitignore_matcher"]

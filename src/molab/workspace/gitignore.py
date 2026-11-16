"""Re-export shim — the ``.gitignore`` matcher moved to :mod:`molab.gitignore`.

It is a cross-layer primitive now: the workspace file browser skips the
same paths git would.
"""

from molab.gitignore import (
    DEFAULT_IGNORE_LINES,
    GitIgnoreMatcher,
    load_gitignore_matcher,
)

__all__ = ["DEFAULT_IGNORE_LINES", "GitIgnoreMatcher", "load_gitignore_matcher"]

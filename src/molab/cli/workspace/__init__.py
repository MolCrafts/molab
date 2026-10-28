"""``molab.cli.workspace`` — workspace command implementations.

Command modules (``run`` / ``serve`` / ``monitor`` / ``explore`` / ``sync`` /
``lifecycle`` / ``resources``) register their commands on the shared top-level
app (:mod:`molab.cli._app`); the flat tree is assembled in :mod:`molab.cli`.
This package no longer owns a Typer group or a target-resolving callback —
target resolution moved to :mod:`molab.cli._target`.
"""

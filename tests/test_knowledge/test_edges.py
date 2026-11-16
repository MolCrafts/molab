"""EdgeRole vocabulary + label-channel encode/parse/validate.

The vocabulary belongs to ``molab.knowledge.edges`` — the OKF layer that owns
the markdown edge format. Moved here from ``tests/test_workspace/`` when the
workspace's forwarder shell went away; the assertions are unchanged.
"""

from __future__ import annotations

import pytest

from molab.knowledge.edges import (
    DEFAULT_EDGE_ROLE,
    encode_label,
    parse_role,
)

ROLES = (
    "derived_from",
    "cites",
    "supports",
    "contradicts",
    "references",
)


@pytest.mark.parametrize("role", ROLES)
def test_encode_parse_round_trip(role: str) -> None:
    encoded = encode_label(role, "my-target")
    assert parse_role(encoded) == (role, "my-target")


def test_the_vocabulary_is_exactly_these_roles() -> None:
    from typing import get_args

    from molab.knowledge.edges import _EDGE_ROLES, EdgeRole

    assert set(get_args(EdgeRole)) == set(ROLES) == set(_EDGE_ROLES)


@pytest.mark.parametrize("role", ["supports", "contradicts"])
def test_evidence_roles_write_the_sigil(role: str) -> None:
    from molab.knowledge.edges import link_line

    assert link_line(encode_label(role, "h1"), "h1.md") == f"- [@{role} h1](h1.md)"


def test_default_role_encodes_to_bare_label() -> None:
    # byte-identical to the pre-role output → on-disk back-compat
    assert encode_label("references", "my-target") == "my-target"


class TestEdge:
    def test_a_ref_target_is_a_ref_and_a_path_is_not(self) -> None:
        from molab.knowledge.edges import Edge

        assert Edge("molab:experiment/E1", "derived_from").is_ref is True
        assert Edge("/w/x", "references").is_ref is False
        assert Edge("/w/x", "references") == ("/w/x", "references")


class TestLinkLine:
    def test_formats_one_list_item(self) -> None:
        from molab.knowledge.edges import link_line

        assert (
            link_line("@derived_from R1", "molab:experiment/E1/run/R1")
            == "- [@derived_from R1](molab:experiment/E1/run/R1)"
        )


class TestBacklink:
    def test_the_tuple_lives_on_edges(self) -> None:
        from molab.knowledge.edges import Backlink

        assert Backlink._fields == ("source", "role")


def test_parse_unrecognized_sigil_is_defaulted_not_dropped() -> None:
    # an unknown sigil token → default role, original label preserved verbatim
    assert parse_role("@mention someone") == (DEFAULT_EDGE_ROLE, "@mention someone")

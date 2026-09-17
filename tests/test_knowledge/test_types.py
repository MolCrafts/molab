"""Tests for the ``molab.knowledge`` concept-type registry.

The registry maps a Concept's ``meta.json`` ``type`` string to its Python
class so a storage layer reconstructs typed Concepts (not bare bases). It is
*open* (upstream layers register their own types) and *forward-compatible*
(unknown types resolve to a supplied default). The registry is process-global,
so these tests use unique type strings to stay isolated.

The registry owns no storage class of its own: these tests use a tiny local
placeholder class to prove the registry works for any caller-supplied type.
"""

from __future__ import annotations

from molab.knowledge.types import (
    register_concept_type,
    resolve_concept_type,
)


class _Concept:
    """Local placeholder standing in for any caller's Concept/Folder class."""


class TestConceptTypeRegistry:
    """The open, forward-compatible concept-type registry (``types.py``)."""

    def test_register_and_resolve_round_trip(self) -> None:
        class CustomRT(_Concept):
            pass

        register_concept_type("test-custom-rt", CustomRT)
        assert resolve_concept_type("test-custom-rt", _Concept) is CustomRT

    def test_unknown_type_resolves_to_default(self) -> None:
        assert resolve_concept_type("totally-unknown-xyz", _Concept) is _Concept

    def test_reregister_same_class_is_noop(self) -> None:
        class Same(_Concept):
            pass

        register_concept_type("test-same", Same)
        register_concept_type("test-same", Same)  # idempotent — must not raise
        assert resolve_concept_type("test-same", _Concept) is Same

    def test_two_families_can_claim_one_type_and_each_resolves_its_own(self) -> None:
        """One type string, two storage families — the ``base`` filter separates them.

        ``workspace`` models a note as a ``Folder`` and ``knowledge`` models it
        as a ``Concept``; both answer ``note.note``. Registration therefore
        records both classes, and each family asks for its own by passing its
        base. Without the filter a walk would receive the other family's class
        and fail to construct it.
        """

        class OtherBase:
            pass

        class FromKnowledge(_Concept):
            pass

        class FromOtherFamily(OtherBase):
            pass

        register_concept_type("test-two-families", FromKnowledge)
        register_concept_type("test-two-families", FromOtherFamily)

        assert resolve_concept_type("test-two-families", _Concept, base=_Concept) is FromKnowledge
        assert (
            resolve_concept_type("test-two-families", OtherBase, base=OtherBase) is FromOtherFamily
        )

    def test_reregistering_the_same_class_is_a_noop(self) -> None:
        class Only(_Concept):
            pass

        register_concept_type("test-idempotent", Only)
        register_concept_type("test-idempotent", Only)

        assert resolve_concept_type("test-idempotent", _Concept, base=_Concept) is Only

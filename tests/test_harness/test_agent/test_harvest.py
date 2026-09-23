"""harvest_session is pinned to Finding."""

from __future__ import annotations

import inspect

from molab.harness.agent import harvest as harvest_mod


class TestHarvestSession:
    def test_no_cls_parameter(self) -> None:
        src = inspect.getsource(harvest_mod.harvest_session)
        assert "cls:" not in src
        assert "of=Finding" in src
        assert "from molab.knowledge import Finding" in inspect.getsource(harvest_mod)

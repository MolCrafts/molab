"""HTTP envelopes for reference errors registered on the FastAPI app."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from molab.server.handlers import register_exception_handlers
from molab.workspace.errors import AmbiguousRefError, RefNotFoundError, UnmigratedAssetError
from molab.workspace.refs import InvalidRefError, MolabRef


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/missing")
    def missing() -> None:
        raise RefNotFoundError(MolabRef(experiment_id="E", run_id="r1"), "run", "r1")

    @app.get("/ambiguous")
    def ambiguous() -> None:
        raise AmbiguousRefError(
            "r1",
            (
                MolabRef(experiment_id="A", run_id="r1"),
                MolabRef(experiment_id="B", run_id="r1"),
            ),
        )

    @app.get("/invalid")
    def invalid() -> None:
        raise InvalidRefError("bad")

    @app.get("/value")
    def value() -> None:
        raise ValueError("nope")

    @app.get("/unmigrated")
    def unmigrated() -> None:
        raise UnmigratedAssetError(
            "/w/assets/x/asset.json", "data-import record", workspace_root="/w"
        )

    @app.get("/ambiguous-locations")
    def ambiguous_locations() -> None:
        raise AmbiguousRefError("x", (), locations=("workspace", "project/p1"))

    with TestClient(app) as http:
        yield http


class TestRegisterExceptionHandlers:
    def test_ref_not_found_is_404(self, client: TestClient) -> None:
        response = client.get("/missing")
        assert response.status_code == 404
        error = response.json()["error"]
        assert error["code"] == "NOT_FOUND"
        assert error["details"]["resource"] == "run"
        assert error["details"]["identifier"] == "r1"
        assert error["details"]["ref"] == "molab:experiment/E/run/r1"

    def test_ambiguous_ref_is_409(self, client: TestClient) -> None:
        response = client.get("/ambiguous")
        assert response.status_code == 409
        error = response.json()["error"]
        assert error["code"] == "CONFLICT"
        assert error["details"]["candidates"] == [
            "molab:experiment/A/run/r1",
            "molab:experiment/B/run/r1",
        ]
        assert "locations" not in error["details"]

    def test_ambiguous_ref_serializes_locations(self, client: TestClient) -> None:
        response = client.get("/ambiguous-locations")
        assert response.status_code == 409
        error = response.json()["error"]
        assert error["code"] == "CONFLICT"
        assert error["details"]["locations"] == ["workspace", "project/p1"]

    def test_invalid_ref_is_422(self, client: TestClient) -> None:
        response = client.get("/invalid")
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "INVALID_REF"

    def test_value_error_is_400(self, client: TestClient) -> None:
        response = client.get("/value")
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    def test_unmigrated_asset_maps_to_409(self, client: TestClient) -> None:
        response = client.get("/unmigrated")
        assert response.status_code == 409
        error = response.json()["error"]
        assert error["code"] == "MIGRATION_REQUIRED"
        assert "molab migrate assets /w" in error["message"]

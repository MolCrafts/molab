"""The isolated operator CLI provisions credentials without exposing them."""

import json

import pytest
from typer.testing import CliRunner

from molab.atomicio import atomic_write_json
from molab.sharing_cli import app


@pytest.fixture
def gateway_config(tmp_path):
    config = tmp_path / "gateway.json"
    atomic_write_json(
        config,
        {
            "issuer": "cluster",
            "proxy_key": "gateway-" + "x" * 32,
            "public_origin": "http://localhost/",
            "state_dir": str(tmp_path / "state"),
            "local_state_confirmed": True,
        },
    )
    return config


def test_provision_source_writes_private_token_and_never_prints_it(gateway_config, tmp_path):
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "principal-add",
            "--config",
            str(gateway_config),
            "--issuer",
            "cluster",
            "--subject",
            "alice",
            "--name",
            "Alice",
        ],
    )
    assert result.exit_code == 0, result.output
    principal = json.loads(result.stdout)
    credential = tmp_path / "source.json"
    source = runner.invoke(
        app,
        [
            "source-add",
            "--config",
            str(gateway_config),
            "--principal",
            principal["id"],
            "--cluster",
            "cluster-a",
            "--uid",
            "1001",
            "--credential-file",
            str(credential),
        ],
    )
    assert source.exit_code == 0, source.output
    token = json.loads(credential.read_text())["source_token"]
    assert token not in source.output
    assert credential.stat().st_mode & 0o777 == 0o600
    rejected = runner.invoke(
        app,
        [
            "source-add",
            "--config",
            str(gateway_config),
            "--principal",
            principal["id"],
            "--cluster",
            "cluster-a",
            "--uid",
            "1001",
            "--credential-file",
            str(credential),
        ],
    )
    assert rejected.exit_code != 0
    assert json.loads(credential.read_text())["source_token"] == token


def test_gateway_launcher_does_not_discover_plugins_or_bind_publicly(gateway_config, monkeypatch):
    observed = {}

    def forbidden():
        pytest.fail("gateway launcher must not discover plugins")

    def launch(application, **kwargs: object):
        observed.update(kwargs)
        assert "/api/workspace/info" not in application.openapi()["paths"]

    monkeypatch.setattr("molab.plugins.discover_cli_plugins", forbidden)
    monkeypatch.setattr("molab.plugins.discover_server_plugins", forbidden)
    monkeypatch.setattr("uvicorn.run", launch)
    result = CliRunner().invoke(app, ["gateway", "--config", str(gateway_config)])
    assert result.exit_code == 0, result.output
    assert observed["host"] == "127.0.0.1"
    assert observed["proxy_headers"] is False


def test_provisioning_rejects_an_untrusted_authentication_issuer(gateway_config):
    result = CliRunner().invoke(
        app,
        [
            "principal-add",
            "--config",
            str(gateway_config),
            "--issuer",
            "other",
            "--subject",
            "alice",
            "--name",
            "Alice",
        ],
    )
    assert result.exit_code != 0

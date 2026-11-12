"""``services.asset_replace`` — new bytes in an existing asset, same id."""

from __future__ import annotations

from pathlib import Path

import pytest

from molab.services.asset_replace import replace_asset
from molab.services.workspace_check import check_path, check_workspace
from molab.workspace import Workspace
from molab.workspace.domain import Asset
from molab.workspace.history import GitHistory


def _product(tmp_path: Path) -> tuple[Workspace, str, Path]:
    ws = Workspace(tmp_path / "ws", name="lab")
    ws.materialize()
    GitHistory(ws.root).init()
    run = ws.add_project("p").add_experiment("e").add_run(params={"seed": 1})
    with run.start() as ctx:
        asset = ctx.register(b"<svg/>\n", title="depiction.svg")
    slot = Path(str(ws.root)) / "projects" / "p" / "experiments" / "e" / "assets"
    (directory,) = [path for path in slot.iterdir() if path.is_dir()]
    return ws, asset.id, directory


def test_replace_keeps_the_id_and_records_history(tmp_path: Path) -> None:
    ws, asset_id, directory = _product(tmp_path)
    source = tmp_path / "depiction.svg"
    source.write_bytes(b"<svg>new</svg>\n")

    replaced = replace_asset(ws, asset_id, source)

    assert replaced.changed is True
    assert replaced.asset.id == asset_id
    assert replaced.asset.title == "depiction.svg"
    assert (directory / "payload.svg").read_bytes() == b"<svg>new</svg>\n"
    found = ws.find(f"molab:asset/{asset_id}")
    assert isinstance(found, Asset)
    assert found.content.digest == replaced.asset.content.digest
    assert check_workspace(ws).error_count == 0
    history = GitHistory(ws.root)
    if history.enabled():
        assert history.latest(entity_id=asset_id, event="AssetReplaced") is not None


def test_replace_by_slot_accepts_a_new_suffix(tmp_path: Path) -> None:
    ws, asset_id, directory = _product(tmp_path)
    original = ws.find(f"molab:asset/{asset_id}")
    assert isinstance(original, Asset)
    previous = original.file
    source = tmp_path / "depiction.png"
    source.write_bytes(b"\x89PNG\n")
    rel = directory.relative_to(Path(str(ws.root))).as_posix()

    replaced = replace_asset(ws, rel, source)

    assert replaced.asset.id == asset_id
    assert replaced.asset.file == "payload.png"
    assert replaced.asset.media_type == "image/png"
    assert previous != "payload.png"
    assert not (directory / previous).exists()
    assert (directory / "payload.png").read_bytes() == b"\x89PNG\n"


def test_the_same_bytes_change_nothing(tmp_path: Path) -> None:
    ws, asset_id, _directory = _product(tmp_path)
    source = tmp_path / "depiction.svg"
    source.write_bytes(b"<svg/>\n")

    replaced = replace_asset(ws, f"molab:asset/{asset_id}", source)

    assert replaced.changed is False
    assert GitHistory(ws.root).latest(entity_id=asset_id, event="AssetReplaced") is None


def test_bytes_owned_by_another_asset_are_refused(tmp_path: Path) -> None:
    ws, asset_id, directory = _product(tmp_path)
    original = ws.find(f"molab:asset/{asset_id}")
    assert isinstance(original, Asset)
    with ws.project("p").experiment("e").add_run(params={"seed": 2}).start() as ctx:
        other = ctx.register(b"other\n", title="other.svg")
    source = tmp_path / "copy.svg"
    source.write_bytes(b"other\n")

    with pytest.raises(ValueError, match=other.ref):
        replace_asset(ws, asset_id, source)

    assert sorted(path.name for path in directory.iterdir()) == sorted(
        ["asset.json", original.file]
    )
    assert (directory / original.file).read_bytes() == b"<svg/>\n"
    found = ws.find(f"molab:asset/{asset_id}")
    assert isinstance(found, Asset)
    assert found.file == original.file
    assert found.content.digest == original.content.digest
    assert found.content.digest != other.content.digest


def test_a_log_is_refused(tmp_path: Path) -> None:
    ws, asset_id, _directory = _product(tmp_path)
    source = tmp_path / "run.log"
    source.write_text("step 1\n")

    with pytest.raises(ValueError, match="log"):
        replace_asset(ws, asset_id, source)


def test_editing_an_existing_slot_points_at_replace(tmp_path: Path) -> None:
    ws, asset_id, directory = _product(tmp_path)
    asset = ws.find(f"molab:asset/{asset_id}")
    assert isinstance(asset, Asset)
    payload = directory / asset.file

    verdict = check_path(payload, "write", "<svg>hand</svg>\n")

    assert verdict.allowed is False
    assert verdict.rule == "asset.owned"
    assert verdict.path is not None
    slot = verdict.path.rsplit("/", 1)[0]
    assert verdict.command == f"molab asset replace {slot} SRC"
    assert slot.endswith(directory.name)


@pytest.mark.parametrize("failure", ["copy", "record", "install"])
def test_failed_replacement_preserves_the_old_slot(tmp_path: Path, monkeypatch, failure) -> None:
    ws, asset_id, directory = _product(tmp_path)
    original_record = (directory / "asset.json").read_bytes()
    original = ws.find(f"molab:asset/{asset_id}")
    assert isinstance(original, Asset)
    source = tmp_path / "new.svg"
    source.write_bytes(b"<svg>new</svg>\n")

    def fail(*_args: object, **_kwargs: object):
        raise OSError("injected failure")

    if failure == "copy":
        monkeypatch.setattr("molab.workspace.asset_repository.shutil.copy2", fail)
    elif failure == "record":
        monkeypatch.setattr(ws.fs, "atomic_write_json", fail)
    else:
        move = ws.fs.mv

        def fail_install(src, dst):
            if Path(src).name == "new":
                raise OSError("injected failure")
            move(src, dst)

        monkeypatch.setattr(ws.fs, "mv", fail_install)

    with pytest.raises(OSError, match="injected failure"):
        replace_asset(ws, asset_id, source)

    assert (directory / "asset.json").read_bytes() == original_record
    payload = ws.assets_at(original.scope).payload_path(asset_id)
    assert Path(payload).read_bytes() == b"<svg/>\n"
    assert sorted(p.name for p in directory.iterdir()) == ["asset.json", original.file]
    assert list((Path(str(ws.root)) / ".molab" / "asset-replacements").iterdir()) == []
    assert GitHistory(ws.root).latest(entity_id=asset_id, event="AssetReplaced") is None


def test_a_copy_digest_mismatch_preserves_the_old_slot(tmp_path: Path, monkeypatch) -> None:
    ws, asset_id, directory = _product(tmp_path)
    source = tmp_path / "new.svg"
    source.write_bytes(b"<svg>new</svg>\n")

    def corrupt_copy(_source, dest):
        Path(dest).write_bytes(b"corrupt")

    monkeypatch.setattr("molab.workspace.asset_repository.shutil.copy2", corrupt_copy)
    with pytest.raises(ValueError, match="copied bytes"):
        replace_asset(ws, asset_id, source)

    asset = ws.find(f"molab:asset/{asset_id}")
    assert isinstance(asset, Asset)
    assert Path(ws.assets_at(asset.scope).payload_path(asset_id)).read_bytes() == b"<svg/>\n"
    assert sorted(p.name for p in directory.iterdir()) == ["asset.json", asset.file]


@pytest.mark.parametrize("directory_first", [True, False])
def test_replacement_can_change_between_a_directory_and_an_extensionless_file(
    tmp_path: Path, directory_first: bool
) -> None:
    ws = Workspace(tmp_path / "ws", name="lab")
    ws.materialize()
    directory = tmp_path / "bundle"
    directory.mkdir()
    (directory / "a.txt").write_text("directory content", encoding="utf-8")
    file = tmp_path / "single"
    file.write_bytes(b"file content")
    original, replacement = (directory, file) if directory_first else (file, directory)
    asset = ws.assets.import_asset("bundle", original)

    replaced = replace_asset(ws, asset.id, replacement)

    payload = Path(ws.assets.payload_path(asset.id))
    assert replaced.asset.id == asset.id
    assert replaced.asset.file == "payload"
    if directory_first:
        assert payload.read_bytes() == b"file content"
        assert replaced.asset.content.kind == "file"
    else:
        assert (payload / "a.txt").read_text(encoding="utf-8") == "directory content"
        assert replaced.asset.content.kind == "directory"

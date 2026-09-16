"""``molexp knowledge ...`` — the CLI over the OKF library.

Driven through Typer's ``CliRunner`` so the tests exercise what a user actually
types, including the two things that are easy to get wrong at the boundary:
a wiki that is **not** a workspace, and a query in Chinese.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from molexp.cli.knowledge_cmd import knowledge_app

runner = CliRunner()

QUESTION = "计算Tg的时候升降温怎么选择"


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point ``~/.molexp`` at a tmp dir — never touch the developer's real config."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: home))
    import molexp.knowledge.sources as sources

    monkeypatch.setattr(sources, "USER_DIR", home / ".molexp")


@pytest.fixture(autouse=True)
def _wide_console(monkeypatch: pytest.MonkeyPatch) -> None:
    """Render rich tables at a fixed wide width.

    Rich falls back to 80 columns when stdout is not a terminal (which it never
    is under ``CliRunner``), so a ``<source>:<path>`` ref folds across lines and
    assertions would end up testing column widths rather than behaviour. The CLI
    folds rather than truncates such a ref, which is the property that matters on
    a real narrow terminal; here we simply give it room.
    """
    import rich
    from rich.console import Console

    # Both dimensions must be pinned: given width alone, rich re-detects the
    # size from the (non-terminal) stream and falls back to 80 anyway.
    monkeypatch.setattr(rich, "get_console", lambda: Console(width=300, height=50))


@pytest.fixture
def wiki(tmp_path: Path) -> Path:
    """A group wiki: an OKF bundle with no workspace anywhere near it."""
    root = tmp_path / "lab-wiki"
    (root / "tg-protocol").mkdir(parents=True)
    (root / "tg-protocol" / "meta.yaml").write_text(
        "type: note.note\nid: tg-protocol\ntags: [Tg]\n", encoding="utf-8"
    )
    (root / "tg-protocol" / "index.md").write_text(
        "# 玻璃化转变温度 Tg 的模拟流程\n\n## 降温速率的选择\n本组约定以 1 K/ns 降温至 200 K。\n",
        encoding="utf-8",
    )
    return root


def _register(wiki: Path, name: str = "lab-wiki") -> None:
    result = runner.invoke(knowledge_app, ["sources", "add", name, str(wiki)])
    assert result.exit_code == 0, result.output


class TestSourcesCommands:
    def test_add_then_list_shows_the_wiki(self, wiki: Path) -> None:
        _register(wiki)
        result = runner.invoke(knowledge_app, ["sources", "list"])
        assert result.exit_code == 0
        assert "lab-wiki" in result.output

    def test_list_with_nothing_registered_says_how_to_add_one(self) -> None:
        result = runner.invoke(knowledge_app, ["sources", "list"])
        assert result.exit_code == 0
        assert "No knowledge sources registered" in result.output
        assert "sources add" in result.output

    def test_add_rejects_an_unusable_name(self, wiki: Path) -> None:
        result = runner.invoke(knowledge_app, ["sources", "add", "Lab Wiki!", str(wiki)])
        assert result.exit_code == 1
        assert "invalid source name" in result.output

    def test_add_warns_when_the_directory_is_absent(self, tmp_path: Path) -> None:
        # Legal (an unmounted share), but the user should hear about it.
        result = runner.invoke(knowledge_app, ["sources", "add", "later", str(tmp_path / "nope")])
        assert result.exit_code == 0
        assert "does not exist yet" in result.output

    def test_remove_unregisters_without_touching_files(self, wiki: Path) -> None:
        _register(wiki)
        result = runner.invoke(knowledge_app, ["sources", "remove", "lab-wiki"])
        assert result.exit_code == 0
        assert (wiki / "tg-protocol" / "index.md").is_file()
        assert "lab-wiki" not in runner.invoke(knowledge_app, ["sources", "list"]).output

    def test_remove_of_an_unknown_name_fails_loudly(self) -> None:
        result = runner.invoke(knowledge_app, ["sources", "remove", "ghost"])
        assert result.exit_code == 1
        assert "no user knowledge source" in result.output

    def test_workspace_scope_without_a_workspace_is_refused(self, wiki: Path) -> None:
        result = runner.invoke(knowledge_app, ["sources", "add", "w", str(wiki), "--workspace"])
        assert result.exit_code == 1
        assert "workspace" in result.output.lower()


class TestInit:
    def test_creates_a_bundle_in_a_plain_directory(self, tmp_path: Path) -> None:
        target = tmp_path / "new-wiki"
        target.mkdir()
        result = runner.invoke(knowledge_app, ["init", str(target)])
        assert result.exit_code == 0
        assert (target / "meta.yaml").is_file()
        assert (target / "index.md").is_file()

    def test_is_idempotent(self, tmp_path: Path) -> None:
        target = tmp_path / "new-wiki"
        target.mkdir()
        runner.invoke(knowledge_app, ["init", str(target)])
        (target / "index.md").write_text("# Kept\n", encoding="utf-8")
        result = runner.invoke(knowledge_app, ["init", str(target)])
        assert result.exit_code == 0
        assert (target / "index.md").read_text(encoding="utf-8") == "# Kept\n"


class TestSearch:
    def test_a_chinese_question_finds_the_note_that_answers_it(self, wiki: Path) -> None:
        _register(wiki)
        result = runner.invoke(knowledge_app, ["search", QUESTION])
        assert result.exit_code == 0
        assert "tg-protocol" in result.output

    def test_reports_which_source_a_hit_came_from(self, wiki: Path) -> None:
        _register(wiki)
        result = runner.invoke(knowledge_app, ["search", "降温速率"])
        assert "lab-wiki" in result.output

    def test_no_match_says_so_without_failing(self, wiki: Path) -> None:
        _register(wiki)
        result = runner.invoke(knowledge_app, ["search", "quantum chromodynamics"])
        assert result.exit_code == 0
        assert "No knowledge matches" in result.output

    def test_restricting_to_another_source_excludes_the_wiki(self, wiki: Path) -> None:
        _register(wiki)
        result = runner.invoke(knowledge_app, ["search", "降温速率", "--source", "somewhere-else"])
        assert "No knowledge matches" in result.output

    def test_searching_with_nothing_registered_explains_why(self, tmp_path: Path) -> None:
        result = runner.invoke(knowledge_app, ["search", "anything"])
        assert result.exit_code == 0
        assert "No knowledge sources are registered" in result.output


class TestRead:
    def test_prints_the_whole_markdown_body(self, wiki: Path) -> None:
        _register(wiki)
        result = runner.invoke(knowledge_app, ["read", "lab-wiki:tg-protocol"])
        assert result.exit_code == 0
        assert "1 K/ns 降温至 200 K" in result.output

    def test_reports_the_file_path_so_a_caller_can_open_it(self, wiki: Path) -> None:
        _register(wiki)
        result = runner.invoke(knowledge_app, ["read", "lab-wiki:tg-protocol"])
        assert "index.md" in result.output

    def test_unknown_source_fails_with_a_usable_message(self, wiki: Path) -> None:
        _register(wiki)
        result = runner.invoke(knowledge_app, ["read", "ghost:tg-protocol"])
        assert result.exit_code == 1
        assert "no knowledge source named" in result.output

    def test_unknown_concept_points_back_at_search(self, wiki: Path) -> None:
        _register(wiki)
        result = runner.invoke(knowledge_app, ["read", "lab-wiki:not-a-note"])
        assert result.exit_code == 1
        assert "knowledge search" in result.output

    def test_bare_path_outside_a_workspace_is_refused(self, wiki: Path) -> None:
        _register(wiki)
        result = runner.invoke(knowledge_app, ["read", "tg-protocol"])
        assert result.exit_code == 1
        assert "not a workspace" in result.output

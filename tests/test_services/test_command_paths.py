"""Shell destinations. The grammar used to live in the harness hook."""

from __future__ import annotations

import os
from pathlib import Path

from molab.services.command_paths import destinations

CWD = "/ws"


def _at(command: str, cwd: str = CWD) -> list[str] | None:
    return destinations(command, cwd)


class TestDestinations:
    def test_cd_then_move_uses_the_new_directory(self) -> None:
        found = _at("cd projects/p/experiments/e && mv /tmp/a.py plot.py")
        assert found == ["/ws/projects/p/experiments/e/plot.py"]

    def test_git_mv_in_another_directory_uses_that_directory(self) -> None:
        found = _at("git -C projects/p/experiments/e mv a.py plot.py")
        assert found == ["/ws/projects/p/experiments/e/plot.py"]

    def test_a_redirect_without_spaces_is_a_destination(self) -> None:
        assert _at("echo hi>projects/p/index.md") == ["/ws/projects/p/index.md"]

    def test_a_redirect_to_a_file_is_kept_and_a_dup_is_not(self) -> None:
        found = _at("echo hi > projects/p/experiments/e/out.py 2>&1")
        assert found == ["/ws/projects/p/experiments/e/out.py"]
        assert "/ws/1" not in (found or [])

    def test_touch_t_is_a_time_stamp_not_a_destination(self) -> None:
        found = _at("touch -t 202601011200 projects/p/index.md")
        assert found is not None
        assert "/ws/projects/p/index.md" in found
        assert "/ws/202601011200" not in found

    def test_sed_in_place_edits_are_destinations(self) -> None:
        assert "/ws/projects/p/index.md" in (_at("sed -i 's/a/b/' projects/p/index.md") or [])
        assert _at("sed -i.bak -e 's/a/b/' -e 's/c/d/' b.md") == ["/ws/b.md"]
        assert "/ws/c.md" not in (_at("sed 's/a/b/' c.md") or [])
        assert _at("perl -pi -e 's/a/b/' d.md") == ["/ws/d.md"]

    def test_wrappers_and_assignments_are_seen_through(self) -> None:
        assert _at("FOO=1 env -u BAR sudo -u me cp /tmp/a.py x/a.py") == ["/ws/x/a.py"]

    def test_a_subshell_cd_does_not_leak(self) -> None:
        found = _at("(cd projects/p && touch a.txt) && touch b.txt")
        assert found == ["/ws/projects/p/a.txt", "/ws/b.txt"]

    def test_variables_are_expanded_or_the_path_is_left_out(self) -> None:
        found = _at("S=/tmp/x; mkdir -p $S/deck && touch ${HOME}/a && cp a $UNSET_GUARD_VAR/b")
        assert found is not None
        assert "/tmp/x/deck" in found
        assert str(Path(os.environ["HOME"]) / "a") in found
        assert not any("$" in path for path in found)
        assert _at("D=d; cd $D && touch e.txt") == ["/ws/d/e.txt"]

    def test_a_heredoc_body_is_data_not_commands(self) -> None:
        found = _at(
            "cat > /tmp/x.js <<'EOF'\n// a -> deck/index.html\necho hi > body.txt\nEOF\ntouch after.txt"
        )
        assert found == ["/tmp/x.js", "/ws/after.txt"]
        assert _at("cat <<-END > t.txt\n\tline > no.txt\n\tEND") == ["/ws/t.txt"]

    def test_mkdir_names_every_directory(self) -> None:
        assert _at("mkdir -p scratch/a scratch/b") == ["/ws/scratch/a", "/ws/scratch/b"]

    def test_an_unparsed_command_is_none(self) -> None:
        assert _at("mv 'unterminated") is None

    def test_a_command_with_no_file_is_an_empty_list(self) -> None:
        assert _at("echo hi") == []

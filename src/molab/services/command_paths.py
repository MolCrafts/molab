"""Destination paths of a shell command.

A hook forwards the command string. This module names the files that command
would write, so the layout rules stay in :func:`molab.services.workspace_check.check_command`.
A command this grammar cannot read returns ``None``; the session's stop check
then sees what it actually wrote. ``cd`` changes the base for the following
segment. A command that writes no file returns an empty list.
"""

from __future__ import annotations

import os
import re
import shlex

__all__ = ["destinations"]

# Options that take the next token. -t / --target-directory is the destination.
_ARG_FLAGS = {
    "mv": {"-t", "--target-directory", "-S", "--suffix"},
    "cp": {"-t", "--target-directory", "-S", "--suffix"},
    "ln": {"-t", "--target-directory", "-S", "--suffix"},
    "install": {
        "-t",
        "--target-directory",
        "-m",
        "--mode",
        "-o",
        "--owner",
        "-g",
        "--group",
        "-S",
        "--suffix",
    },
    "mkdir": {"-m", "--mode", "-Z", "--context"},
    "touch": {"-d", "--date", "-r", "--reference", "-t"},
    "tee": set(),
    "rsync": {"-e", "--rsh"},
}
_TARGET_FLAGS = {"-t", "--target-directory"}
# Only these read -t as the destination; touch -t is a time stamp.
_TARGET_COMMANDS = {"mv", "cp", "ln", "install"}
_LAST_DEST = {"mv", "cp", "ln", "install", "rsync"}
# Words that run the command after them.
_WRAPPERS = {"env", "command", "nohup", "time", "exec", "sudo", "builtin"}
_WRAPPER_ARGS = {"sudo": {"-u", "-g", "-C", "-h", "-p"}, "env": {"-u", "-C", "-S"}}
_ALL_DEST = {"mkdir", "touch", "tee"}
_NOT_A_FILE = {"/dev/null", "/dev/stdout", "/dev/stderr", "/dev/fd/1", "/dev/fd/2"}
_REDIRECT = re.compile(r"\d*&>>|\d*&>|\d*>>|\d*>\||\d*>")
_HEREDOC = re.compile(r"<<(-?)\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\2")


def _absolute(path: str, cwd: str) -> str:
    """*path* joined onto *cwd* when it is relative."""
    path = os.path.expanduser(path)
    if not os.path.isabs(path):
        path = os.path.join(cwd, path)
    return os.path.normpath(path)


def _skip_heredocs(command, i, pending):
    """Index after the bodies of *pending* here-documents, which start at *i* (after a newline)."""
    n = len(command)
    for strip_tabs, word in pending:
        while i < n:
            end = command.find("\n", i)
            end = n if end < 0 else end
            line = command[i:end]
            i = end + 1
            if (line.lstrip("\t") if strip_tabs else line) == word:
                break
    return i


def _split_segments(command):
    parts = []
    buf = []
    i = 0
    n = len(command)
    quote = None
    pending = []  # here-documents whose bodies start after the next newline
    while i < n:
        char = command[i]
        if not quote and command.startswith("<<", i) and not command.startswith("<<<", i):
            heredoc = _HEREDOC.match(command, i)
            if heredoc:
                pending.append((heredoc.group(1) == "-", heredoc.group(3)))
                buf.append(command[i : heredoc.end()])
                i = heredoc.end()
                continue
        if not quote and char == "\n" and pending:
            # the body is data for the command, not commands: skip it
            parts.append("".join(buf))
            buf = []
            i = _skip_heredocs(command, i + 1, pending)
            pending = []
            continue
        if quote:
            buf.append(char)
            if char == "\\" and quote == '"' and i + 1 < n:
                buf.append(command[i + 1])
                i += 2
                continue
            if char == quote:
                quote = None
            i += 1
            continue
        if char in "'\"":
            quote = char
            buf.append(char)
            i += 1
            continue
        if char == "\\" and i + 1 < n:
            buf.append(char)
            buf.append(command[i + 1])
            i += 2
            continue
        if (char == "&" and (buf and buf[-1] in "<>" or command.startswith("&>", i))) or (
            char == "|" and buf and buf[-1] == ">"
        ):
            # part of a redirection (2>&1, &>file, >|file), not a separator
            buf.append(char)
            i += 1
            continue
        if command.startswith("&&", i) or command.startswith("||", i):
            parts.append("".join(buf))
            buf = []
            i += 2
            continue
        if char in ";\n|&":
            parts.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(char)
        i += 1
    if quote:
        return None
    parts.append("".join(buf))
    return parts


def _read_word(text, i):
    n = len(text)
    while i < n and text[i].isspace():
        i += 1
    if i >= n:
        return "", i
    buf = []
    quote = None
    while i < n:
        char = text[i]
        if quote:
            if char == quote:
                quote = None
                i += 1
                continue
            if char == "\\" and quote == '"' and i + 1 < n:
                buf.append(text[i + 1])
                i += 2
                continue
            buf.append(char)
            i += 1
            continue
        if char.isspace() or char in ";&|<>()":
            break
        if char in "'\"":
            quote = char
            i += 1
            continue
        if char == "\\" and i + 1 < n:
            buf.append(text[i + 1])
            i += 2
            continue
        buf.append(char)
        i += 1
    if quote:
        return None
    return "".join(buf), i


def _peel_redirects(segment):
    cleaned = []
    targets = []
    i = 0
    n = len(segment)
    quote = None
    while i < n:
        char = segment[i]
        if quote:
            cleaned.append(char)
            if char == "\\" and quote == '"' and i + 1 < n:
                cleaned.append(segment[i + 1])
                i += 2
                continue
            if char == quote:
                quote = None
            i += 1
            continue
        if char in "'\"":
            quote = char
            cleaned.append(char)
            i += 1
            continue
        if char == "\\" and i + 1 < n:
            cleaned.append(char)
            cleaned.append(segment[i + 1])
            i += 2
            continue
        matched = _REDIRECT.match(segment, i)
        boundary = i == 0 or segment[i - 1].isspace() or segment[i - 1] in ";&|(){}"
        # `echo hi>f` redirects too; only digits inside a word (`a2>f`) are no fd.
        if matched and (boundary or not char.isdigit()):
            j = matched.end()
            if j < n and segment[j] == "&":
                i = j + 1
                while i < n and not segment[i].isspace():
                    i += 1
                continue
            word = _read_word(segment, j)
            if word is None:
                return None
            target, i = word
            if target and target not in _NOT_A_FILE:
                targets.append(target)
            cleaned.append(" ")
            continue
        cleaned.append(char)
        i += 1
    if quote:
        return None
    return "".join(cleaned), targets


def _split_args(args, takes_arg, target_flags=frozenset()):
    positional = []
    targeted = []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--":
            positional.extend(args[i + 1 :])
            break
        if arg.startswith("--"):
            name, eq, value = arg.partition("=")
            if name in takes_arg:
                got = value if eq else (args[i + 1] if not eq and i + 1 < len(args) else None)
                if name in target_flags and got:
                    targeted.append(got)
                i += 1 if eq or got is None else 2
                continue
            i += 1
            continue
        if arg.startswith("-") and arg != "-":
            letters = arg[1:]
            consume = False
            for index, letter in enumerate(letters):
                flag = "-" + letter
                if flag not in takes_arg:
                    continue
                rest = letters[index + 1 :]
                if flag in target_flags:
                    if rest:
                        targeted.append(rest)
                    elif i + 1 < len(args):
                        targeted.append(args[i + 1])
                        consume = True
                elif not rest:
                    consume = True
                break
            i += 2 if consume else 1
            continue
        positional.append(arg)
        i += 1
    return positional, targeted


def _inplace_files(args, script_letters, arg_letters, long_script, long_arg):
    """Files a ``sed -i`` / ``perl -i`` edits in place; [] without ``-i``.

    Without an ``-e``/``-f`` style script the first operand is the script.
    """
    files = []
    in_place = False
    script_given = False
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--":
            files.extend(args[i + 1 :])
            break
        if arg.startswith("--"):
            name, eq, _value = arg.partition("=")
            if name == "--in-place":
                in_place = True
            elif name in long_script:
                script_given = True
                i += 0 if eq else 1
            elif name in long_arg and not eq:
                i += 1
        elif arg.startswith("-") and arg != "-":
            for index, letter in enumerate(arg[1:]):
                last = index == len(arg) - 2
                if letter == "i":  # the rest is a backup suffix
                    in_place = True
                    break
                if letter in script_letters:
                    script_given = True
                    i += 1 if last else 0
                    break
                if letter in arg_letters:
                    i += 1 if last else 0
                    break
        else:
            files.append(arg)
        i += 1
    if not in_place:
        return []
    return files if script_given else files[1:]


_VAR = re.compile(r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))")


def _expand(path, variables):
    """*path* with ``$NAME`` / ``${NAME}`` filled in, or None when something stays unknown.

    Names come from assignments earlier in the same command, then the hook's
    environment. A path still holding ``$`` or a backtick cannot be checked
    before the command runs; the stop check sees what it made.
    """

    def fill(match):
        name = match.group(1) or match.group(2)
        value = variables.get(name, os.environ.get(name))
        return match.group(0) if value is None else value

    expanded = _VAR.sub(fill, path)
    return None if "$" in expanded or "`" in expanded else expanded


def _unwrap(argv):
    """*argv* without leading ``VAR=value`` words and wrappers (``env``, ``sudo``, ``nohup`` …)."""
    argv = list(argv)
    while argv:
        word = argv[0]
        if "=" in word and not word.startswith(("-", "=")) and word.split("=", 1)[0].isidentifier():
            argv.pop(0)
            continue
        base = os.path.basename(word)
        if base not in _WRAPPERS:
            break
        argv.pop(0)
        takes = _WRAPPER_ARGS.get(base, set())
        while argv and argv[0].startswith("-") and argv[0] != "-":
            flag = argv.pop(0)
            if flag in takes and argv:
                argv.pop(0)
    return argv


def _command_dests(argv):
    argv = _unwrap(argv)
    if not argv:
        return []
    base = os.path.basename(argv[0])
    args = argv[1:]
    if base == "sed":
        return _inplace_files(args, "ef", "l", {"--expression", "--file"}, {"--line-length"})
    if base == "perl":
        return _inplace_files(args, "eE", "", set(), set())
    if base not in _ARG_FLAGS:
        return []
    targets = _TARGET_FLAGS if base in _TARGET_COMMANDS else frozenset()
    positional, targeted = _split_args(args, _ARG_FLAGS[base], targets)
    if targeted:
        return targeted
    if base in _ALL_DEST:
        return positional
    if base in _LAST_DEST and len(positional) >= 2:
        return [positional[-1]]
    return []


def _next_cwd(argv, cwd):
    positional, _targeted = _split_args(argv[1:], set())
    chosen = [item for item in positional if item != "-"]
    if len(chosen) != 1:
        return cwd
    return _absolute(chosen[0], cwd)


def destinations(command: str, cwd: str) -> list[str] | None:
    """Destination paths of a shell command, or None when the command cannot be parsed.

    Only paths that receive a file are returned. ``cd`` changes the base for
    the following segment. A command with no such path returns an empty list.
    """
    segments = _split_segments(command)
    if segments is None:
        return None
    found = []
    here = cwd
    outer = []  # cwd to restore when a `( … )` subshell closes
    variables = {}  # NAME=value set earlier in this command
    for segment in segments:
        peeled = _peel_redirects(segment)
        if peeled is None:
            return None
        cleaned, targets = peeled
        try:
            argv = shlex.split(cleaned, posix=True)
        except ValueError:
            return None
        for target in targets:
            found.append((target, here))
        while argv and argv[0].startswith(("(", "{")):
            if argv[0].startswith("("):
                outer.append(here)
            argv[0] = argv[0][1:]
            if not argv[0]:
                argv.pop(0)
        closing = 0
        while argv and argv[-1].endswith((")", "}")):
            closing += argv[-1].endswith(")")
            argv[-1] = argv[-1][:-1]
            if not argv[-1]:
                argv.pop()
        assigned = 0
        for word in argv:
            name, eq, value = word.partition("=")
            if not eq or not name.isidentifier():
                break
            variables[name] = _expand(value, variables) or value
            assigned += 1
        if argv[assigned:] and os.path.basename(argv[assigned]) == "export":
            for word in argv[assigned + 1 :]:
                name, eq, value = word.partition("=")
                if eq and name.isidentifier():
                    variables[name] = _expand(value, variables) or value
        argv = _unwrap(argv)
        if not argv:
            for _ in range(closing):
                here = outer.pop() if outer else here
            continue
        if os.path.basename(argv[0]) in ("cd", "pushd"):
            moved = [_expand(word, variables) for word in argv]
            here = _next_cwd(moved, here) if None not in moved else here
            for _ in range(closing):
                here = outer.pop() if outer else here
            continue
        if os.path.basename(argv[0]) == "git":
            base = here
            args = argv[1:]
            index = 0
            while index < len(args) and args[index] != "mv":
                if args[index] == "-C" and index + 1 < len(args):
                    base = _absolute(args[index + 1], here)
                    index += 2
                    continue
                index += 1
            if index < len(args) and args[index] == "mv":
                for target in _command_dests(["mv", *args[index + 1 :]]):
                    found.append((target, base))
            continue
        for target in _command_dests(argv):
            found.append((target, here))
        for _ in range(closing):
            here = outer.pop() if outer else here
    seen = set()
    unique = []
    for target, base in found:
        expanded = _expand(target, variables)
        if expanded is None:
            continue
        path = _absolute(expanded, base)
        if path not in seen:
            seen.add(path)
            unique.append(path)
    return unique

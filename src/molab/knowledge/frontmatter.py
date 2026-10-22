"""YAML-subset frontmatter for Knowledge markdown files.

Stdlib only. Understands the keys Knowledge actually writes: scalars,
``tags: [a, b]``, and ``sources:`` as a list of ``{kind, ref}`` maps.
Broken YAML is returned as empty meta so a bad header never 500s a walk.
"""

from __future__ import annotations

_FENCE = "---"


def split_frontmatter(text: str) -> tuple[dict[str, object], str]:
    """Split *text* into ``(meta, body)``. No fence → empty meta + full text."""
    if not text.startswith(_FENCE):
        return {}, text
    rest = text[len(_FENCE) :]
    if rest.startswith("\n"):
        rest = rest[1:]
    end = rest.find(f"\n{_FENCE}")
    if end < 0:
        return {}, text
    raw = rest[:end]
    body = rest[end + len(f"\n{_FENCE}") :].lstrip("\n")
    try:
        return _parse_yaml(raw), body
    except (ValueError, KeyError):
        return {}, text


def dump_frontmatter(meta: dict[str, object], body: str) -> str:
    """Render *meta* + *body* as a markdown file with a YAML fence."""
    cleaned = {k: v for k, v in meta.items() if v is not None and v != "" and v != []}
    if not cleaned:
        return body if body.endswith("\n") or body == "" else body + "\n"
    lines = [_FENCE, *_dump_yaml(cleaned), _FENCE, ""]
    if body and not body.endswith("\n"):
        body = body + "\n"
    return "\n".join(lines) + body


def _parse_yaml(raw: str) -> dict[str, object]:
    meta: dict[str, object] = {}
    lines = raw.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip() or line.lstrip().startswith("#"):
            i += 1
            continue
        if line.startswith((" ", "\t")):
            i += 1
            continue
        if ":" not in line:
            i += 1
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if value == "":
            block, i = _parse_list_block(lines, i + 1)
            meta[key] = block
            continue
        meta[key] = _parse_scalar(value)
        i += 1
    return meta


def _parse_list_block(lines: list[str], start: int) -> tuple[list[object], int]:
    items: list[object] = []
    i = start
    current: dict[str, object] | None = None
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if not line.startswith((" ", "\t", "-")):
            break
        stripped = line.strip()
        if stripped.startswith("- "):
            payload = stripped[2:].strip()
            if current is not None:
                items.append(current)
            if ":" in payload:
                k, _, v = payload.partition(":")
                current = {k.strip(): _parse_scalar(v.strip())}
            else:
                items.append(_parse_scalar(payload))
                current = None
            i += 1
            continue
        if current is not None and ":" in stripped:
            k, _, v = stripped.partition(":")
            current[k.strip()] = _parse_scalar(v.strip())
        i += 1
    if current is not None:
        items.append(current)
    return items, i


def _parse_scalar(value: str) -> object:
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(part.strip()) for part in inner.split(",")]
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    if value.isdigit() or (value.startswith("-") and value[1:].isdigit()):
        return int(value)
    return value


def _dump_yaml(meta: dict[str, object]) -> list[str]:
    lines: list[str] = []
    for key, value in meta.items():
        if isinstance(value, list) and value and isinstance(value[0], dict):
            lines.append(f"{key}:")
            for row in value:
                if not isinstance(row, dict):
                    continue
                first = True
                for rk, rv in row.items():
                    if rv is None:
                        continue
                    prefix = "- " if first else "  "
                    first = False
                    lines.append(f"  {prefix}{rk}: {_dump_scalar(rv)}")
            continue
        if isinstance(value, list):
            inner = ", ".join(_dump_scalar(v) for v in value)
            lines.append(f"{key}: [{inner}]")
            continue
        lines.append(f"{key}: {_dump_scalar(value)}")
    return lines


def _dump_scalar(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    text = str(value)
    if text == "" or any(ch in text for ch in ":#{}[]&*!|>%@`"):
        return json_quote(text)
    if text.lower() in {"true", "false", "null"}:
        return json_quote(text)
    return text


def json_quote(text: str) -> str:
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'

"""One knowledge document as a standalone HTML page — to read it, or to hand it on.

``molab knowledge serve DOC`` renders the document the way a reader sees it:
the markdown body (or an HTML document's ``<molab-markdown>`` blocks), with
every ``molab:asset/<id>`` image shown in place. Nothing needs the web UI.

* :func:`render_page` turns one document into one HTML page. How an asset is
  addressed is the caller's: the server links ``/asset/<id>``, an export
  inlines the bytes as a ``data:`` URI, so the exported file stands alone.
* :func:`serve` answers ``/view/<path>`` by rendering the file again on every
  request — edit, reload — and ``/asset/<id>`` from the asset's slot.

What the page shows:

* Markdown (CommonMark + tables), with MkDocs-style admonitions
  (``!!! type "Title"`` and an indented body) and ``::molab-…`` component
  lines shown as labelled placeholders — they are live only in molab's UI.
* Links: ``molab:asset/<id>`` opens the asset; a relative link to another
  knowledge document in the workspace opens that document here; other
  ``molab:`` refs stay as plain text.
* The trailing ``- [@role …](…)`` source lines become a small "Sources" list.

Raw HTML in a markdown body is shown as text, not executed.
"""

from __future__ import annotations

import base64
import html
import mimetypes
import posixpath
import re
import textwrap
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from http.server import ThreadingHTTPServer

    from markdown_it import MarkdownIt

    from molab.workspace import Workspace

__all__ = ["RenderedPage", "export_page", "render_page", "serve"]

ASSET_REF = re.compile(r"^molab:asset/([0-9a-fA-F-]{8,})$")
_ADMONITION = re.compile(r'^(!!!|\?\?\?\+?)\s+([A-Za-z]+)(?:\s+"([^"]*)")?\s*$')
_COMPONENT = re.compile(r"^::(molab-[a-z][a-z0-9-]*)(?:\{(.*)\})?\s*$")
_SOURCE_LINE = re.compile(r"^- \[@[a-z_]+ ")
_MARKDOWN_BLOCK = re.compile(r"<molab-markdown>(.*?)</molab-markdown>", re.S)
_ELEMENT = re.compile(r"<(molab-[a-z][a-z0-9-]*)\b([^>]*)>\s*</\1>", re.S)

#: Admonition colors by MkDocs type (title tint, border).
_ADMONITION_COLORS = {
    "note": "#2f62b5",
    "abstract": "#1f7a8c",
    "summary": "#1f7a8c",
    "info": "#2f62b5",
    "tip": "#2e7d4f",
    "success": "#2e7d4f",
    "question": "#2f62b5",
    "warning": "#9a6a10",
    "failure": "#b0442b",
    "danger": "#b0442b",
    "bug": "#b0442b",
    "example": "#5a4fb0",
    "quote": "#5c5c5c",
}


@dataclass(frozen=True)
class RenderedPage:
    """One rendered document and the assets its page refers to."""

    html: str
    title: str
    asset_ids: tuple[str, ...]


def _markdown() -> MarkdownIt:
    from markdown_it import MarkdownIt

    return MarkdownIt("commonmark", {"html": False}).enable("table")


def _split_sources(body: str) -> tuple[str, list[str]]:
    """The body without its trailing ``- [@role …](…)`` lines, and those lines."""
    lines = body.rstrip("\n").splitlines()
    sources: list[str] = []
    while lines and _SOURCE_LINE.match(lines[-1]):
        sources.insert(0, lines.pop())
    return "\n".join(lines) + "\n", sources


def _segments(markdown: str) -> list[tuple[str, str, str]]:
    """Split *markdown* into ``("md", text, "")``, admonition and component segments."""
    out: list[tuple[str, str, str]] = []
    prose: list[str] = []
    lines = markdown.splitlines()
    code_lines = {
        line
        for token in _markdown().parse(markdown)
        if token.type in ("fence", "code_block") and token.map is not None
        for line in range(*token.map)
    }
    i = 0

    def flush() -> None:
        if prose:
            out.append(("md", "\n".join(prose), ""))
            prose.clear()

    while i < len(lines):
        line = lines[i]
        if i in code_lines:
            prose.append(line)
            i += 1
            continue
        admonition = _ADMONITION.match(line)
        component = _COMPONENT.match(line)
        if admonition:
            flush()
            kind, title = admonition.group(2).lower(), admonition.group(3)
            block: list[str] = []
            i += 1
            while i < len(lines) and (lines[i].startswith("    ") or not lines[i].strip()):
                block.append(lines[i])
                i += 1
            out.append(
                (
                    "admonition",
                    textwrap.dedent("\n".join(block)),
                    f"{kind}\0{title or kind.title()}",
                )
            )
            continue
        if component:
            flush()
            out.append(("component", component.group(2) or "", component.group(1)))
        else:
            prose.append(line)
        i += 1
    flush()
    return out


def _html_body_markdown(text: str) -> str:
    """An HTML document's body as markdown: its blocks, components as ``::`` lines."""
    parts: list[str] = []
    for chunk in re.split(r"(<molab-markdown>.*?</molab-markdown>)", text, flags=re.S):
        block = _MARKDOWN_BLOCK.fullmatch(chunk.strip())
        if block:
            parts.append(textwrap.dedent(block.group(1)).strip("\n"))
            continue
        for element in _ELEMENT.finditer(chunk):
            parts.append(f"::{element.group(1)}{{{element.group(2).strip()}}}")
    return "\n\n".join(parts) + "\n"


class _Linker:
    """Rewrites a token's link target and remembers the assets it named."""

    def __init__(
        self,
        doc: Path,
        root: Path,
        asset_url: Callable[[str], str],
        doc_url: Callable[[str], str] | None,
    ) -> None:
        self.doc, self.root = doc, root
        self.asset_url, self.doc_url = asset_url, doc_url
        self.assets: list[str] = []

    def target(self, href: str) -> str | None:
        """The URL to put in the page, or ``None`` to drop the link (keep its text)."""
        match = ASSET_REF.match(href)
        if match:
            self.assets.append(match.group(1))
            return self.asset_url(match.group(1))
        if href.startswith("molab:"):
            return None
        if "://" in href or href.startswith(("#", "mailto:")):
            return href
        if self.doc_url and href.endswith((".md", ".html")):
            resolved = (self.doc.parent / href).resolve()
            try:
                rel = resolved.relative_to(self.root.resolve())
            except ValueError:
                return None
            return self.doc_url(rel.as_posix()) if resolved.is_file() else None
        return None


def _render_markdown(text: str, linker: _Linker) -> str:
    md = _markdown()
    tokens = md.parse(text)
    for token in tokens:
        for child in token.children or []:
            if child.type == "image":
                src = linker.target(str(child.attrGet("src") or ""))
                child.attrSet("src", src or "")
            elif child.type == "link_open":
                href = linker.target(str(child.attrGet("href") or ""))
                if href is None:
                    child.attrs.pop("href", None)
                else:
                    child.attrSet("href", href)
    return md.renderer.render(tokens, md.options, {})


def _body_html(markdown: str, linker: _Linker) -> str:
    out: list[str] = []
    for kind, text, extra in _segments(markdown):
        if kind == "md":
            out.append(_render_markdown(text, linker))
        elif kind == "admonition":
            adm, title = extra.split("\0")
            color = _ADMONITION_COLORS.get(adm, "#2f62b5")
            out.append(
                f'<div class="adm" style="--adm:{color}"><div class="adm-t">{html.escape(title)}</div>'
                f'<div class="adm-b">{_render_markdown(text, linker)}</div></div>'
            )
        else:
            out.append(
                f'<div class="component"><code>{html.escape(extra)}</code>'
                f"<span>{html.escape(text)}</span><em>live in the molab UI</em></div>"
            )
    return "\n".join(out)


def _sources_html(lines: list[str], linker: _Linker) -> str:
    if not lines:
        return ""
    items = _render_markdown("\n".join(lines), linker)
    items = re.sub(r"\[?@([a-z_]+) ", lambda m: f'<span class="role">{m.group(1)}</span> ', items)
    return f'<section class="sources"><h2>Sources</h2>{items}</section>'


def render_page(
    doc: Path,
    workspace_root: Path,
    *,
    asset_url: Callable[[str], str],
    doc_url: Callable[[str], str] | None = None,
) -> RenderedPage:
    """Render the knowledge document at *doc* as one HTML page.

    Args:
        doc: The document's file (``.md`` or ``.html``).
        workspace_root: The workspace it belongs to; relative links resolve
            inside it.
        asset_url: The URL the page uses for asset *id*.
        doc_url: The URL for another document by workspace-relative path, or
            ``None`` to show such links as text.
    """
    from molab.knowledge.concepts import _open_document

    concept = _open_document(doc)
    meta = concept.frontmatter() if callable(getattr(concept, "frontmatter", None)) else {}
    body = concept.read()
    if doc.suffix == ".html":
        body = _html_body_markdown(body)
    body, sources = _split_sources(body)
    linker = _Linker(doc, workspace_root, asset_url, doc_url)
    content = _body_html(body, linker)
    footer = _sources_html(sources, linker)
    heading = re.search(r"<h1>(.*?)</h1>", content, re.S)
    title = (
        re.sub(r"<[^>]+>", "", heading.group(1)) if heading else str(meta.get("name") or doc.stem)
    )
    cls = str(meta.get("class") or type(concept).__name__)
    tags = " ".join(f'<span class="tag">#{html.escape(str(t))}</span>' for t in concept.tags())
    byline = " · ".join(
        html.escape(str(v)) for v in (meta.get("created_by"), meta.get("created_at")) if v
    )
    page = _PAGE.format(
        title=html.escape(title),
        cls=html.escape(cls),
        tags=tags,
        byline=byline,
        path=html.escape(
            doc.resolve().relative_to(workspace_root.resolve()).as_posix()
            if doc.resolve().is_relative_to(workspace_root.resolve())
            else doc.name
        ),
        content=content,
        footer=footer,
        css=_CSS,
    )
    return RenderedPage(html=page, title=title, asset_ids=tuple(dict.fromkeys(linker.assets)))


_MAGIC = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF8", "image/gif"),
    (b"%PDF", "application/pdf"),
)


def _mime(path: Path, data: bytes) -> str:
    """The payload's media type: by extension, else by its leading bytes."""
    guessed = mimetypes.guess_type(path.name)[0]
    if guessed:
        return guessed
    for magic, mime in _MAGIC:
        if data.startswith(magic):
            return mime
    if data.lstrip()[:5] in (b"<svg ", b"<?xml") and b"<svg" in data[:2048]:
        return "image/svg+xml"
    return "application/octet-stream"


def _payload(workspace: Workspace, asset_id: str) -> Path:
    from molab.workspace.asset_repository import payload_path_for

    return Path(payload_path_for(workspace, asset_id))


def export_page(doc: Path, workspace: Workspace, out: Path) -> RenderedPage:
    """Write *doc* to *out* as one self-contained file, assets inlined.

    ``.pdf`` prints the same page to A4 with headless Chromium (Playwright,
    which must be installed); any other suffix writes the HTML.

    Raises:
        RuntimeError: A PDF was asked for and Playwright is not installed.
    """

    def inline(asset_id: str) -> str:
        path = _payload(workspace, asset_id)
        data = path.read_bytes()
        return f"data:{_mime(path, data)};base64,{base64.b64encode(data).decode()}"

    page = render_page(doc, Path(str(workspace.root)), asset_url=inline)
    if out.suffix.lower() == ".pdf":
        _print_pdf(page.html, out)
    else:
        out.write_text(page.html, encoding="utf-8")
    return page


def _print_pdf(page_html: str, out: Path) -> None:
    """Print *page_html* to *out* as an A4 PDF with headless Chromium."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "PDF export needs Playwright: pip install playwright && playwright install chromium"
        ) from exc
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            tab = browser.new_page()
            tab.set_content(page_html, wait_until="load")
            tab.pdf(
                path=str(out),
                format="A4",
                print_background=True,
                margin={"top": "16mm", "bottom": "16mm", "left": "14mm", "right": "14mm"},
            )
        finally:
            browser.close()


def serve(
    doc: Path,
    workspace: Workspace,
    *,
    host: str = "127.0.0.1",
    port: int = 0,
    on_ready: Callable[[str], None] | None = None,
) -> ThreadingHTTPServer:
    """Serve *doc* (and the documents it links) until interrupted.

    Returns the server after ``serve_forever`` stops. *on_ready* receives the
    page URL once the socket is bound (port 0 picks a free one).
    """
    from http import HTTPStatus
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from urllib.parse import quote, unquote

    root = Path(str(workspace.root)).resolve()
    start = doc.resolve().relative_to(root).as_posix()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *_args: object) -> None:  # noqa: ARG002
            """Suppress HTTP access logs."""
            return

        def _send(self, status: int, body: bytes, mime: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            path = unquote(self.path.split("?", 1)[0])
            if path in ("/", ""):
                self.send_response(HTTPStatus.FOUND)
                self.send_header("Location", "/view/" + quote(start))
                self.end_headers()
                return
            if path.startswith("/asset/"):
                try:
                    file = _payload(workspace, path.removeprefix("/asset/"))
                    data = file.read_bytes()
                    self._send(HTTPStatus.OK, data, _mime(file, data))
                except (KeyError, ValueError, OSError) as exc:
                    self._send(HTTPStatus.NOT_FOUND, f"no asset: {exc}".encode(), "text/plain")
                return
            if path.startswith("/view/"):
                rel = posixpath.normpath(path.removeprefix("/view/"))
                target = (root / rel).resolve()
                if not target.is_relative_to(root) or not target.is_file():
                    self._send(HTTPStatus.NOT_FOUND, b"no such document", "text/plain")
                    return
                try:
                    page = render_page(
                        target,
                        root,
                        asset_url=lambda a: f"/asset/{a}",
                        doc_url=lambda p: "/view/" + quote(p),
                    )
                except Exception as exc:  # shown in the page, not swallowed
                    self._send(
                        HTTPStatus.INTERNAL_SERVER_ERROR,
                        f"cannot render {rel}: {exc}".encode(),
                        "text/plain",
                    )
                    return
                self._send(HTTPStatus.OK, page.html.encode(), "text/html; charset=utf-8")
                return
            self._send(HTTPStatus.NOT_FOUND, b"not found", "text/plain")

    server = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{host}:{server.server_address[1]}/view/{quote(start)}"
    if on_ready:
        on_ready(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return server


_CSS = """
:root { --fg:#1f2328; --muted:#5c6370; --line:#e3e5e8; --bg:#fff; --soft:#f6f7f9; --accent:#2f62b5; }
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--fg);
  font: 15px/1.7 "Geist", "Inter", "Noto Sans SC", "PingFang SC", system-ui, sans-serif; }
main { max-width: 860px; margin: 0 auto; padding: 48px 24px 96px; }
header.doc { border-bottom:1px solid var(--line); padding-bottom:12px; margin-bottom:8px; }
.meta { font-size:13px; color:var(--muted); display:flex; gap:10px; flex-wrap:wrap; align-items:center; }
.cls { font-weight:600; color:#66781f; }
.tag { background:#eef1e3; color:#66781f; border-radius:10px; padding:0 8px; font-size:12px; }
.path { font-family: ui-monospace, Menlo, monospace; font-size:12px; }
h1 { font-size:30px; font-weight:400; line-height:1.3; margin:28px 0 12px; }
h2 { font-size:21px; font-weight:600; margin:40px 0 12px; padding-bottom:6px; border-bottom:1px solid var(--line); }
h3 { font-size:17px; margin:28px 0 8px; }
p, li { margin: 6px 0; }
img { max-width:100%; height:auto; display:block; margin:16px auto; border-radius:6px; }
table { border-collapse: collapse; width:100%; margin:14px 0; font-size:13.5px; display:block; overflow-x:auto; }
th, td { padding:6px 10px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; }
th { color:var(--muted); font-weight:600; border-bottom:1px solid #c9ccd1; white-space:nowrap; }
td { font-variant-numeric: tabular-nums; }
code { font-family: ui-monospace, Menlo, monospace; font-size:0.9em; background:var(--soft); padding:1px 4px; border-radius:4px; }
a { color: var(--accent); }
.adm { border:1px solid color-mix(in srgb, var(--adm) 35%, transparent); border-radius:6px; margin:16px 0; overflow:hidden; }
.adm-t { background: color-mix(in srgb, var(--adm) 10%, white); color:var(--adm); font-weight:600; padding:6px 12px; }
.adm-b { padding: 2px 16px; }
.component { border:1.5px dashed #c5cba8; border-radius:8px; padding:10px 14px; margin:14px 0;
  display:flex; gap:10px; align-items:baseline; font-size:13px; color:var(--muted); }
.component em { margin-left:auto; font-size:12px; }
.sources { margin-top:48px; font-size:13px; color:var(--muted); }
.sources h2 { font-size:14px; border:none; margin-bottom:4px; }
.sources ul { padding-left:18px; }
.role { font-size:11px; text-transform:uppercase; letter-spacing:.04em; color:#8a8f98; }
@media print {
  main { padding:0; max-width:none; }
  img, table, .adm, .component { break-inside: avoid; }
  h1, h2, h3 { break-after: avoid; }
  p:has(> img) { break-inside: avoid; break-after: avoid; }
}
"""

_PAGE = """<!doctype html>
<html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title><style>{css}</style></head>
<body><main>
<header class="doc"><div class="meta"><span class="cls">{cls}</span>{tags}<span>{byline}</span>
<span class="path">{path}</span></div></header>
{content}
{footer}
</main></body></html>
"""

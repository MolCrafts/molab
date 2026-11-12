"""``molab knowledge serve`` / ``knowledge.preview`` — one document as a reader sees it.

The page shows ``molab:asset`` images in place, MkDocs admonitions, component
lines as placeholders and the trailing source lines as a list; the server
re-renders on every request and answers ``/asset/<id>`` from the slot; an
export inlines every image so the file stands alone.
"""

from __future__ import annotations

import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from molab.knowledge.preview import export_page, render_page, serve
from molab.workspace import Workspace
from molab.workspace.history import GitHistory

PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
    b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe"
    b"\x02\xfe\xa7V\xbd\xfa\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _workspace(tmp_path: Path) -> tuple[Workspace, str, Path]:
    ws = Workspace(tmp_path / "ws", name="lab")
    ws.materialize()
    GitHistory(ws.root).init()
    run = ws.add_project("p").add_experiment("e").add_run(params={"seed": 1})
    with run.start() as ctx:
        asset = ctx.register(PNG, title="figure.png")
    knowledges = Path(str(ws.root)) / "knowledges"
    knowledges.mkdir(exist_ok=True)
    (knowledges / "other.md").write_text("---\nname: other\nclass: Note\n---\n# Other\n")
    doc = knowledges / "report.md"
    doc.write_text(
        "---\nname: report\nclass: Report\ncreated_by: me\n---\n"
        "# The report\n\n"
        f"![Figure 1](molab:asset/{asset.id})\n\n"
        "| a | b |\n|---|---|\n| 1 | 2 |\n\n"
        '!!! warning "Before use"\n    Only **one** box.\n\n'
        "::molab-stage-track\n\n"
        "See [the other note](other.md) and <script>alert(1)</script>.\n"
        "- [@cites x](https://doi.org/10.1/x)\n"
    )
    return ws, asset.id, doc


class TestRenderPage:
    @pytest.mark.parametrize("fence", ["```", "~~~~"])
    def test_extension_examples_inside_code_fences_stay_literal(
        self, tmp_path: Path, fence: str
    ) -> None:
        ws, _asset_id, doc = _workspace(tmp_path)
        doc.write_text(
            "---\nname: example\nclass: Note\n---\n# Example\n\n"
            f'{fence}markdown\n!!! warning "Example"\n    Literal text.\n'
            f"::molab-stage-track\n{fence}\n\n"
            '!!! note "Real note"\n    Real text.\n',
            encoding="utf-8",
        )

        page = render_page(doc, Path(str(ws.root)), asset_url=str)

        assert '<pre><code class="language-markdown">' in page.html
        assert "!!! warning" in page.html
        assert "::molab-stage-track" in page.html
        assert 'class="component"' not in page.html
        assert page.html.count('class="adm"') == 1
        assert "Real note" in page.html

    def test_images_tables_admonitions_components_and_sources(self, tmp_path: Path) -> None:
        ws, asset_id, doc = _workspace(tmp_path)

        page = render_page(
            doc,
            Path(str(ws.root)),
            asset_url=lambda a: f"/asset/{a}",
            doc_url=lambda p: f"/view/{p}",
        )

        assert page.title == "The report"
        assert page.asset_ids == (asset_id,)
        assert f'src="/asset/{asset_id}"' in page.html
        assert "<table>" in page.html
        assert 'class="adm"' in page.html and "Before use" in page.html
        assert "<strong>one</strong>" in page.html
        assert "molab-stage-track" in page.html
        assert 'href="/view/knowledges/other.md"' in page.html
        assert '<section class="sources">' in page.html
        # Raw HTML in the body is text, never markup.
        assert "<script>" not in page.html

    def test_html_document_blocks_render_as_markdown(self, tmp_path: Path) -> None:
        ws, _asset_id, _doc = _workspace(tmp_path)
        doc = Path(str(ws.root)) / "knowledges" / "page.html"
        doc.write_text(
            '<!doctype html><html><head><script id="molab-record" type="application/json">'
            '{"name": "page", "class": "Note"}</script></head><body>\n'
            "<molab-markdown>\n# Page\n\nSome *text*.\n</molab-markdown>\n"
            '<molab-run-ref ref="molab:run/1"></molab-run-ref>\n</body></html>\n'
        )

        page = render_page(doc, Path(str(ws.root)), asset_url=lambda a: a)

        assert page.title == "Page"
        assert "<em>text</em>" in page.html
        assert "molab-run-ref" in page.html


def test_export_inlines_every_image(tmp_path: Path) -> None:
    ws, asset_id, doc = _workspace(tmp_path)
    out = tmp_path / "report.html"

    page = export_page(doc, ws, out)

    text = out.read_text()
    assert page.asset_ids == (asset_id,)
    assert 'src="data:image/png;base64,' in text
    assert "molab:asset" not in text


def test_server_renders_on_each_request_and_serves_assets(tmp_path: Path) -> None:
    ws, asset_id, doc = _workspace(tmp_path)
    ready: list[str] = []
    started = threading.Event()

    def on_ready(url: str) -> None:
        ready.append(url)
        started.set()

    servers: list[object] = []

    def run() -> None:
        servers.append(serve(doc, ws, port=0, on_ready=on_ready))

    import http.server

    original = http.server.ThreadingHTTPServer.serve_forever

    def capture(self, *args, **kwargs):  # noqa: ANN002, ANN003
        servers.append(self)
        return original(self, *args, **kwargs)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(http.server.ThreadingHTTPServer, "serve_forever", capture)
        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        assert started.wait(5)
        url = ready[0]
        base = url.split("/view/")[0]

        first = urllib.request.urlopen(url).read().decode()
        assert "The report" in first
        doc.write_text(doc.read_text().replace("# The report", "# Edited report"))
        assert "Edited report" in urllib.request.urlopen(url).read().decode()
        assert urllib.request.urlopen(f"{base}/asset/{asset_id}").read() == PNG
        assert urllib.request.urlopen(base + "/").geturl() == url
        with pytest.raises(urllib.error.HTTPError):
            urllib.request.urlopen(f"{base}/view/../../etc/passwd")

        servers[0].shutdown()  # ty: ignore[unresolved-attribute]
        thread.join(5)

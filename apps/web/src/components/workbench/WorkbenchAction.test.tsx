import { describe, expect, it } from "@rstest/core";
import { Download } from "lucide-react";
import { renderToStaticMarkup } from "react-dom/server";

import { WorkbenchAction, WorkbenchIconAction } from "./WorkbenchAction";

describe("WorkbenchAction", () => {
  it("keeps icon actions named and compact without visible label or filled chrome", () => {
    const html = renderToStaticMarkup(
      <WorkbenchAction icon={<Download aria-hidden />} kind="primary" disabled>
        Download result
      </WorkbenchAction>,
    );
    expect(html).toContain('title="Download result"');
    expect(html).toContain('class="sr-only">Download result</span>');
    expect(html).toContain('disabled=""');
    expect(html).toContain("size-control-compact");
    expect(html).not.toContain("bg-primary");
    expect(html).not.toContain("border-input");
  });

  it("keeps destructive intent visible without a filled danger button", () => {
    const html = renderToStaticMarkup(
      <WorkbenchIconAction label="Delete run" kind="danger">
        <Download />
      </WorkbenchIconAction>,
    );
    expect(html).toContain('aria-label="Delete run"');
    expect(html).toContain("text-destructive");
    expect(html).not.toContain("bg-destructive");
  });

  it("slots one link child while preserving adjacent action content", () => {
    const html = renderToStaticMarkup(
      <WorkbenchAction asChild icon={<Download />}>
        <a href="/export">Export</a>
      </WorkbenchAction>,
    );

    expect(html).toContain('href="/export"');
    expect(html).toContain("Export");
    expect(html).not.toContain('type="button"');
  });

  it("renders an accessible borderless icon link", () => {
    const html = renderToStaticMarkup(
      <WorkbenchIconAction label="Download result" asChild>
        <a href="/result">
          <Download />
        </a>
      </WorkbenchIconAction>,
    );

    expect(html).toContain('href="/result"');
    expect(html).toContain('aria-label="Download result"');
    expect(html).toContain('title="Download result"');
    expect(html).not.toContain("border-input");
    expect(html).not.toContain('type="button"');
  });
});

import { describe, expect, it } from "@rstest/core";
import { renderToStaticMarkup } from "react-dom/server";

import { StatusLedger } from "./StatusLedger";

const counts = { total: 4, running: 1, pending: 0, succeeded: 1, failed: 1, cancelled: 1 };

describe("StatusLedger completeness", () => {
  it("identifies the basis of a success rate while inventory is incomplete", () => {
    const html = renderToStaticMarkup(<StatusLedger counts={counts} partial />);
    expect(html).toContain("33");
    expect(html).toContain("loaded so far");
    expect(html).toContain("finished");
  });

  it("removes the partial qualifier once the full inventory is available", () => {
    const html = renderToStaticMarkup(<StatusLedger counts={counts} />);
    expect(html).not.toContain("loaded so far");
    expect(html).toContain("33");
  });
});

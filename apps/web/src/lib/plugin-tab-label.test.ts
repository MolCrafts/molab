import { describe, expect, it } from "@rstest/core";

import { pluginTabLabel } from "./plugin-tab-label";

describe("pluginTabLabel", () => {
  it("labels catalog-badge tabs with the catalog count, never the matched-file count", () => {
    expect(pluginTabLabel("Metrics", 27, true)).toBe("Metrics");
    expect(pluginTabLabel("Metrics", 27, true, null)).toBe("Metrics");
    expect(pluginTabLabel("Metrics", 27, true, 6)).toBe("Metrics (6)");
  });

  it("shows a count for file-badge tabs only when more than one file matched", () => {
    expect(pluginTabLabel("MolVis", 1, false)).toBe("MolVis");
    expect(pluginTabLabel("MolVis", 3, false)).toBe("MolVis (3)");
    expect(pluginTabLabel("MolPlot", 2, false)).toBe("MolPlot (2)");
  });
});

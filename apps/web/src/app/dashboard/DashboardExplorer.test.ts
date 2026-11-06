import { describe, expect, it } from "@rstest/core";

import { PROJECT_LIMIT, projectDetail } from "@/app/dashboard/DashboardExplorer";

describe("DashboardExplorer", () => {
  it("caps the project sample", () => {
    expect(PROJECT_LIMIT).toBe(6);
  });

  it("names a project's experiment count without a false plural", () => {
    expect(projectDetail("Cooling study", 4)).toBe("Cooling study");
    expect(projectDetail("", 1)).toBe("1 experiment");
    expect(projectDetail("", 0)).toBe("No experiments yet");
    expect(projectDetail("", 3)).toBe("3 experiments");
    expect(projectDetail("", null)).toBe("");
  });
});

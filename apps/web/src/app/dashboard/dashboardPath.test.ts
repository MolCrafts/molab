import { describe, expect, it } from "@rstest/core";
import { leftPanelViewFromPath, SECTION_PATH } from "@/app/entities/paths";

describe("dashboard section routing", () => {
  it("uses the application root as the workspace dashboard", () => {
    expect(SECTION_PATH.dashboard).toBe("/");
    expect(leftPanelViewFromPath("/")).toBe("dashboard");
    expect(leftPanelViewFromPath("/dashboard")).toBe("dashboard");
  });
});

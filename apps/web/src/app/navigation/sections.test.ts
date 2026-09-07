import { beforeEach, describe, expect, it } from "@rstest/core";
import { createPluginAPI } from "@/plugins/api/create_api";
import { resetContributionRuntimeForTests } from "@/plugins/contribution-runtime";
import { registerCoreNavigation } from "@/plugins/core/navigation";
import { registerKnowledgeNavigation } from "@/plugins/knowledge/navigation";
import {
  getNavigationContribution,
  leftPanelViewFromPath,
  managementNavigationContribution,
  navigationContributions,
  railNavigationContributions,
} from "./sections";

describe("navigation contributions", () => {
  beforeEach(() => {
    resetContributionRuntimeForTests();
    registerCoreNavigation(createPluginAPI("core").api);
    registerKnowledgeNavigation(createPluginAPI("knowledge").api);
  });

  it("exposes the operational rail without legacy collection routes", () => {
    expect(railNavigationContributions().map(({ id }) => id)).toEqual([
      "dashboard",
      "projects",
      "runs",
      "agent",
      "knowledge",
      "asset",
      "workspace",
    ]);
    expect(managementNavigationContribution()?.id).toBe("settings");
    expect(navigationContributions.find(({ id }) => id === "activity")?.placement).toBe("legacy");
    expect(navigationContributions.find(({ id }) => id === "workflow")?.placement).toBe("legacy");
  });

  it("keeps Files copy and full-surface settings in product metadata", () => {
    expect(getNavigationContribution("workspace")).toMatchObject({
      label: "Files",
      explorerTitle: "Files",
      breadcrumbLabel: "Files",
    });
    expect(getNavigationContribution("settings").shellMode).toBe("rail-only");
  });

  it("declares feature-owned landing surfaces in the same section manifest", () => {
    expect(getNavigationContribution("dashboard").landing).toBeDefined();
    expect(getNavigationContribution("runs").landing).toBeDefined();
    expect(getNavigationContribution("settings").landing).toBeDefined();
    expect(getNavigationContribution("activity").landing).toBeDefined();
    expect(getNavigationContribution("workflow").landing).toBeDefined();
    expect(getNavigationContribution("projects").landing).toBeUndefined();
  });

  it("owns explorer-specific empty-state language outside the center host", () => {
    expect(getNavigationContribution("projects").emptySelection?.title).toBe(
      "No project item selected",
    );
    expect(getNavigationContribution("asset").emptySelection?.title).toBe("No asset selected");
    expect(getNavigationContribution("workspace").emptySelection?.title).toBe("No file selected");
    expect(getNavigationContribution("agent").emptySelection?.title).toBe("No agent task selected");
  });

  it("matches canonical and compatibility paths", () => {
    expect(leftPanelViewFromPath("/")).toBe("dashboard");
    expect(leftPanelViewFromPath("/projects/p/experiments/e/workflow")).toBe("projects");
    expect(leftPanelViewFromPath("/runs?view=timeline")).toBe("runs");
    expect(leftPanelViewFromPath("/activity/extra")).toBe("activity");
    expect(leftPanelViewFromPath("/workflows/legacy")).toBe("workflow");
    expect(leftPanelViewFromPath("/unknown")).toBe("projects");
  });
});

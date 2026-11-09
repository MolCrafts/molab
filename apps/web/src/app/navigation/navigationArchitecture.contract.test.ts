import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "@rstest/core";

const here = dirname(fileURLToPath(import.meta.url));
const appRoot = resolve(here, "..");
const readAppSource = (path: string): string => readFileSync(resolve(appRoot, path), "utf8");

describe("navigation contribution boundary", () => {
  it("keeps product metadata in one descriptor", () => {
    const sections = readAppSource("navigation/sections.tsx");
    const coreNav = readAppSource("../plugins/core/navigation.tsx");
    const knowledgeNav = readAppSource("../plugins/knowledge/navigation.tsx");
    expect(sections).toContain("listNavigationContributions");
    expect(sections).toContain("retainSelectionFor");
    expect(sections).toContain("emptySelection");
    expect(coreNav).toContain("explorer: RunsExplorer");
    expect(coreNav).toContain("explorer: AssetsExplorer");
    expect(coreNav).toContain("explorer: FilesExplorer");
    expect(coreNav).toContain("explorer: ProjectsExplorer");
    expect(coreNav).not.toContain("ActivityExplorer");
    expect(coreNav).not.toContain("WorkflowExplorer");
    expect(coreNav).toContain("landing: DashboardPage");
    expect(coreNav).toContain("landing: RunsPage");
    expect(coreNav).toContain("landing: ComparePane");
    expect(coreNav).toContain("landing: SettingsPage");
    expect(knowledgeNav).toContain("explorer: KnowledgeExplorer");
  });

  it("keeps the rail and explorer host out of the legacy LeftPanel body", () => {
    const leftPanel = readAppSource("panels/LeftPanel.tsx");
    const shell = readAppSource("layout/AppShell.tsx");
    const rail = readAppSource("navigation/NavigationRail.tsx");
    const host = readAppSource("navigation/NavigationExplorerHost.tsx");

    // L00: the activity bar is the shell's, outside the resizable side bar.
    expect(shell).toContain("<NavigationRail");
    expect(leftPanel).not.toContain("<NavigationRail");
    expect(leftPanel).toContain("<NavigationExplorerHost");
    expect(leftPanel).not.toContain("<LeftIconRail");
    expect(leftPanel).not.toContain("<LeftExplorer ");
    // The side bar splits its own column (explorer over Pinned) through
    // domain-free chrome; it still builds neither rail nor explorer.
    expect(leftPanel).toContain("<ExplorerDock");
    expect(rail).toContain("LeftIconRail");
    expect(host).toContain("LeftExplorer");
  });

  it("mounts Runs filters from the Runs feature instead of LeftPanel", () => {
    const leftPanel = readAppSource("panels/LeftPanel.tsx");
    const explorer = readAppSource("runs/RunsExplorer.tsx");

    expect(leftPanel).not.toContain("useWorkspaceRuns");
    expect(leftPanel).not.toContain("RunsFacetPanel");
    expect(explorer).toContain("useWorkspaceRuns");
    expect(explorer).toContain("RunsFacetPanel");
    expect(explorer).toContain("writeFilterParams");
  });

  it("does not start a workspace inventory scan just to decide rail visibility", () => {
    const visibility = readAppSource("dashboard/useWorkspaceTab.ts");
    const app = readAppSource("../App.tsx");
    expect(visibility).toContain("useWorkspaceRuns({ enabled: false })");
    expect(app).toContain('enabled: activeView === "runs" || activeView === "dashboard"');
    expect(app).not.toContain("for (const experiment of snapshot.experiments)");
  });

  it("mounts the Knowledge tree from the Knowledge feature", () => {
    const leftPanel = readAppSource("panels/LeftPanel.tsx");
    const explorer = readAppSource("../plugins/knowledge/KnowledgeExplorer.tsx");

    expect(leftPanel).not.toContain("DocTree");
    expect(explorer).toContain("DocTree");
    expect(explorer).toContain("NavigationExplorerProps");
  });

  it("removes Assets domain logic from LeftPanel", () => {
    const leftPanel = readAppSource("panels/LeftPanel.tsx");
    const assets = readAppSource("assets/AssetsExplorer.tsx");

    expect(leftPanel).not.toContain("buildAssetNodes");
    expect(assets).toContain("buildAssetExplorerNodes");
  });

  it("moves Files tree and filesystem commands out of LeftPanel", () => {
    const leftPanel = readAppSource("panels/LeftPanel.tsx");
    const files = readAppSource("files/FilesExplorer.tsx");

    expect(leftPanel).not.toContain("buildWorkspaceNodes");
    expect(leftPanel).not.toContain("detectFileKind");
    expect(leftPanel).not.toContain("handleOpenWorkspace");
    expect(files).toContain("buildFilesExplorerNodes");
    expect(files).toContain("onOpenWorkspace");
    expect(files).toContain("withWriteGate");
  });

  it("leaves LeftPanel as a small navigation adapter", () => {
    const leftPanel = readAppSource("panels/LeftPanel.tsx");
    const projects = readAppSource("projects/ProjectsExplorer.tsx");

    expect(leftPanel.split("\n").length).toBeLessThan(100);
    expect(leftPanel).not.toContain("TreeView");
    expect(leftPanel).not.toContain("projectsApi");
    expect(leftPanel).not.toContain("workspaceApi");
    expect(leftPanel).not.toContain("CreateProjectDialog");
    expect(projects).toContain("buildProjectNodes");
    expect(projects).toContain("CreateProjectDialog");
  });

  it("keeps landing and contextual inspector domains out of host panels", () => {
    const centerPanel = readAppSource("panels/CenterPanel.tsx");
    const appShell = readAppSource("layout/AppShell.tsx");
    const runsPage = readAppSource("runs/RunsPage.tsx");
    const explorerHost = readAppSource("navigation/NavigationExplorerHost.tsx");

    expect(centerPanel).toContain("getNavigationContribution(leftPanelView)");
    expect(centerPanel).toContain("navigation?.landing");
    // L00: nothing open is the editor watermark, not a per-section placeholder.
    expect(centerPanel).toContain("<Watermark");
    expect(centerPanel).not.toContain("emptySelection");
    expect(centerPanel).not.toContain("leftPanelView ===");
    expect(centerPanel).not.toContain("DashboardPage");
    expect(centerPanel).not.toContain("RunsPage");
    expect(centerPanel).not.toContain("No document selected");
    // L12: one Preview, owned by the shell; pages name a target and never
    // register a surface of their own.
    expect(appShell).toContain("PreviewProvider");
    expect(appShell).not.toContain("InspectorSurfaceRegistration");
    expect(appShell).not.toContain("RightPanel");
    expect(runsPage).toContain("usePreview");
    expect(runsPage).not.toContain("onInspectorChange");
    expect(centerPanel).toContain("SurfaceErrorBoundary");
    expect(explorerHost).toContain("SurfaceErrorBoundary");
    expect(explorerHost).toContain("Could not load");
  });
});

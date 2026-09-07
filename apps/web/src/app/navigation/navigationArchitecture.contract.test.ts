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
    expect(coreNav).toContain("explorer: AgentExplorer");
    expect(coreNav).toContain("explorer: FilesExplorer");
    expect(coreNav).toContain("explorer: ProjectsExplorer");
    expect(coreNav).toContain("explorer: ActivityExplorer");
    expect(coreNav).toContain("explorer: WorkflowExplorer");
    expect(coreNav).toContain("landing: DashboardPage");
    expect(coreNav).toContain("landing: RunsPage");
    expect(coreNav).toContain("landing: SettingsPage");
    expect(knowledgeNav).toContain("explorer: KnowledgeExplorer");
  });

  it("keeps the rail and explorer host out of the legacy LeftPanel body", () => {
    const leftPanel = readAppSource("panels/LeftPanel.tsx");
    const rail = readAppSource("navigation/NavigationRail.tsx");
    const host = readAppSource("navigation/NavigationExplorerHost.tsx");

    expect(leftPanel).toContain("<NavigationRail");
    expect(leftPanel).toContain("<NavigationExplorerHost");
    expect(leftPanel).not.toContain("<LeftIconRail");
    expect(leftPanel).not.toContain("<LeftExplorer ");
    // The panel splits its own column (explorer over the docked Comparison)
    // through domain-free chrome; it still builds neither rail nor explorer.
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

  it("mounts the Knowledge tree from the Knowledge feature", () => {
    const leftPanel = readAppSource("panels/LeftPanel.tsx");
    const explorer = readAppSource("../plugins/knowledge/KnowledgeExplorer.tsx");

    expect(leftPanel).not.toContain("DocTree");
    expect(explorer).toContain("DocTree");
    expect(explorer).toContain("NavigationExplorerProps");
  });

  it("removes Assets and Agent domain logic from LeftPanel", () => {
    const leftPanel = readAppSource("panels/LeftPanel.tsx");
    const assets = readAppSource("assets/AssetsExplorer.tsx");
    const agent = readAppSource("agent/AgentExplorer.tsx");

    expect(leftPanel).not.toContain("buildAssetNodes");
    expect(leftPanel).not.toContain("buildAgentNodes");
    expect(leftPanel).not.toContain("handleDeleteAgentTask");
    expect(assets).toContain("buildAssetExplorerNodes");
    expect(agent).toContain("buildAgentExplorerNodes");
    expect(agent).toContain("agentApi.deleteSession");
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
    const workflows = readAppSource("workflows/WorkflowExplorer.tsx");

    expect(leftPanel.split("\n").length).toBeLessThan(100);
    expect(leftPanel).not.toContain("TreeView");
    expect(leftPanel).not.toContain("projectsApi");
    expect(leftPanel).not.toContain("workspaceApi");
    expect(leftPanel).not.toContain("CreateProjectDialog");
    expect(projects).toContain("buildProjectNodes");
    expect(projects).toContain("CreateProjectDialog");
    expect(workflows).toContain("buildWorkflowExplorerNodes");
  });

  it("keeps landing and contextual inspector domains out of host panels", () => {
    const centerPanel = readAppSource("panels/CenterPanel.tsx");
    const appShell = readAppSource("layout/AppShell.tsx");
    const runsPage = readAppSource("runs/RunsPage.tsx");
    const explorerHost = readAppSource("navigation/NavigationExplorerHost.tsx");

    expect(centerPanel).toContain("getNavigationContribution(leftPanelView)");
    expect(centerPanel).toContain("navigation?.landing");
    expect(centerPanel).toContain("navigation?.emptySelection");
    expect(centerPanel).not.toContain("leftPanelView ===");
    expect(centerPanel).not.toContain("DashboardPage");
    expect(centerPanel).not.toContain("RunsPage");
    expect(centerPanel).not.toContain("No agent task selected");
    expect(centerPanel).not.toContain("No document selected");
    expect(appShell).not.toContain('from "@/app/runs/inspector/RunInspector"');
    expect(appShell).toContain("InspectorSurfaceRegistration");
    expect(runsPage).toContain("RunInspector");
    expect(runsPage).toContain("onInspectorChange");
    expect(centerPanel).toContain("SurfaceErrorBoundary");
    expect(explorerHost).toContain("SurfaceErrorBoundary");
    expect(explorerHost).toContain("Could not load");
  });
});

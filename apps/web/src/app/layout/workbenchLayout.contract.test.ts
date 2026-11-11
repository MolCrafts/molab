import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "@rstest/core";

const here = dirname(fileURLToPath(import.meta.url));
const webRoot = resolve(here, "../..");
const readWebSource = (path: string): string => readFileSync(resolve(webRoot, path), "utf8");

describe("workbench layout contract", () => {
  it("keeps the title bar one 35px band whose search is a command centre, not an input", () => {
    const titleBar = readWebSource("app/shell/TitleBar.tsx");
    const tokens = readWebSource("styles/tailwind.css");

    // L00 (DS v1.4): VS Code density lives in product shell tokens; the
    // constitution's own bands stay as they are.
    expect(titleBar).toContain("h-shell-titlebar");
    expect(tokens).toContain("--spacing-shell-titlebar: 2.1875rem");
    expect(readWebSource("styles/constitution-theme.css")).toContain(
      "--spacing-toolbar-compact: 2.5rem",
    );
    expect(titleBar).not.toMatch(/h-\[\d/);
    expect(titleBar).not.toContain("<Input");
    // The centre opens ⌘K; nothing filters in place.
    expect(titleBar).toContain('openCommandPalette("goto")');
  });

  it("frames the editor VS Code style and keeps the right slot contextual", () => {
    const shell = readWebSource("app/layout/AppShell.tsx");
    const explorer = readWebSource("components/layout/ExplorerShell.tsx");
    const tokens = readWebSource("styles/tailwind.css");
    const theme = readWebSource("styles/constitution-theme.css");

    // L00: side bar 248 (200–480) under one new key; the old keys are ignored.
    expect(shell).toContain('default: "248px", min: "200px", max: "480px"');
    expect(shell).toContain('autoSaveId="molab.shell.v3"');
    expect(shell).not.toContain("molab.workbench.shell");
    // Activity bar outside the resizable side bar, so hiding it keeps the rail.
    expect(shell).toContain("{activityBar}");
    expect(explorer).toContain('"flex w-12');
    // Tabs · breadcrumb · page; actions in the tab row (editor actions).
    expect(shell).toContain("<EditorTabStrip");
    expect(shell).toContain("<Breadcrumb");
    expect(shell).toContain("EditorActionsSlotProvider");
    expect(readWebSource("app/components/entity/EntityPage.tsx")).toContain("<EditorActions>");
    // L12: the docked right slot is gone; one Preview overlays the editor.
    expect(shell).toContain("<PreviewOverlay");
    expect(shell).not.toContain("molab.workbench.detail");
    expect(shell).not.toContain("DetailsInspector");
    // Status bar 22px is a product shell token; the constitution keeps 28px.
    expect(tokens).toContain("--spacing-shell-status: 1.375rem");
    expect(theme).toContain("--spacing-statusbar: 1.75rem");
  });

  it("keeps Dashboard exploratory and Settings in the side bar (L11)", () => {
    const coreNav = readWebSource("plugins/core/navigation.tsx");

    expect(coreNav).toContain("explorer: DashboardExplorer");
    expect(coreNav).toMatch(/id: "dashboard"[\s\S]*?shellMode: "explorer"/);
    expect(coreNav).toMatch(/id: "settings"[\s\S]*?shellMode: "explorer"/);
    expect(coreNav).toContain("explorer: SettingsExplorer");
  });

  it("gives the workspace, a project and an experiment one Overview shape (L01–L03)", () => {
    const dashboard = readWebSource("app/dashboard/DashboardPage.tsx");
    const workspaceOverview = readWebSource("app/dashboard/WorkspaceOverview.tsx");
    const explorer = readWebSource("app/dashboard/DashboardExplorer.tsx");
    const project = readWebSource("app/renderers/ProjectViewer.tsx");
    const projectOverview = readWebSource("app/renderers/project/ProjectOverview.tsx");

    // The workspace (L01): verdict, the shared gauges, Activity, outcome / backends /
    // duration by project. The run lists are the side bar's, not views.
    expect(dashboard).toContain("<WorkspaceOverview");
    expect(dashboard).not.toMatch(
      /value: "(attention|timeline)"|Arrange|<DashboardGrid|localStorage/,
    );
    expect(dashboard).toContain('value: "plan"');
    for (const part of ["<Verdict", "<Gauges", "<ActivityPanel", "<MixChart", "<DurationsBy"]) {
      expect(workspaceOverview).toContain(part);
    }
    expect(workspaceOverview).not.toMatch(/NeedsAttention|RunTimeline|PlanProgress/);
    expect(explorer).toContain("dashboardLists");
    for (const list of ["Needs attention", "Active", "Finished · 24h"]) {
      expect(explorer).toContain(list);
    }

    // An experiment has its own Overview (L03): a verdict, three gauges, outcome and key result.
    const experiment = readWebSource("app/renderers/ExperimentViewer.tsx");
    const experimentOverview = readWebSource("app/renderers/experiment/ExperimentOverview.tsx");
    expect(experiment).toContain("<ExperimentOverview");
    expect(experiment).not.toContain("PlanProgress");
    for (const gauge of ["SuccessDial", "UnitMeter", "DurationRange", "SweepChart", "MixChart"]) {
      expect(experimentOverview).toContain(gauge);
    }
    expect(experimentOverview).not.toMatch(/ActivityPanel|Backends/);

    // A project is that shape one level up (L02): verdict, the same gauges, outcome and
    // duration by experiment; Attention, Timeline and Settings left; Plan is its own roadmap.
    expect(project).toContain("<ProjectOverview");
    expect(project).not.toMatch(/value: "(attention|timeline|settings)"/);
    expect(project).toContain('value: "plan"');
    expect(project).toContain("usePlanCampaigns(project");
    for (const part of ["<Verdict", "<Gauges", "<MixChart", "<DurationsBy"]) {
      expect(projectOverview).toContain(part);
    }
    expect(projectOverview).not.toMatch(/ActivityPanel|Backends|PlanProgress/);
  });

  it("gives Compare a page frame and a single matrix scrollport", () => {
    const pane = readWebSource("app/compare/ComparePane.tsx");
    const table = readWebSource("app/compare/CompareTable.tsx");
    const dock = readWebSource("app/compare/SelectionPanel.tsx");
    const dialog = readWebSource("app/compare/MetricDetailDialog.tsx");

    // L05: an editor tab with views Table · Chart | MolPlot; runs as columns with a
    // baseline; metric files are read only when the MolPlot view is asked for.
    expect(pane).toContain("EntityPage");
    expect(pane).toContain('title="Compare"');
    expect(pane).toContain("parameterRows(runs, baseline)");
    expect(pane).toContain("CompareBarsChart");
    expect(pane).toContain('view !== "molplot"');
    expect(pane).not.toContain("runs from");
    expect(table).not.toMatch(/import \{[^}]*\bTable\b[^}]*\} from "@\/components\/ui\/table"/);
    expect(table).toContain("visibleRows");
    expect(table).toContain("rowGroups");
    expect(table).toContain("compileRunFilter");
    expect(table).toContain("cursor-col-resize");
    expect(table).toContain("openMetric");
    expect(table).toContain("nextRunSort");
    expect(table).not.toContain("workspaceLabel} /");
    expect(dock).toContain("overflow-hidden");
    expect(dock).toContain("hydrateComparisonTree");
    expect(dock).not.toContain("setCategory");
    expect(dock).not.toContain("workspaceLabel} /");
    expect(dialog).toContain("h-viewport-tall");
    expect(dialog).toContain("w-drawer");
    expect(dialog).toContain('placement="overlay"');
    expect(dialog).not.toContain("h-[85vh]");
    expect(readWebSource("components/layout/ExplorerShell.tsx")).toContain('min: "88px"');
  });
});

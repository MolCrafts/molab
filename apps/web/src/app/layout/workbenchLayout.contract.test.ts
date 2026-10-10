import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "@rstest/core";

const here = dirname(fileURLToPath(import.meta.url));
const webRoot = resolve(here, "../..");
const readWebSource = (path: string): string => readFileSync(resolve(webRoot, path), "utf8");

describe("workbench layout contract", () => {
  it("keeps the global bar compact and free of persistent search", () => {
    const contextBar = readWebSource("app/layout/ContextBar.tsx");

    // The band is the constitution's own 40px region band, not a literal and
    // not a product-invented token. It was 35px until 2026-09-07, below § 2.
    expect(contextBar).toContain("h-toolbar-compact");
    expect(readWebSource("styles/constitution-theme.css")).toContain(
      "--spacing-toolbar-compact: 2.5rem",
    );
    expect(contextBar).not.toMatch(/h-\[\d/);
    expect(contextBar).not.toContain("Filter explorer");
    expect(contextBar).not.toContain("<Input");
    expect(contextBar).not.toContain("<Search");
  });

  it("uses fixed editor chrome and reserves the inspector for contextual surfaces", () => {
    const shell = readWebSource("app/layout/AppShell.tsx");
    const explorer = readWebSource("components/layout/ExplorerShell.tsx");
    const theme = readWebSource("styles/constitution-theme.css");

    // 360px: at 272px the project tree truncated most experiment names.
    expect(shell).toContain('default: "360px"');
    expect(shell).toContain('default: "280px"');
    expect(shell).toContain('className="h-full w-12');
    expect(shell).toContain("Boolean(inspectorSurface || inspectorSelection)");
    expect(shell).not.toContain("inspectorSurface || inspectorSelection || selection");
    expect(explorer).toContain('"flex w-12');
    // Vendored from molcrafts-ui; the 22px this once pinned was local drift
    // below the constitution's 28–32px status-bar band.
    expect(theme).toContain("--spacing-statusbar: 1.75rem");
  });

  it("keeps Dashboard exploratory and Settings rail-only", () => {
    const coreNav = readWebSource("plugins/core/navigation.tsx");
    const catalog = readWebSource("app/dashboard/layout.ts");
    const dashboard = readWebSource("app/dashboard/DashboardGrid.tsx");

    expect(coreNav).toContain("explorer: DashboardExplorer");
    expect(coreNav).toMatch(/id: "dashboard"[\s\S]*?shellMode: "explorer"/);
    expect(coreNav).toMatch(/id: "settings"[\s\S]*?shellMode: "rail-only"/);
    // The six panels are a catalog the operator can arrange, not a fixed page.
    for (const panel of [
      "Execution status",
      "Activity",
      "Backends",
      "Run duration",
      "Schedule",
      "Needs attention",
    ]) {
      expect(catalog).toContain(panel);
    }
    expect(dashboard).toContain("Arrange");
  });

  it("gives Compare a page frame and a single matrix scrollport", () => {
    const pane = readWebSource("app/compare/ComparePane.tsx");
    const table = readWebSource("app/compare/CompareTable.tsx");
    const dock = readWebSource("app/compare/SelectionPanel.tsx");
    const dialog = readWebSource("app/compare/MetricDetailDialog.tsx");

    expect(pane).toContain("EntityPage");
    expect(pane).toContain('title="Compare"');
    expect(pane).toContain("flex flex-col overflow-hidden");
    expect(pane).not.toContain("runs from");
    expect(pane).toContain("scanMetrics(selected");
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

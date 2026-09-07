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

    expect(contextBar).toContain("h-[35px]");
    expect(contextBar).not.toContain("Filter explorer");
    expect(contextBar).not.toContain("<Input");
    expect(contextBar).not.toContain("<Search");
  });

  it("uses fixed editor chrome and reserves the inspector for contextual surfaces", () => {
    const shell = readWebSource("app/layout/AppShell.tsx");
    const explorer = readWebSource("components/layout/ExplorerShell.tsx");
    const theme = readWebSource("styles/constitution-theme.css");

    expect(shell).toContain('default: "272px"');
    expect(shell).toContain('default: "280px"');
    expect(shell).toContain('className="h-full w-12');
    expect(shell).toContain("Boolean(inspectorSurface || inspectorSelection)");
    expect(shell).not.toContain("inspectorSurface || inspectorSelection || selection");
    expect(explorer).toContain('"flex w-12');
    expect(theme).toContain("--spacing-statusbar: 1.375rem");
  });

  it("keeps Dashboard exploratory and Settings rail-only", () => {
    const coreNav = readWebSource("plugins/core/navigation.tsx");
    const dashboard = readWebSource("app/dashboard/DashboardPage.tsx");

    expect(coreNav).toContain("explorer: DashboardExplorer");
    expect(coreNav).toMatch(/id: "dashboard"[\s\S]*?shellMode: "explorer"/);
    expect(coreNav).toMatch(/id: "settings"[\s\S]*?shellMode: "rail-only"/);
    for (const panel of [
      "Execution summary",
      "Status mix",
      "Run activity",
      "Backends & failures",
      "Recent activity",
      "Timeline",
    ]) {
      expect(dashboard).toContain(panel);
    }
  });
});

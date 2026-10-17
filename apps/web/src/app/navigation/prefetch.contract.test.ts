import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "@rstest/core";

const here = dirname(fileURLToPath(import.meta.url));
const webSrc = resolve(here, "../..");
const read = (path: string): string => readFileSync(resolve(webSrc, path), "utf8");

describe("intent prefetch", () => {
  it("warms navigation chunks from the rail before click", () => {
    const rail = read("app/navigation/NavigationRail.tsx");
    const coreNav = read("plugins/core/navigation.tsx");
    expect(rail).toContain("prefetchNavigationView");
    expect(rail).toContain("onIntent");
    expect(coreNav).toContain("lazyWithPrefetch");
  });

  it("keeps default entity viewers out of the core plugin's static graph", () => {
    const register = read("app/renderers/registerRenderers.ts");
    expect(register).toContain("ProjectViewerLazy");
    expect(register).not.toMatch(/from "@\/app\/renderers\/ProjectViewer"/);
    expect(register).not.toMatch(/from "@\/app\/renderers\/RunViewer"/);
  });

  it("uses local molrs-wasm/.x86_64 in dev and npm @molcrafts/molrs on publish", () => {
    const rsbuild = read("../rsbuild.config.ts");
    const pkg = JSON.parse(read("../package.json"));
    expect(rsbuild).toContain("molrs-wasm/.x86_64");
    expect(rsbuild).toContain("resolveMolrs");
    expect(pkg.dependencies["@molcrafts/molrs"]).toBe("^0.13.2");
  });

  it("keeps KaTeX markdown off the initial graph", () => {
    const markdown = read("components/ui/markdown.tsx");
    const core = read("plugins/core/index.ts");
    expect(markdown).toContain("lazyWithPrefetch");
    expect(markdown).not.toContain("rehype-katex");
    expect(core).toContain("lazyWithPrefetch");
    expect(core).not.toMatch(/from "@\/components\/previews\/MarkdownPreview"/);
  });

  it("starts tree-row work on hover and focus", () => {
    const tree = read("app/panels/TreeView.tsx");
    expect(tree).toContain("onPrefetch");
    expect(tree).toContain("onPointerEnter");
    expect(tree).toContain("onFocus");
  });
});

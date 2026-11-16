import { describe, expect, it } from "@rstest/core";
import { categoryFromPath, matchesQuery, type SettingEntry, settingsPath } from "./settingsModel";

const known = ["appearance", "plugins", "history"];

describe("categoryFromPath", () => {
  it("reads the category from /settings/<id>", () => {
    expect(categoryFromPath(settingsPath("history"), known)).toBe("history");
  });

  it("falls back to Appearance for /settings and unknown ids", () => {
    expect(categoryFromPath("/settings", known)).toBe("appearance");
    expect(categoryFromPath("/settings/nope", known)).toBe("appearance");
  });

  it("keeps the old ui-plugins link working", () => {
    expect(categoryFromPath("/settings/ui-plugins", known)).toBe("plugins");
  });
});

describe("matchesQuery", () => {
  const entry: SettingEntry = {
    id: "molvis",
    title: "MolVis",
    description: "3D scenes for structures",
    keywords: ["molvis"],
    render: () => null,
  };

  it("needs every word, anywhere in title, description, keywords or category", () => {
    expect(matchesQuery(entry, "mol")).toBe(true);
    expect(matchesQuery(entry, "3d scenes")).toBe(true);
    expect(matchesQuery(entry, "plugins mol", "Plugins")).toBe(true);
    expect(matchesQuery(entry, "mol theme")).toBe(false);
  });

  it("matches nothing on an empty query", () => {
    expect(matchesQuery(entry, "  ")).toBe(false);
  });
});

import { describe, expect, it } from "@rstest/core";
import {
  addEditorTabInBackground,
  adjacentEditorTab,
  closeEditorTab,
  type EditorTab,
  type EditorTabsState,
  EMPTY_EDITOR_TABS,
  editorOpenMode,
  editorTabKey,
  followLocation,
  MAX_EDITOR_TABS,
  openEditorTab,
  openPreviewTab,
  parseStoredEditorTabs,
  pinEditorTab,
} from "./editorTabs";

const tab = (key: string, path = `/${key}`): EditorTab => ({ key, path, kind: "run", label: key });

const stateOf = (keys: string[], activeKey: string | null): EditorTabsState => ({
  tabs: keys.map((key) => tab(key)),
  activeKey,
});

describe("editorTabKey", () => {
  it("keeps project plugin views in independent, reusable editor tabs", () => {
    const relations = editorTabKey(
      {
        objectType: "project",
        objectId: "p1",
        pluginView: "relations",
        pluginExplorer: "knowledge",
      },
      null,
    );
    expect(relations).toBe("project:p1:plugin:relations");
    expect(relations).not.toBe(editorTabKey({ objectType: "project", objectId: "p1" }, null));
    expect(relations).not.toBe(
      editorTabKey({ objectType: "project", objectId: "p2", pluginView: "relations" }, null),
    );
    const file = { ...tab("file:note.md", "/knowledge/note.md"), kind: "knowledge" as const };
    const view = {
      ...tab(relations ?? "", "/knowledge?project=p1&plugin=relations"),
      kind: "project" as const,
    };
    const opened = followLocation(followLocation(EMPTY_EDITOR_TABS, file, null), view, null);
    expect(opened.tabs.map((tab) => tab.key)).toEqual([file.key, view.key]);
    expect(followLocation(opened, view, null).tabs).toHaveLength(2);
  });

  it("names the entity, not the view, so switching a view keeps one tab", () => {
    const overview = editorTabKey({ objectType: "run", objectId: "r1" }, null);
    const logs = editorTabKey({ objectType: "run", objectId: "r1", objectView: "logs" }, null);
    expect(overview).toBe("run:r1");
    expect(logs).toBe(overview);
  });

  it("keys a task by its run, a file by its path and a workflow by its id", () => {
    expect(
      editorTabKey({ objectType: "task", objectId: "t", taskId: "t", runId: "r1" }, null),
    ).toBe("task:r1/t");
    expect(
      editorTabKey(
        { objectType: "workspace-file", objectId: "a.py", filePath: "a.py", fileKind: "python" },
        null,
      ),
    ).toBe("file:a.py");
    expect(editorTabKey({ objectType: "workflow", objectId: "w", workflowId: "w" }, null)).toBe(
      "workflow:w",
    );
  });

  it("gives a section page a tab and leaves an empty section without one", () => {
    expect(editorTabKey(null, { id: "runs", hasLanding: true })).toBe("section:runs");
    expect(editorTabKey(null, { id: "projects", hasLanding: false })).toBeNull();
    expect(editorTabKey(null, null)).toBeNull();
  });
});

describe("openEditorTab", () => {
  it("inserts a new tab to the right of the active one and activates it", () => {
    const next = openEditorTab(stateOf(["a", "b", "c"], "a"), tab("d"));
    expect(next.tabs.map((t) => t.key)).toEqual(["a", "d", "b", "c"]);
    expect(next.activeKey).toBe("d");
  });

  it("updates an open tab in place: same position, latest path and label", () => {
    const before = stateOf(["a", "b"], "a");
    const next = openEditorTab(before, { ...tab("b"), path: "/b?tab=logs", label: "B" });
    expect(next.tabs.map((t) => t.key)).toEqual(["a", "b"]);
    expect(next.tabs[1]).toMatchObject({ path: "/b?tab=logs", label: "B" });
    expect(next.activeKey).toBe("b");
    expect(before.tabs[1]?.path).toBe("/b");
  });

  it("returns the same state when nothing changed", () => {
    const before = stateOf(["a"], "a");
    expect(openEditorTab(before, tab("a"))).toBe(before);
  });

  it("caps the open set by dropping the leftmost inactive tab", () => {
    const keys = Array.from({ length: MAX_EDITOR_TABS }, (_, i) => `t${i}`);
    const full = stateOf(keys, `t${MAX_EDITOR_TABS - 1}`);
    const next = openEditorTab(full, tab("new"));
    expect(next.tabs).toHaveLength(MAX_EDITOR_TABS);
    expect(next.tabs.some((t) => t.key === "t0")).toBe(false);
    expect(next.tabs.at(-1)?.key).toBe("new");
  });
});

describe("closeEditorTab", () => {
  it("activates the right neighbour when the active tab closes", () => {
    const { state, next } = closeEditorTab(stateOf(["a", "b", "c"], "b"), "b");
    expect(state.tabs.map((t) => t.key)).toEqual(["a", "c"]);
    expect(state.activeKey).toBe("c");
    expect(next?.key).toBe("c");
  });

  it("falls back to the left neighbour at the end of the row", () => {
    const { state, next } = closeEditorTab(stateOf(["a", "b"], "b"), "b");
    expect(state.activeKey).toBe("a");
    expect(next?.key).toBe("a");
  });

  it("leaves the active tab alone when another tab closes", () => {
    const { state, next } = closeEditorTab(stateOf(["a", "b"], "a"), "b");
    expect(state.activeKey).toBe("a");
    expect(next).toBeNull();
  });

  it("empties the editor when the last tab closes", () => {
    const { state, next } = closeEditorTab(stateOf(["a"], "a"), "a");
    expect(state).toEqual(EMPTY_EDITOR_TABS);
    expect(next).toBeNull();
  });

  it("ignores an unknown key", () => {
    const before = stateOf(["a"], "a");
    expect(closeEditorTab(before, "zz").state).toBe(before);
  });
});

describe("adjacentEditorTab", () => {
  it("wraps around in both directions", () => {
    const state = stateOf(["a", "b", "c"], "c");
    expect(adjacentEditorTab(state, 1)?.key).toBe("a");
    expect(adjacentEditorTab(state, -1)?.key).toBe("b");
  });

  it("starts from the first tab when none is active and returns null when empty", () => {
    expect(adjacentEditorTab(stateOf(["a", "b"], null), 1)?.key).toBe("a");
    expect(adjacentEditorTab(EMPTY_EDITOR_TABS, 1)).toBeNull();
  });
});

describe("parseStoredEditorTabs", () => {
  it("keeps well-formed tabs and drops the rest", () => {
    const parsed = parseStoredEditorTabs(
      JSON.stringify({
        tabs: [tab("a"), { key: 1 }, { key: "b", path: "no-slash", kind: "run", label: "b" }],
        activeKey: "a",
      }),
    );
    expect(parsed.tabs.map((t) => t.key)).toEqual(["a"]);
    expect(parsed.activeKey).toBe("a");
  });

  it("drops an active key that names no stored tab", () => {
    expect(
      parseStoredEditorTabs(JSON.stringify({ tabs: [tab("a")], activeKey: "x" })).activeKey,
    ).toBeNull();
  });

  it("returns the empty state for missing or corrupt storage", () => {
    expect(parseStoredEditorTabs(null)).toEqual(EMPTY_EDITOR_TABS);
    expect(parseStoredEditorTabs("{not json")).toEqual(EMPTY_EDITOR_TABS);
    expect(parseStoredEditorTabs(JSON.stringify([1, 2]))).toEqual(EMPTY_EDITOR_TABS);
  });
});

const previewOf = (key: string): EditorTab => ({ ...tab(key), preview: true });

describe("openPreviewTab", () => {
  it("opens the first single click as the one italic tab", () => {
    const next = openPreviewTab(stateOf(["a"], "a"), tab("b"));
    expect(next.tabs.map((item) => item.key)).toEqual(["a", "b"]);
    expect(next.tabs[1]?.preview).toBe(true);
    expect(next.activeKey).toBe("b");
  });

  it("replaces the italic tab in place and leaves concrete tabs", () => {
    const before: EditorTabsState = {
      tabs: [tab("a"), previewOf("b"), tab("c")],
      activeKey: "b",
    };
    const next = openPreviewTab(before, tab("d"));
    expect(next.tabs.map((item) => [item.key, Boolean(item.preview)])).toEqual([
      ["a", false],
      ["d", true],
      ["c", false],
    ]);
    expect(next.activeKey).toBe("d");
  });

  it("activates a concrete tab instead of demoting it", () => {
    const before: EditorTabsState = {
      tabs: [tab("a"), previewOf("b")],
      activeKey: "b",
    };
    const next = openPreviewTab(before, tab("a"));
    expect(next.activeKey).toBe("a");
    expect(next.tabs.find((item) => item.key === "a")?.preview).toBe(false);
    expect(next.tabs.find((item) => item.key === "b")?.preview).toBe(true);
  });
});

describe("pinEditorTab", () => {
  it("makes the italic tab concrete where it stands", () => {
    const before: EditorTabsState = { tabs: [previewOf("a"), tab("b")], activeKey: "a" };
    const next = pinEditorTab(before, "a");
    expect(next.tabs[0]?.preview).toBe(false);
    expect(next.tabs.map((item) => item.key)).toEqual(["a", "b"]);
    expect(next.activeKey).toBe("a");
  });

  it("leaves a concrete tab untouched", () => {
    const before = stateOf(["a"], "a");
    expect(pinEditorTab(before, "a")).toBe(before);
  });
});

describe("editorOpenMode", () => {
  it("reads a preview or pin navigation and follows anything else", () => {
    expect(editorOpenMode({ editorOpen: "preview" })).toBe("preview");
    expect(editorOpenMode({ editorOpen: "pin" })).toBe("pin");
    expect(editorOpenMode(null)).toBe("follow");
    expect(editorOpenMode({ editorOpen: "nope" })).toBe("follow");
  });
});

describe("followLocation", () => {
  it("closes a requested tab once the URL has left it", () => {
    const next = followLocation(stateOf(["a", "b"], "a"), tab("b"), "a");
    expect(next.tabs.map((t) => t.key)).toEqual(["b"]);
    expect(next.activeKey).toBe("b");
  });

  it("keeps the tab while the URL is still on it (navigation blocked)", () => {
    const before = stateOf(["a", "b"], "a");
    const next = followLocation(before, tab("a"), "a");
    expect(next.tabs.map((t) => t.key)).toEqual(["a", "b"]);
    expect(next.activeKey).toBe("a");
  });

  it("empties the editor when the last tab closes onto a page with no tab", () => {
    expect(followLocation(stateOf(["a"], "a"), null, "a")).toEqual(EMPTY_EDITOR_TABS);
  });

  it("clears the active tab, keeping the set, on a page with no tab", () => {
    const next = followLocation(stateOf(["a", "b"], "a"), null, null);
    expect(next.tabs).toHaveLength(2);
    expect(next.activeKey).toBeNull();
  });

  it("keeps an italic tab italic when its view changes", () => {
    const before: EditorTabsState = { tabs: [previewOf("a")], activeKey: "a" };
    const next = followLocation(before, { ...tab("a"), path: "/a?tab=logs" }, null, "follow");
    expect(next.tabs[0]).toMatchObject({ path: "/a?tab=logs", preview: true });
  });

  it("pins on a double-click navigation", () => {
    const before: EditorTabsState = { tabs: [previewOf("a")], activeKey: "a" };
    const next = followLocation(before, tab("a"), null, "pin");
    expect(next.tabs[0]?.preview).toBe(false);
  });

  it("opens a single click as a preview tab", () => {
    const next = followLocation(stateOf(["a"], "a"), tab("b"), null, "preview");
    expect(next.tabs.find((item) => item.key === "b")?.preview).toBe(true);
  });
});

describe("addEditorTabInBackground", () => {
  it("adds after the active tab and keeps the active tab", () => {
    const next = addEditorTabInBackground(stateOf(["a", "b"], "a"), tab("c"));
    expect(next.tabs.map((t) => t.key)).toEqual(["a", "c", "b"]);
    expect(next.activeKey).toBe("a");
  });

  it("leaves an already open tab where it is", () => {
    const before = stateOf(["a", "b"], "a");
    expect(addEditorTabInBackground(before, tab("b"))).toBe(before);
  });
});

describe("the cap never drops the active tab", () => {
  it("evicts the leftmost inactive tab even when the active one is leftmost", () => {
    const keys = Array.from({ length: MAX_EDITOR_TABS }, (_, i) => `t${i}`);
    const next = addEditorTabInBackground(stateOf(keys, "t0"), tab("bg"));
    expect(next.activeKey).toBe("t0");
    expect(next.tabs.some((t) => t.key === "t0")).toBe(true);
    expect(next.tabs.some((t) => t.key === "t1")).toBe(false);
    expect(next.tabs).toHaveLength(MAX_EDITOR_TABS);
  });
});

import { describe, expect, it } from "@rstest/core";
import { renderToStaticMarkup } from "react-dom/server";
import { buildEmptySnapshot } from "@/app/state/api";
import type { Selection } from "@/app/types";
import { buildFilesExplorerNodes, detectFileKind } from "./FilesExplorer";
import type { SyncRule } from "./syncRules";

describe("Files explorer", () => {
  it("detects supported file kinds case-insensitively", () => {
    expect(detectFileKind("config.YAML")).toBe("yaml");
    expect(detectFileKind("notes.md")).toBe("markdown");
    expect(detectFileKind("archive.bin")).toBe("unknown");
  });

  it("keeps directory writes gated and file selections typed", () => {
    const snapshot = buildEmptySnapshot();
    snapshot.workspaceRoot = {
      id: "root",
      name: "workspace",
      path: "",
      kind: "directory",
      childrenLoaded: true,
      sizeBytes: 0,
      updatedAt: "2026-08-30T12:00:00Z",
      children: [
        {
          id: "config",
          name: "config.YAML",
          path: "config.YAML",
          kind: "file",
          children: [],
          sizeBytes: 12,
          updatedAt: "2026-08-30T12:00:00Z",
        },
      ],
    };
    let selected: Selection | null = null;
    const [root] = buildFilesExplorerNodes(snapshot, {
      onSelect: (next) => {
        selected = next;
      },
      onCreateDirectory: () => undefined,
      onCreateFile: () => undefined,
      pathContext: { root: "/workspace", workspace: null },
      onRefresh: () => undefined,
      writeDeniedReason: "Viewer role cannot modify files.",
    });

    expect(root?.actions?.find((action) => action.id === "new-file")).toMatchObject({
      disabled: true,
      title: "Viewer role cannot modify files.",
    });
    expect(root?.children?.[0]?.actions?.some((action) => action.id === "sync")).toBe(false);
    root?.children?.[0]?.onSelect?.();
    expect(selected).toMatchObject({
      objectType: "workspace-file",
      filePath: "config.YAML",
      fileKind: "yaml",
    });
  });

  it("offers Sync on a remote tree and marks a saved rule", () => {
    const snapshot = buildEmptySnapshot();
    snapshot.workspaceRoot = {
      id: "/lab/nve",
      name: "nve",
      path: "/lab/nve",
      kind: "directory",
      childrenLoaded: true,
      sizeBytes: 0,
      updatedAt: "2026-10-20T12:00:00Z",
      children: [
        {
          id: "/lab/nve/note.md",
          name: "note.md",
          path: "/lab/nve/note.md",
          kind: "file",
          children: [],
          sizeBytes: 4,
          updatedAt: "2026-10-20T12:00:00Z",
        },
        {
          id: "/lab/nve/experiments",
          name: "experiments",
          path: "/lab/nve/experiments",
          kind: "directory",
          children: [],
          childrenLoaded: true,
          sizeBytes: 0,
          updatedAt: "2026-10-20T12:00:00Z",
        },
      ],
    };
    const rule = (path: string, when: SyncRule["when"]): SyncRule => ({
      id: path,
      path,
      kind: path.endsWith(".md") ? "file" : "directory",
      direction: "pull",
      content: "everything",
      types: [],
      extraFiles: "keep",
      when,
      intervalMinutes: 15,
      lastRunAt: null,
      lastStatus: null,
      lastOutput: null,
    });
    let opened = "";
    const [root] = buildFilesExplorerNodes(snapshot, {
      onSelect: () => undefined,
      onCreateDirectory: () => undefined,
      onCreateFile: () => undefined,
      pathContext: { root: "/lab/nve", workspace: null },
      onRefresh: () => undefined,
      writeDeniedReason: null,
      workspaceRoot: "/lab/nve",
      rules: [rule("note.md", "manual"), rule("experiments", "interval")],
      onSync: (target) => {
        opened = target.path;
      },
    });
    const file = root?.children?.[0];
    const folder = root?.children?.[1];
    if (!root || !file || !folder) throw new Error("tree is missing nodes");
    expect(file.actions?.some((action) => action.label === "Sync…")).toBe(true);
    expect(folder.actions?.some((action) => action.label === "Sync…")).toBe(true);
    expect(root.right).toBeUndefined();
    const sync = file.actions?.find((action) => action.id === "sync");
    if (!sync || !file.right || !folder.right) throw new Error("sync action or mark is missing");
    sync.onSelect();
    expect(opened).toBe("/lab/nve/note.md");
    expect(renderToStaticMarkup(file.right)).toContain('aria-label="Syncs when you ask"');
    expect(renderToStaticMarkup(folder.right)).toContain('aria-label="Syncs every 15 minutes"');
  });
});

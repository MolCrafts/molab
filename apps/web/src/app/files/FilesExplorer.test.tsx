import { describe, expect, it } from "@rstest/core";
import { buildEmptySnapshot } from "@/app/state/api";
import type { Selection } from "@/app/types";
import { buildFilesExplorerNodes, detectFileKind } from "./FilesExplorer";

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
    root?.children?.[0]?.onSelect?.();
    expect(selected).toMatchObject({
      objectType: "workspace-file",
      filePath: "config.YAML",
      fileKind: "yaml",
    });
  });
});

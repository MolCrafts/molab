import { describe, expect, it } from "@rstest/core";
import { fileEditorMark, isEditorDirty, setEditorDirty } from "./dirtyEditors";

describe("dirty editors", () => {
  it("marks every view of a page under its base path, and nothing beside it", () => {
    const marked = new Set(["/projects/p/experiments/e"]);
    expect(isEditorDirty(marked, "/projects/p/experiments/e/workflow")).toBe(true);
    expect(isEditorDirty(marked, "/projects/p/experiments/e?filter=x")).toBe(true);
    expect(isEditorDirty(marked, "/projects/p/experiments/e2")).toBe(false);
    expect(isEditorDirty(marked, "/projects/p")).toBe(false);
  });

  it("marks one file's editor, not every file on the Files page", () => {
    const marked = new Set([fileEditorMark("docs/README.md")]);
    expect(isEditorDirty(marked, "/workspace?file=docs%2FREADME.md&fileKind=markdown")).toBe(true);
    expect(isEditorDirty(marked, "/workspace?file=docs%2FREADME.md")).toBe(true);
    expect(isEditorDirty(marked, "/workspace?file=docs%2FREADME.md.bak")).toBe(false);
    expect(isEditorDirty(marked, "/workspace?file=main.tex")).toBe(false);
    // Either spelling of the same path is the same editor.
    expect(isEditorDirty(new Set([fileEditorMark("a b.md")]), "/workspace?file=a%20b.md")).toBe(
      true,
    );
  });

  it("adds and removes a mark", () => {
    setEditorDirty("/a", true);
    setEditorDirty("/a", false);
    expect(isEditorDirty(new Set(), "/a")).toBe(false);
  });
});

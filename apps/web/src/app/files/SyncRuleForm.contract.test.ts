import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "@rstest/core";

const here = dirname(fileURLToPath(import.meta.url));
const form = readFileSync(resolve(here, "SyncRuleForm.tsx"), "utf8");
const explorer = readFileSync(resolve(here, "FilesExplorer.tsx"), "utf8");
const strip = readFileSync(
  resolve(here, "../../components/workbench/WorkbenchStatusStrip.tsx"),
  "utf8",
);
const tree = readFileSync(resolve(here, "../panels/TreeView.tsx"), "utf8");

describe("path sync form", () => {
  it("is a file-tree form, not an rsync flag menu", () => {
    expect(explorer).toContain('label: "Sync…"');
    expect(explorer).toContain("activeWorkspace?.isRemote");
    expect(explorer).toContain("!activeWorkspace.unreachable");
    expect(explorer).toContain("!activeWorkspace.needsAuth");
    expect(form).toContain("Bring here");
    expect(form).toContain("Send there");
    expect(form).toContain("This changes the remote copy.");
    expect(form).toContain("Records and notes");
    expect(form).toContain("Skip bulk products");
    expect(form).toContain("Selected types");
    expect(form).toContain("When this workspace opens");
    expect(form).toContain("Remove files the source does not have");
    expect(form).toContain("Sync now");
    expect(form).toContain("Preview");
    expect(form).toContain('type="checkbox"');
    expect(form).not.toContain("--include");
    expect(form).not.toContain("--exclude");
    expect(form).not.toContain("--delete");
    expect(form).not.toContain("--dry-run");
    expect(form).not.toContain("Dialog");
    expect(form).not.toContain("<textarea");
    expect(form).toContain("createPortal");
    expect(tree).toContain("data-tree-id");
    expect(strip).not.toContain("RsyncMenu");
  });
});

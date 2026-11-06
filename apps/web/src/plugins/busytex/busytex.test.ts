import { beforeEach, describe, expect, it } from "@rstest/core";
import { filePreviewPluginRegistry } from "@/lib/file-preview-plugins";
import { createPluginAPI } from "@/plugins/api/create_api";
import { resetContributionRuntimeForTests } from "@/plugins/contribution-runtime";
import { compileRequest, MAIN_TEX_PATH, TEXLIVE_REMOTE_ENDPOINT } from "./compile-request";
import { logSummary } from "./log";
import busytexPlugin from "./plugin";
import { manuscriptFiles } from "./siblings";

beforeEach(() => {
  resetContributionRuntimeForTests();
});

describe("busytex preview plugin", () => {
  it("claims .tex and .ltx on the editor preview tab", () => {
    const { api } = createPluginAPI("busytex");
    busytexPlugin.activate(api);

    const resolved = filePreviewPluginRegistry.getPluginForFile("notes.tex", "a/notes.tex");
    expect(resolved?.id).toBe("busytex:preview");
    expect(resolved?.name).toBe("BusyTeX");
    expect(filePreviewPluginRegistry.getPluginForFile("letter.ltx", "a/letter.ltx")?.id).toBe(
      "busytex:preview",
    );
    expect(filePreviewPluginRegistry.getPluginForFile("notes.md", "a/notes.md")).toBeNull();
  });
});

describe("compileRequest", () => {
  it("compiles the buffer as main.tex and fetches missing packages on demand", () => {
    expect(compileRequest("\\documentclass{article}")).toEqual({
      input: "\\documentclass{article}",
      mainTexPath: MAIN_TEX_PATH,
      bibtex: false,
      biber: false,
      makeindex: false,
      rerun: true,
      verbose: "silent",
      shellEscape: false,
      remoteEndpoint: TEXLIVE_REMOTE_ENDPOINT,
      additionalFiles: [],
    });
  });
});

describe("manuscriptFiles", () => {
  it("stages the nve-drift bibliography, tables, and figures beside main.tex", () => {
    const source = [
      "\\addbibresource{references.bib}",
      "\\graphicspath{{figures/}}",
      "\\includegraphics[width=\\textwidth]{fig1_translation}",
      "\\csname @@input\\endcsname figures/tab_kick.tex",
    ].join("\n");
    const files = manuscriptFiles(source, "projects/nve-drift/manuscript/nve-drift.tex").map(
      (file) => [file.enginePath, file.workspacePath, file.binary],
    );

    expect(files).toContainEqual([
      "references.bib",
      "projects/nve-drift/manuscript/references.bib",
      false,
    ]);
    expect(files).toContainEqual([
      "main.bbl",
      "projects/nve-drift/manuscript/nve-drift.bbl",
      false,
    ]);
    expect(files).toContainEqual([
      "figures/tab_kick.tex",
      "projects/nve-drift/manuscript/figures/tab_kick.tex",
      false,
    ]);
    expect(files).toContainEqual([
      "figures/fig1_translation.pdf",
      "projects/nve-drift/manuscript/figures/fig1_translation.pdf",
      true,
    ]);
  });
});

describe("logSummary", () => {
  it("prefers the TeX error over the engine's trailer", () => {
    expect(
      logSummary("$ pdflatex main.tex\nEXITCODE: 1\nLOG:\n! Undefined control sequence.\n======\n"),
    ).toBe("! Undefined control sequence.");
    expect(logSummary("   ")).toBe("The engine returned no PDF.");
  });
});

import { describe, expect, it } from "@rstest/core";
import {
  docHeadings,
  formatComponent,
  insertAfterBlock,
  keepTrailing,
  parseAttrs,
  parseDocBlocks,
  replaceBlock,
  toggleTaskLine,
} from "./blocks";

const DOC = [
  "Intro with a [ref](molab:run/abc).",
  "",
  "## Evidence",
  "",
  '!!! warning "Not yet tested"',
  "    The 2 fs runs failed.",
  "",
  "    Second paragraph.",
  "",
  '::molab-run-table{experiment="molab:experiment/x" columns=timestep_fs,energy_drift}',
  "",
  '=== "Chart"',
  "",
  "    chart body",
  "",
  '=== "Runs"',
  "    runs body",
  "",
  "```",
  "!!! note inside a fence",
  "```",
  "### Sub",
  "- [ ] open item",
  "- [x] done item",
].join("\n");

describe("parseDocBlocks", () => {
  const blocks = parseDocBlocks(DOC);

  it("splits markdown, admonition, component and tabs in order", () => {
    expect(blocks.map((block) => block.kind)).toEqual([
      "markdown",
      "admonition",
      "markdown",
      "component",
      "markdown",
      "tabs",
      "markdown",
    ]);
  });

  it("reads an admonition's type, title and dedented body", () => {
    const adm = blocks[1];
    expect(adm).toMatchObject({
      kind: "admonition",
      type: "warning",
      title: "Not yet tested",
      fold: "none",
    });
    if (adm?.kind !== "admonition") throw new Error("not an admonition");
    expect(adm.body).toBe("The 2 fs runs failed.\n\nSecond paragraph.");
    expect(adm.start).toBe(4);
    expect(adm.end).toBe(8);
  });

  it("reads a directive's attributes", () => {
    const comp = blocks[3];
    if (comp?.kind !== "component") throw new Error("not a component");
    expect(comp.name).toBe("molab-run-table");
    expect(comp.attrs).toEqual({
      experiment: "molab:experiment/x",
      columns: "timestep_fs,energy_drift",
    });
    expect(comp.syntax).toBe("directive");
  });

  it("groups consecutive tabs", () => {
    const tabs = blocks[5];
    if (tabs?.kind !== "tabs") throw new Error("not tabs");
    expect(tabs.tabs).toEqual([
      { label: "Chart", body: "chart body" },
      { label: "Runs", body: "runs body" },
    ]);
  });

  it("leaves a fenced block untouched", () => {
    const last = blocks[6];
    if (last?.kind !== "markdown") throw new Error("not markdown");
    expect(last.text).toContain("!!! note inside a fence");
  });

  it("reads folding admonitions and the html form of a component", () => {
    const parsed = parseDocBlocks(
      [
        '??? abstract "Abstract"',
        "    text",
        "???+ tip",
        "    open",
        '<molab-todo-list source="record"></molab-todo-list>',
      ].join("\n"),
    );
    expect(parsed.map((b) => (b.kind === "admonition" ? b.fold : b.kind))).toEqual([
      "closed",
      "open",
      "component",
    ]);
    const html = parsed[2];
    if (html?.kind !== "component") throw new Error("not a component");
    expect(html).toMatchObject({
      name: "molab-todo-list",
      attrs: { source: "record" },
      syntax: "html",
    });
  });

  it("round-trips an untouched document line for line", () => {
    const rebuilt = blocks.map((block) => block.source).join("\n");
    expect(rebuilt).toBe(DOC);
  });
});

describe("edits", () => {
  const blocks = parseDocBlocks(DOC);

  it("replaces one block's lines", () => {
    const adm = blocks[1];
    if (!adm) throw new Error("missing");
    const next = replaceBlock(DOC, adm, '!!! tip "Done"\n    Fixed.');
    expect(next.split("\n").slice(4, 6)).toEqual(['!!! tip "Done"', "    Fixed."]);
    expect(next).toContain("## Evidence");
    expect(next).toContain("::molab-run-table");
  });

  it("inserts after a block with one blank line between", () => {
    const md = blocks[0];
    if (!md) throw new Error("missing");
    const next = insertAfterBlock("Para.", parseDocBlocks("Para.")[0] ?? md, "::molab-todo-list");
    expect(next).toBe("Para.\n\n::molab-todo-list");
  });

  it("formats a directive with quoted values only when needed", () => {
    expect(formatComponent("molab-run-ref", { ref: "molab:run/abc", label: "ase nve" })).toBe(
      '::molab-run-ref{ref=molab:run/abc label="ase nve"}',
    );
    expect(formatComponent("molab-todo-list", {})).toBe("::molab-todo-list");
  });

  it("parses bare, quoted and flag attributes", () => {
    expect(parseAttrs('q="say &quot;hi&quot; &amp; &lt;go"')).toEqual({ q: 'say "hi" & <go' });
    expect(parseAttrs(`a=1 b="two words" c='x' flag`)).toEqual({
      a: "1",
      b: "two words",
      c: "x",
      flag: "true",
    });
  });

  it("toggles a task line", () => {
    const lines = DOC.split("\n");
    const open = lines.indexOf("- [ ] open item");
    const toggled = toggleTaskLine(DOC, open).split("\n");
    expect(toggled[open]).toBe("- [x] open item");
    expect(toggleTaskLine(DOC, open + 1).split("\n")[open + 1]).toBe("- [ ] done item");
    expect(toggleTaskLine(DOC, 0)).toBe(DOC);
  });
});

describe("docHeadings", () => {
  it("lists h2 and h3 outside fences and admonitions with unique ids", () => {
    const headings = docHeadings(
      parseDocBlocks(
        ["## Results", "### Results", "!!! note", "    ## hidden", "## Results"].join("\n"),
      ),
    );
    expect(headings).toEqual([
      { level: 2, text: "Results", id: "results", line: 0 },
      { level: 3, text: "Results", id: "results-1", line: 1 },
      { level: 2, text: "Results", id: "results-2", line: 4 },
    ]);
  });
});

describe("HTML documents", () => {
  it("keeps <molab-markdown> wrapper lines out of the prose they wrap", () => {
    const body = [
      "<molab-markdown>",
      "## Results",
      "",
      "Prose.",
      "</molab-markdown>",
      '<molab-run-table experiment="molab:experiment/x"></molab-run-table>',
    ].join("\n");
    const blocks = parseDocBlocks(body);
    expect(blocks.map((block) => [block.kind, block.start, block.end])).toEqual([
      ["markdown", 0, 1],
      ["markdown", 1, 4],
      ["markdown", 4, 5],
      ["component", 5, 6],
    ]);
    expect(blocks.map((block) => block.source).join("\n")).toBe(body);
    expect(docHeadings(blocks).map((h) => h.id)).toEqual(["results"]);
  });
});

describe("keepTrailing", () => {
  it("keeps the block's own trailing blank lines, not the editor's", () => {
    expect(keepTrailing("a\n", "a b\n\n")).toBe("a b\n");
    expect(keepTrailing("a", "a b\n")).toBe("a b");
  });
});

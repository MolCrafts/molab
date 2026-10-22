import { describe, expect, it } from "@rstest/core";
import { joinMarkdownCells, splitMarkdownCells } from "./markdownCells";

describe("splitMarkdownCells", () => {
  it("returns one empty cell for blank input", () => {
    expect(splitMarkdownCells("")).toEqual([""]);
    expect(splitMarkdownCells("  \n\n")).toEqual([""]);
  });

  it("splits paragraphs on a blank line", () => {
    expect(splitMarkdownCells("one\n\ntwo")).toEqual(["one", "two"]);
  });

  it("keeps a heading as its own cell", () => {
    expect(splitMarkdownCells("# Title\n\nbody")).toEqual(["# Title", "body"]);
    expect(splitMarkdownCells("# Title\nbody")).toEqual(["# Title", "body"]);
  });

  it("keeps a fenced block as one cell", () => {
    const src = "intro\n\n```py\nprint(1)\n\nprint(2)\n```\n\noutro";
    expect(splitMarkdownCells(src)).toEqual(["intro", "```py\nprint(1)\n\nprint(2)\n```", "outro"]);
  });

  it("keeps a list together without blank lines", () => {
    expect(splitMarkdownCells("- a\n- b\n- c")).toEqual(["- a\n- b\n- c"]);
  });
});

describe("joinMarkdownCells", () => {
  it("joins with a blank line and drops empties", () => {
    expect(joinMarkdownCells(["# Title", "", "body"])).toBe("# Title\n\nbody");
  });

  it("round-trips a split document", () => {
    const src = "# Title\n\nA paragraph.\n\n- a\n- b\n\n```\nx\n```";
    expect(joinMarkdownCells(splitMarkdownCells(src))).toBe(src);
  });
});

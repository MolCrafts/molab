import { describe, expect, it } from "@rstest/core";
import { parseTablePreview, splitDelimited } from "./tablePreview";

describe("splitDelimited", () => {
  it("honours quoted fields and doubled quotes", () => {
    expect(splitDelimited('a,"b,c","say ""hi""",', ",")).toEqual(["a", "b,c", 'say "hi"', ""]);
  });
});

describe("parseTablePreview", () => {
  it("reads the header and the first rows", () => {
    const table = parseTablePreview("ligand,smiles\nL-1,CCO\nL-2,CC\nL-3,C\n", "l.csv", 2);
    expect(table.header).toEqual(["ligand", "smiles"]);
    expect(table.rows).toEqual([
      ["L-1", "CCO"],
      ["L-2", "CC"],
    ]);
    expect(table.totalRows).toBe(3);
  });

  it("detects tabs and drops a cut-off last line", () => {
    const table = parseTablePreview("a\tb\n1\t2\n3\t", "x.txt", 10, true);
    expect(table.header).toEqual(["a", "b"]);
    expect(table.rows).toEqual([["1", "2"]]);
    expect(table.partial).toBe(true);
  });
});

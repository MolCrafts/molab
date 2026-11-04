import { describe, expect, it } from "@rstest/core";

import { parseStructure } from "./structureGraph";
import { structureSvg } from "./structureSvg";

describe("structureSvg", () => {
  it("draws a Kekulé ring as an SVG formula", () => {
    const graph = parseStructure(
      "ring.mol2",
      `@<TRIPOS>MOLECULE
b
6 6
@<TRIPOS>ATOM
1 C 0 0 0 ca
2 C 1.4 0 0 ca
3 C 2.1 1.2 0 ca
4 C 1.4 2.4 0 ca
5 C 0 2.4 0 ca
6 C -0.7 1.2 0 ca
@<TRIPOS>BOND
1 1 2 ar
2 2 3 ar
3 3 4 ar
4 4 5 ar
5 5 6 ar
6 6 1 ar
`,
    );
    expect(graph).not.toBeNull();
    const svg = structureSvg(graph ?? { formula: "", atoms: [], bonds: [] });
    expect(svg.startsWith("<svg")).toBe(true);
    expect(svg).toContain('fill="transparent"');
  });
});

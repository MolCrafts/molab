import { describe, expect, it } from "@rstest/core";

import { hillFormula, parseStructure } from "./structureGraph";

const pdb = `ATOM      1 C1   MOL     1       0.000   0.000   0.000  1.00  0.00           C
ATOM      2 C2   MOL     1       1.400   0.000   0.000  1.00  0.00           C
ATOM      3 BR1  MOL     1       2.800   0.000   0.000  1.00  0.00          BR
ATOM      4 H1   MOL     1       0.000   1.100   0.000  1.00  0.00           H
CONECT    2    1    3
CONECT    1    2    4
CONECT    3    2
END
`;

const benzene = `@<TRIPOS>MOLECULE
b
6 6 0 0 0
SMALL
USER_CHARGES

@<TRIPOS>ATOM
1 C1 0 0 0 ca 1 MOL 0
2 C2 1.4 0 0 ca 1 MOL 0
3 C3 2.1 1.2 0 ca 1 MOL 0
4 C4 1.4 2.4 0 ca 1 MOL 0
5 C5 0 2.4 0 ca 1 MOL 0
6 C6 -0.7 1.2 0 ca 1 MOL 0
@<TRIPOS>BOND
1 1 2 ca-ca
2 2 3 ca-ca
3 3 4 ca-ca
4 4 5 ca-ca
5 5 6 ca-ca
6 6 1 ca-ca
`;

describe("hillFormula", () => {
  it("puts carbon and hydrogen first", () => {
    expect(
      hillFormula(
        new Map([
          ["Br", 1],
          ["H", 10],
          ["C", 9],
        ]),
      ),
    ).toBe("C9H10Br");
  });
});

describe("parseStructure", () => {
  it("reads PDB connectivity and folds explicit hydrogens into the formula", () => {
    const graph = parseStructure("piece.pdb", pdb);
    expect(graph?.formula).toBe("C2HBr");
    expect(graph?.atoms.map((atom) => atom.element)).toEqual(["C", "C", "Br"]);
    expect(graph?.atoms[0]?.hydrogens).toBe(1);
    expect(graph?.bonds).toEqual([
      { i: 0, j: 1, order: 1 },
      { i: 1, j: 2, order: 1 },
    ]);
  });

  it("draws a Kekulé ring from aromatic MOL2 types", () => {
    const graph = parseStructure("ring.mol2", benzene);
    expect(graph?.formula).toBe("C6");
    expect(graph?.bonds.filter((bond) => bond.order === 2)).toHaveLength(3);
  });

  it("draws a Kekulé ring from aromatic bond lengths when the file has no bond order", () => {
    const xyz = `6
benzene
C 1.400000 0.000000 0
C 0.700000 1.212436 0
C -0.700000 1.212436 0
C -1.400000 0.000000 0
C -0.700000 -1.212436 0
C 0.700000 -1.212436 0
`;
    const graph = parseStructure("benzene.xyz", xyz);
    expect(graph?.bonds.filter((bond) => bond.order === 2)).toHaveLength(3);
  });

  it("leaves a saturated ring as single bonds", () => {
    const xyz = `6
cyclohexane
C 1.540000 0.000000 0
C 0.770000 1.333680 0
C -0.770000 1.333680 0
C -1.540000 0.000000 0
C -0.770000 -1.333680 0
C 0.770000 -1.333680 0
`;
    const graph = parseStructure("cyclohexane.xyz", xyz);
    expect(graph?.bonds.filter((bond) => bond.order === 2)).toHaveLength(0);
    expect(graph?.bonds).toHaveLength(6);
  });

  it("perceives a bond in an XYZ coordinate file", () => {
    const xyz = "2\ncomment\nC 0 0 0\nC 1.5 0 0\n";
    const graph = parseStructure("pair.xyz", xyz);
    expect(graph?.bonds).toEqual([{ i: 0, j: 1, order: 1 }]);
  });

  it("leaves a log alone", () => {
    expect(parseStructure("run.log", "Per MPI rank memory allocation")).toBeNull();
  });
});

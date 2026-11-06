import { defaultCanvasTheme, MoleculeLayout, SketchBoard } from "@molcrafts/molvis-sketch";

import type { StructureGraph } from "./structureGraph";

/** 2D structural formula as SVG, laid out by molvis sketch. */
export const structureSvg = (graph: StructureGraph): string => {
  const placed = new MoleculeLayout().place({
    atoms: graph.atoms.map((atom) => ({
      element: atom.element,
      ...(atom.charge ? { charge: atom.charge } : {}),
      ...(atom.hydrogens ? { hydrogens: atom.hydrogens } : {}),
    })),
    bonds: graph.bonds.map((bond) => ({ i: bond.i, j: bond.j, order: bond.order })),
  });
  const board = new SketchBoard({ omitCarbonLabel: true });
  board.renderer.setTheme({ ...defaultCanvasTheme(), background: "transparent" });
  board.loadMoleculeData(placed);
  return board.toSvg({
    width: 520,
    height: 320,
    padding: 20,
    background: "transparent",
  });
};

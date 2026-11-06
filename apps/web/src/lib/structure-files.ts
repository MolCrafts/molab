/** Chemical structure files a browser can draw as a 2D formula and a 3D model. */

const STRUCTURE = /\.(pdb|ent|brk|xyz|extxyz|exyz|cif|mmcif|sdf|mol|mol2|gro|cube|cub)$/i;

/** Extensions including the dot, for file-preview registration. */
export const CHEMICAL_STRUCTURE_EXTENSIONS = [
  ".pdb",
  ".ent",
  ".brk",
  ".xyz",
  ".extxyz",
  ".exyz",
  ".cif",
  ".mmcif",
  ".sdf",
  ".mol",
  ".mol2",
  ".gro",
  ".cube",
  ".cub",
] as const;

export const isChemicalStructureName = (name: string): boolean => STRUCTURE.test(name);

/**
 * Prefer a connection table over bare coordinates when several files describe
 * the same molecule. Lower is better.
 */
export const structureRank = (name: string): number => {
  const dot = name.lastIndexOf(".");
  const ext = (dot < 0 ? "" : name.slice(dot + 1)).toLowerCase();
  const order = [
    "mol2",
    "sdf",
    "mol",
    "pdb",
    "ent",
    "brk",
    "gro",
    "cif",
    "mmcif",
    "xyz",
    "extxyz",
    "exyz",
    "cube",
    "cub",
  ];
  const index = order.indexOf(ext);
  return index < 0 ? order.length : index;
};

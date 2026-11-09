/** Chemical structure files a browser can draw as a 3D scene. */

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

/**
 * LAMMPS data files: the periodic cell plus the full topology. molvis-stage
 * reads them by extension (format "lammps"). `.lammps` stays out — that is
 * `log.lammps`, a solver log.
 */
export const LAMMPS_DATA_EXTENSIONS = [".data", ".lmp", ".lammpsdata"] as const;

const LAMMPS_DATA = /\.(data|lmp|lammpsdata)$/i;

export const isChemicalStructureName = (name: string): boolean => STRUCTURE.test(name);

export const isLammpsDataName = (name: string): boolean => LAMMPS_DATA.test(name);

/** A file the output pane should hand to the 3D structure preview. */
export const isStructurePreviewName = (name: string): boolean =>
  isChemicalStructureName(name) || isLammpsDataName(name);

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

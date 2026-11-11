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

/** Binary trajectories molvis reads from bytes. A DCD is not UTF-8. */
export const BINARY_TRAJECTORY_EXTENSIONS = [".dcd"] as const;

const BINARY_TRAJECTORY = /\.dcd$/i;

export const isChemicalStructureName = (name: string): boolean => STRUCTURE.test(name);

export const isLammpsDataName = (name: string): boolean => LAMMPS_DATA.test(name);

export const isBinaryTrajectoryName = (name: string): boolean => BINARY_TRAJECTORY.test(name);

/** A file the output pane should hand to the 3D structure preview. */
export const isStructurePreviewName = (name: string): boolean =>
  isChemicalStructureName(name) || isLammpsDataName(name);

/**
 * Prefer a connection table over bare coordinates when several files describe
 * the same molecule. Lower is better. `.dcd` is last: it is a trajectory,
 * not the default frame.
 */
const STRUCTURE_RANK = [
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
  "data",
  "lmp",
  "lammpsdata",
  "dcd",
] as const;

const extensionOf = (name: string): string => {
  const dot = name.lastIndexOf(".");
  return (dot < 0 ? "" : name.slice(dot + 1)).toLowerCase();
};

/** True when the suffix is one `structureRank` orders, including `.dcd`. */
export const isRankedStructureName = (name: string): boolean =>
  (STRUCTURE_RANK as readonly string[]).includes(extensionOf(name));

export const structureRank = (name: string): number => {
  const index = (STRUCTURE_RANK as readonly string[]).indexOf(extensionOf(name));
  return index < 0 ? STRUCTURE_RANK.length : index;
};

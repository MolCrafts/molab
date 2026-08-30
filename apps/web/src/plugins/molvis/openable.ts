/** Formats molvis-stage can load in-browser today. Not a file tree. */

const TRAJECTORY = /\.(lammpstrj|lmptrj|lammpsdump|dump|xyz|extxyz|pdb)$/i;
const LOG = /(^log\.lammps$|\.lammps\.log$|^lmp\.log$)/i;
const ZARR_GROUP = /(?:^|\/)(?:frame|trajectory|meta)\/zarr\.json$/i;

const posix = (relPath: string): string => relPath.replace(/\\/g, "/").replace(/\/+$/, "");

/** Host metrics Zarr — molplot's surface, never a molvis trajectory. */
const isMlpZarrPath = (path: string, name: string): boolean =>
  path.includes(".mlp.zarr") || name.includes(".mlp.zarr");

const hasMrecAncestor = (path: string): boolean =>
  path.split("/").some((seg) => seg.endsWith(".mrec"));

export const isMolvisTrajectoryName = (name: string): boolean => TRAJECTORY.test(name);

export const isMolvisLog = (name: string): boolean => LOG.test(name);

/**
 * True when this file is a molvis-openable ``*.mrec`` store marker.
 *
 * Matches ``*.mrec`` directories and ``*.mrec/zarr.json``. Group markers
 * (``frame|trajectory|meta/zarr.json``) match only when an ancestor path
 * segment ends with ``.mrec``. Nested array metadata is not a store.
 * Packed ``*.mrec.zip`` and bare ``*.zarr`` are not matched. ``*.mlp.zarr``
 * belongs to molplot.
 */
export const isMolvisZarr = (file: { name: string; relPath: string }): boolean => {
  const path = posix(file.relPath).toLowerCase();
  const name = file.name.toLowerCase();
  if (isMlpZarrPath(path, name)) return false;
  if (name.endsWith(".mrec.zip") || path.endsWith(".mrec.zip")) return false;
  if (name.endsWith(".mrec") || path.endsWith(".mrec")) return true;
  if (name !== "zarr.json") return false;
  if (path.endsWith(".mrec/zarr.json")) return true;
  return hasMrecAncestor(path) && ZARR_GROUP.test(path);
};

/** Store directory molvis should walk (parent of the matched marker). */
export const zarrStoreRoot = (relPath: string): string => {
  const path = posix(relPath);
  if (!path.toLowerCase().endsWith("/zarr.json")) return path;
  const parent = path.slice(0, -"/zarr.json".length);
  const parentName = parent.split("/").pop() ?? parent;
  if (/^(frame|trajectory|meta)$/i.test(parentName)) {
    const i = parent.lastIndexOf("/");
    return i < 0 ? "" : parent.slice(0, i);
  }
  return parent;
};

export const isMolvisTrajectory = (file: { name: string; relPath: string }): boolean =>
  isMolvisTrajectoryName(file.name) || isMolvisZarr(file);

/** True when molvis can actually open this file (not a nested array sidecar). */
export const isMolvisOpenable = (file: { name: string; relPath?: string }): boolean =>
  isMolvisTrajectoryName(file.name) ||
  isMolvisLog(file.name) ||
  isMolvisZarr({ name: file.name, relPath: file.relPath ?? file.name });

export interface MolvisListedFile {
  name: string;
  relPath: string;
}

/**
 * One row per classic file, and one row per ``*.mrec`` store (markers
 * collapsed to the store directory name).
 */
export const uniqueMolvisFiles = <T extends MolvisListedFile>(files: readonly T[]): T[] => {
  const seen = new Set<string>();
  const out: T[] = [];
  for (const file of files) {
    if (!isMolvisOpenable(file)) continue;
    if (isMolvisZarr(file)) {
      const root = zarrStoreRoot(file.relPath);
      const key = `zarr:${root}`;
      if (seen.has(key)) continue;
      seen.add(key);
      const name = root.split("/").pop() || root || file.name;
      out.push({ ...file, relPath: file.relPath, name });
      continue;
    }
    if (seen.has(file.relPath)) continue;
    seen.add(file.relPath);
    out.push(file);
  }
  return out;
};

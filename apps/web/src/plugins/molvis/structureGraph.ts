/**
 * Connection table for a 2D formula, read from the structure text itself.
 *
 * PDB CONECT, MOL2/SDF bonds, or a distance guess for bare XYZ. Hydrogens
 * bonded to one heavy atom become implicit so the drawing is a formula,
 * not a ball of protons. Aromatic Sybyl types (`ca-ca`), and 5- or 6-rings
 * whose bonds are all aromatic lengths, get a Kekulé alternation.
 */

export interface SketchAtom {
  element: string;
  charge?: number;
  hydrogens?: number;
}

export interface SketchBond {
  i: number;
  j: number;
  order: number;
}

export interface StructureGraph {
  /** Hill formula of every atom in the file, including explicit hydrogens. */
  formula: string;
  atoms: SketchAtom[];
  bonds: SketchBond[];
}

interface RawAtom {
  element: string;
  x: number;
  y: number;
  z: number;
  /** Sybyl / GAFF type when the file has one. */
  type?: string;
  charge?: number;
}

interface RawBond {
  i: number;
  j: number;
  order: number;
  aromatic: boolean;
}

const AROMATIC_TYPE = new Set(["ca", "cc", "cd", "cp", "na", "nb", "nc", "nd", "sa"]);

const RADII: Record<string, number> = {
  H: 0.31,
  C: 0.76,
  N: 0.71,
  O: 0.66,
  F: 0.57,
  P: 1.07,
  S: 1.05,
  Cl: 1.02,
  Br: 1.14,
  I: 1.33,
};

const elementFromType = (type: string): string => {
  const token = type.toLowerCase();
  if (token.startsWith("br")) return "Br";
  if (token.startsWith("cl")) return "Cl";
  if (token.startsWith("si")) return "Si";
  const letter = token.charAt(0);
  return letter ? letter.toUpperCase() : "X";
};

const titleElement = (raw: string): string => {
  const token = raw.trim();
  if (!token) return "X";
  if (token.length >= 2 && /^(br|cl|si)/i.test(token)) {
    return token.charAt(0).toUpperCase() + token.charAt(1).toLowerCase();
  }
  return token.charAt(0).toUpperCase() + token.slice(1).toLowerCase();
};

export const hillFormula = (counts: ReadonlyMap<string, number>): string => {
  const present = [...counts.keys()].filter((element) => (counts.get(element) ?? 0) > 0);
  const head = ["C", "H"].filter((element) => present.includes(element));
  const tail = present.filter((element) => element !== "C" && element !== "H").sort();
  return [...head, ...tail]
    .map((element) => {
      const count = counts.get(element) ?? 0;
      return count === 1 ? element : `${element}${count}`;
    })
    .join("");
};

const countElements = (atoms: readonly { element: string }[]): Map<string, number> => {
  const counts = new Map<string, number>();
  for (const atom of atoms) counts.set(atom.element, (counts.get(atom.element) ?? 0) + 1);
  return counts;
};

const parsePdb = (text: string): { atoms: RawAtom[]; bonds: RawBond[] } | null => {
  const atoms: RawAtom[] = [];
  const serials: number[] = [];
  const bonds: RawBond[] = [];
  const seenBonds = new Set<string>();
  let sawAtom = false;
  for (const line of text.split(/\r?\n/)) {
    if (line.startsWith("ATOM") || line.startsWith("HETATM")) {
      sawAtom = true;
      const serial = Number.parseInt(line.slice(6, 11), 10);
      const named = line.slice(76, 78).trim() || line.slice(12, 16).trim();
      atoms.push({
        element: titleElement(named),
        x: Number.parseFloat(line.slice(30, 38)),
        y: Number.parseFloat(line.slice(38, 46)),
        z: Number.parseFloat(line.slice(46, 54)),
      });
      serials.push(Number.isFinite(serial) ? serial : atoms.length);
    } else if (line.startsWith("CONECT")) {
      const ids = line
        .slice(6)
        .trim()
        .split(/\s+/)
        .map((part) => Number.parseInt(part, 10))
        .filter((value) => Number.isFinite(value));
      const from = serials.indexOf(ids[0] ?? -1);
      if (from < 0) continue;
      for (const other of ids.slice(1)) {
        const to = serials.indexOf(other);
        if (to < 0 || to === from) continue;
        const left = Math.min(from, to);
        const right = Math.max(from, to);
        const key = `${left}:${right}`;
        if (seenBonds.has(key)) continue;
        seenBonds.add(key);
        bonds.push({ i: left, j: right, order: 1, aromatic: false });
      }
    }
  }
  return sawAtom ? { atoms, bonds } : null;
};

const section = (text: string, name: string): string[] => {
  const lines = text.split(/\r?\n/);
  const start = lines.findIndex((line) => line.trim() === `@<TRIPOS>${name}`);
  if (start < 0) return [];
  const body: string[] = [];
  for (const line of lines.slice(start + 1)) {
    if (line.startsWith("@<TRIPOS>")) break;
    if (line.trim()) body.push(line);
  }
  return body;
};

const parseMol2 = (text: string): { atoms: RawAtom[]; bonds: RawBond[] } | null => {
  if (!text.includes("@<TRIPOS>ATOM")) return null;
  const atoms: RawAtom[] = [];
  for (const line of section(text, "ATOM")) {
    const parts = line.trim().split(/\s+/);
    if (parts.length < 6) continue;
    const type = parts[5] ?? "";
    atoms.push({
      element: elementFromType(type),
      x: Number.parseFloat(parts[2] ?? ""),
      y: Number.parseFloat(parts[3] ?? ""),
      z: Number.parseFloat(parts[4] ?? ""),
      type: type.toLowerCase(),
    });
  }
  const bonds: RawBond[] = [];
  for (const line of section(text, "BOND")) {
    const parts = line.trim().split(/\s+/);
    const i = Number.parseInt(parts[1] ?? "", 10) - 1;
    const j = Number.parseInt(parts[2] ?? "", 10) - 1;
    if (i < 0 || j < 0 || i >= atoms.length || j >= atoms.length || i === j) continue;
    const kind = (parts[3] ?? "1").toLowerCase();
    const numeric = kind === "1" || kind === "2" || kind === "3" ? Number(kind) : 0;
    const aromatic =
      kind === "ar" ||
      (AROMATIC_TYPE.has(atoms[i]?.type ?? "") && AROMATIC_TYPE.has(atoms[j]?.type ?? ""));
    bonds.push({
      i,
      j,
      order: numeric || 1,
      aromatic: aromatic && numeric === 0,
    });
  }
  return atoms.length > 0 ? { atoms, bonds } : null;
};

const parseSdf = (text: string): { atoms: RawAtom[]; bonds: RawBond[] } | null => {
  const lines = text.split(/\r?\n/);
  const counts = lines[3];
  if (!counts || !/V2000/.test(counts)) return null;
  const atomCount = Number.parseInt(counts.slice(0, 3), 10);
  const bondCount = Number.parseInt(counts.slice(3, 6), 10);
  if (!Number.isFinite(atomCount) || atomCount <= 0) return null;
  const atoms: RawAtom[] = [];
  for (let index = 0; index < atomCount; index += 1) {
    const line = lines[4 + index] ?? "";
    const parts = line.trim().split(/\s+/);
    atoms.push({
      element: titleElement(parts[3] ?? "C"),
      x: Number.parseFloat(parts[0] ?? ""),
      y: Number.parseFloat(parts[1] ?? ""),
      z: Number.parseFloat(parts[2] ?? ""),
    });
  }
  const bonds: RawBond[] = [];
  for (let index = 0; index < bondCount; index += 1) {
    const line = lines[4 + atomCount + index] ?? "";
    const parts = line.trim().split(/\s+/);
    const i = Number.parseInt(parts[0] ?? "", 10) - 1;
    const j = Number.parseInt(parts[1] ?? "", 10) - 1;
    const order = Number.parseInt(parts[2] ?? "1", 10);
    if (i < 0 || j < 0 || i >= atoms.length || j >= atoms.length) continue;
    bonds.push({
      i,
      j,
      order: order === 2 || order === 3 ? order : 1,
      aromatic: order === 4,
    });
  }
  return { atoms, bonds };
};

const parseXyz = (text: string): { atoms: RawAtom[]; bonds: RawBond[] } | null => {
  const lines = text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line.length > 0);
  const count = Number.parseInt(lines[0] ?? "", 10);
  if (!Number.isFinite(count) || count <= 0 || lines.length < count + 2) return null;
  const atoms: RawAtom[] = [];
  for (const line of lines.slice(2, 2 + count)) {
    const parts = line.split(/\s+/);
    const element = titleElement(parts[0] ?? "");
    const x = Number.parseFloat(parts[1] ?? "");
    const y = Number.parseFloat(parts[2] ?? "");
    const z = Number.parseFloat(parts[3] ?? "");
    if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(z)) return null;
    atoms.push({ element, x, y, z });
  }
  return atoms.length === count ? { atoms, bonds: [] } : null;
};

const perceiveBonds = (atoms: readonly RawAtom[]): RawBond[] => {
  const bonds: RawBond[] = [];
  for (let i = 0; i < atoms.length; i += 1) {
    for (let j = i + 1; j < atoms.length; j += 1) {
      const left = atoms[i];
      const right = atoms[j];
      if (!left || !right) continue;
      const reach = ((RADII[left.element] ?? 0.77) + (RADII[right.element] ?? 0.77)) * 1.25;
      const distance = Math.hypot(left.x - right.x, left.y - right.y, left.z - right.z);
      if (distance > 0.4 && distance < reach + 0.15) {
        bonds.push({ i, j, order: 1, aromatic: false });
      }
    }
  }
  return bonds;
};

const RING_ELEMENTS = new Set(["C", "N", "O", "S"]);

/** A 5- or 6-ring of short bonds is aromatic even when the file has no bond order. */
const markAromaticRings = (atoms: readonly RawAtom[], bonds: RawBond[]): void => {
  const adjacency = new Map<number, { to: number; bond: number }[]>();
  bonds.forEach((bond, index) => {
    const left = adjacency.get(bond.i) ?? [];
    left.push({ to: bond.j, bond: index });
    adjacency.set(bond.i, left);
    const right = adjacency.get(bond.j) ?? [];
    right.push({ to: bond.i, bond: index });
    adjacency.set(bond.j, right);
  });
  const seen = new Set<string>();
  const rings: number[][] = [];
  const walk = (start: number, atom: number, pathAtoms: number[], pathBonds: number[]): void => {
    if (pathBonds.length >= 6) return;
    for (const edge of adjacency.get(atom) ?? []) {
      if (pathBonds.includes(edge.bond)) continue;
      if (edge.to === start && pathBonds.length >= 4) {
        const ring = [...pathBonds, edge.bond];
        const key = [...ring].sort((left, right) => left - right).join(",");
        if (!seen.has(key)) {
          seen.add(key);
          rings.push(ring);
        }
        continue;
      }
      if (pathAtoms.includes(edge.to)) continue;
      walk(start, edge.to, [...pathAtoms, edge.to], [...pathBonds, edge.bond]);
    }
  };
  for (const start of adjacency.keys()) walk(start, start, [start], []);

  for (const ring of rings) {
    if (ring.length < 5 || ring.length > 6) continue;
    let aromatic = true;
    for (const bondIndex of ring) {
      const bond = bonds[bondIndex];
      const left = bond ? atoms[bond.i] : undefined;
      const right = bond ? atoms[bond.j] : undefined;
      if (!bond || !left || !right) {
        aromatic = false;
        break;
      }
      if (!RING_ELEMENTS.has(left.element) || !RING_ELEMENTS.has(right.element)) {
        aromatic = false;
        break;
      }
      const distance = Math.hypot(left.x - right.x, left.y - right.y, left.z - right.z);
      if (distance < 1.25 || distance > 1.46) {
        aromatic = false;
        break;
      }
    }
    if (!aromatic) continue;
    for (const bondIndex of ring) {
      const bond = bonds[bondIndex];
      if (bond && bond.order === 1) bond.aromatic = true;
    }
  }
};

const kekulize = (bonds: RawBond[]): void => {
  const aromatic = bonds
    .map((bond, index) => (bond.aromatic ? index : -1))
    .filter((index) => index >= 0);
  if (aromatic.length === 0) return;
  const neighbors = new Map<number, number[]>();
  for (const index of aromatic) {
    const bond = bonds[index];
    if (!bond) continue;
    const left = neighbors.get(bond.i) ?? [];
    left.push(index);
    neighbors.set(bond.i, left);
    const right = neighbors.get(bond.j) ?? [];
    right.push(index);
    neighbors.set(bond.j, right);
  }
  const rings: number[][] = [];
  const seen = new Set<string>();
  for (const start of neighbors.keys()) {
    const walk = (atom: number, path: number[], used: Set<number>): void => {
      if (path.length > 7) return;
      for (const bondIndex of neighbors.get(atom) ?? []) {
        if (used.has(bondIndex)) continue;
        const bond = bonds[bondIndex];
        if (!bond) continue;
        const next = bond.i === atom ? bond.j : bond.i;
        if (next === start && path.length >= 4) {
          const key = [...path, bondIndex].sort((a, b) => a - b).join(",");
          if (!seen.has(key)) {
            seen.add(key);
            rings.push([...path, bondIndex]);
          }
          continue;
        }
        if (path.includes(bondIndex)) continue;
        used.add(bondIndex);
        walk(next, [...path, bondIndex], used);
        used.delete(bondIndex);
      }
    };
    walk(start, [], new Set());
  }
  const doubles = new Map<number, number>();
  for (const ring of rings) {
    let wantDouble = true;
    for (const bondIndex of ring) {
      const bond = bonds[bondIndex];
      if (!bond) continue;
      const left = doubles.get(bond.i) ?? 0;
      const right = doubles.get(bond.j) ?? 0;
      if (wantDouble && bond.aromatic && left === 0 && right === 0) {
        bond.order = 2;
        doubles.set(bond.i, left + 1);
        doubles.set(bond.j, right + 1);
        wantDouble = false;
      } else {
        wantDouble = true;
      }
    }
  }
};

const collapseHydrogens = (
  atoms: readonly RawAtom[],
  bonds: readonly RawBond[],
): { atoms: SketchAtom[]; bonds: SketchBond[] } => {
  const degree = new Map<number, number>();
  const partner = new Map<number, number>();
  for (const bond of bonds) {
    degree.set(bond.i, (degree.get(bond.i) ?? 0) + 1);
    degree.set(bond.j, (degree.get(bond.j) ?? 0) + 1);
    partner.set(bond.i, bond.j);
    partner.set(bond.j, bond.i);
  }
  const hidden = new Set<number>();
  const implicit = new Map<number, number>();
  atoms.forEach((atom, index) => {
    if (atom.element !== "H" || (degree.get(index) ?? 0) !== 1) return;
    const heavy = partner.get(index);
    if (heavy === undefined || atoms[heavy]?.element === "H") return;
    hidden.add(index);
    implicit.set(heavy, (implicit.get(heavy) ?? 0) + 1);
  });
  const remap = new Map<number, number>();
  const drawn: SketchAtom[] = [];
  atoms.forEach((atom, index) => {
    if (hidden.has(index)) return;
    remap.set(index, drawn.length);
    const hydrogens = implicit.get(index) ?? 0;
    drawn.push({
      element: atom.element,
      ...(atom.charge ? { charge: atom.charge } : {}),
      ...(hydrogens > 0 ? { hydrogens } : {}),
    });
  });
  const drawnBonds: SketchBond[] = [];
  const seen = new Set<string>();
  for (const bond of bonds) {
    if (hidden.has(bond.i) || hidden.has(bond.j)) continue;
    const i = remap.get(bond.i);
    const j = remap.get(bond.j);
    if (i === undefined || j === undefined) continue;
    const key = i < j ? `${i}:${j}` : `${j}:${i}`;
    if (seen.has(key)) continue;
    seen.add(key);
    drawnBonds.push({ i, j, order: bond.order });
  }
  return { atoms: drawn, bonds: drawnBonds };
};

/** Read a structure file into a formula plus the graph the sketcher draws. */
export const parseStructure = (name: string, text: string): StructureGraph | null => {
  const lower = name.toLowerCase();
  const parsed = lower.endsWith(".mol2")
    ? parseMol2(text)
    : lower.endsWith(".sdf") || lower.endsWith(".mol")
      ? parseSdf(text)
      : lower.endsWith(".xyz") || lower.endsWith(".extxyz") || lower.endsWith(".exyz")
        ? parseXyz(text)
        : lower.endsWith(".pdb") || lower.endsWith(".ent") || lower.endsWith(".brk")
          ? parsePdb(text)
          : null;
  if (!parsed || parsed.atoms.length === 0) return null;
  const bonds = parsed.bonds.length > 0 ? parsed.bonds : perceiveBonds(parsed.atoms);
  markAromaticRings(parsed.atoms, bonds);
  kekulize(bonds);
  const drawn = collapseHydrogens(parsed.atoms, bonds);
  return {
    formula: hillFormula(countElements(parsed.atoms)) || parsed.atoms[0]?.element || "",
    atoms: drawn.atoms,
    bonds: drawn.bonds,
  };
};

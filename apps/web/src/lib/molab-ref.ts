/**
 * Grammar-free `molab:` resolver.
 *
 * The server owns the spelling (`workspace/refs.py`): a run ref plus
 * `/artifact/<id>` or `/execution/<eNN>`. This module only matches those
 * strings against a map of server refs. It does not parse the grammar.
 */

export const MOLAB_REF_SCHEME = "molab:";

export const isMolabRef = (url: string | undefined): url is `molab:${string}` =>
  typeof url === "string" && url.startsWith(MOLAB_REF_SCHEME);

export interface MolabRefTarget {
  kind: "project" | "experiment" | "run";
  label: string;
  path: string;
}

export interface ResolvedMolabRef extends MolabRefTarget {
  ref: string;
  rest: string;
}

/** Longest indexed prefix. A suffix is kept only when that prefix is a run. */
export const resolveMolabRef = (
  href: string,
  index: ReadonlyMap<string, MolabRefTarget>,
): ResolvedMolabRef | null => {
  if (!isMolabRef(href)) return null;
  const exact = index.get(href);
  if (exact) return { ...exact, ref: href, rest: "" };
  let cursor: string = href;
  while (true) {
    const slash = cursor.lastIndexOf("/");
    if (slash < MOLAB_REF_SCHEME.length) return null;
    cursor = cursor.slice(0, slash);
    const hit = index.get(cursor);
    if (!hit) continue;
    if (hit.kind !== "run") return null;
    return { ...hit, ref: cursor, rest: href.slice(cursor.length + 1) };
  }
};

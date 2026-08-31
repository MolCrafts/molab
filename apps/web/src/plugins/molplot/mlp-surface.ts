/**
 * Filename gate for the molplot Metrics tab.
 *
 * Host metrics persist as ``*.mlp.jsonl`` only. Leftover ``*.mlp.zarr``
 * stores (and nested ``zarr.json``) do not activate the tab.
 */

const normalizePath = (relPath: string): string => relPath.toLowerCase().replace(/\\/g, "/");

export const isMlpMetricsSurface = (file: { name: string; relPath: string }): boolean => {
  const path = normalizePath(file.relPath);
  const name = file.name.toLowerCase();
  return name.endsWith(".mlp.jsonl") || path.endsWith(".mlp.jsonl");
};

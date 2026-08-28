/**
 * Filename gate for the molplot Metrics tab.
 *
 * A run may expose one WAL (``*.mlp.jsonl``) and one dense store
 * (``*.mlp.zarr/zarr.json``). Nested arrays inside the Zarr group
 * (``series/<key>/zarr.json``, chunks) are not host surfaces — matching
 * them inflates the tab badge (Metrics (27) for six scalars).
 */

const normalizePath = (relPath: string): string => relPath.toLowerCase().replace(/\\/g, "/");

export const isMlpMetricsSurface = (file: { name: string; relPath: string }): boolean => {
  const path = normalizePath(file.relPath);
  const name = file.name.toLowerCase();
  if (name.endsWith(".mlp.jsonl") || path.endsWith(".mlp.jsonl")) return true;
  if (name.endsWith(".mlp.zarr") || path.endsWith(".mlp.zarr")) return true;
  // Store-root marker only: <stem>.mlp.zarr/zarr.json — not nested arrays.
  if (name === "zarr.json" && path.endsWith(".mlp.zarr/zarr.json")) return true;
  return false;
};

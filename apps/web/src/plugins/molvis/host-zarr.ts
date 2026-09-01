/**
 * Host I/O adapter: workspace.fs as a molvis Zarr directory source.
 *
 * No record-root walking here — molvis resolves the store.
 */

import { getWorkspaceFs, type WorkspaceFs } from "@/lib/workspace-fs";
import { join } from "@/lib/workspace-path";

export interface ZarrDirent {
  name: string;
  kind: "file" | "directory";
}

export interface ZarrDirectorySource {
  list(path: string): Promise<readonly ZarrDirent[]>;
  read(path: string): Promise<Uint8Array>;
}

export const runWorkspaceRelPath = (
  projectId: string,
  experimentId: string,
  runId: string,
): string => `projects/${projectId}/experiments/${experimentId}/runs/run-${runId}`;

export const workspaceZarrSource = (
  runDirRel: string,
  fs: WorkspaceFs = getWorkspaceFs(),
): ZarrDirectorySource => ({
  list: async (path) => {
    const full = path ? join(runDirRel, path) : runDirRel;
    const entries = await fs.listdir(full, { maxDepth: 1 });
    return entries.map((entry) => ({
      name: entry.name,
      kind: entry.kind === "file" ? "file" : "directory",
    }));
  },
  read: async (path) => {
    const blob = await fs.readBlob(join(runDirRel, path));
    return new Uint8Array(await blob.arrayBuffer());
  },
});

/** Restrict a source to one store directory; paths handed to molvis are store-relative. */
export const scopedZarrSource = (
  source: ZarrDirectorySource,
  storeRoot: string,
): ZarrDirectorySource => ({
  list: (path) => source.list(path ? join(storeRoot, path) : storeRoot),
  read: (path) => source.read(join(storeRoot, path)),
});

const bytesToBase64 = (bytes: Uint8Array): string => {
  const chunk = 0x8000;
  let binary = "";
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return btoa(binary);
};

/** Fallback when molvis has not yet exported ``loadZarrSource``. */
export const collectZarrStore = async (
  source: ZarrDirectorySource,
): Promise<Record<string, string>> => {
  const files: Record<string, string> = {};
  const visit = async (rel: string): Promise<void> => {
    const entries = await source.list(rel);
    for (const entry of entries) {
      const path = rel ? `${rel}/${entry.name}` : entry.name;
      if (entry.kind === "directory") {
        await visit(path);
        continue;
      }
      files[path] = bytesToBase64(await source.read(path));
    }
  };
  await visit("");
  if (Object.keys(files).length === 0) {
    throw new Error("Zarr store is empty");
  }
  return files;
};

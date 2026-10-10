import { workspaceApi } from "@/api/workspace";
import type { TexInputFile } from "./compile-request";
import { manuscriptFiles } from "./siblings";

/** Read the figures, tables, and bibliography a manuscript names. Missing files are skipped. */
export const loadManuscriptFiles = async (
  source: string,
  texPath: string,
): Promise<TexInputFile[]> => {
  if (!texPath) return [];
  const loaded: TexInputFile[] = [];
  const seen = new Set<string>();
  for (const file of manuscriptFiles(source, texPath)) {
    if (seen.has(file.enginePath)) continue;
    try {
      const content = file.binary
        ? new Uint8Array(
            await (await workspaceApi.getWorkspaceFileBlob(file.workspacePath)).arrayBuffer(),
          )
        : await workspaceApi.getWorkspaceFileText(file.workspacePath);
      if (file.binary && content instanceof Uint8Array && content.byteLength === 0) continue;
      seen.add(file.enginePath);
      loaded.push({ path: file.enginePath, content });
    } catch {
      // A .png candidate can miss when the figure is a .pdf.
    }
  }
  return loaded;
};

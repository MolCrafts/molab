import type { ZarrDirectorySource } from "./host-zarr";

type LoadFileContent = typeof import("@molcrafts/molvis-stage/io")["loadFileContent"];
type MolvisApp = Parameters<LoadFileContent>[0];

type MolvisIo = {
  loadFileContent: LoadFileContent;
  loadZarrSource?: (app: MolvisApp, source: ZarrDirectorySource, filename: string) => Promise<void>;
};

export const loadMolvisCore = async (): Promise<{
  mountMolvis: typeof import("@molcrafts/molvis-stage")["mountMolvis"];
  loadFileContent: LoadFileContent;
  loadZarrSource: MolvisIo["loadZarrSource"];
}> => {
  const [{ mountMolvis }, ioModule] = await Promise.all([
    import("@molcrafts/molvis-stage"),
    import("@molcrafts/molvis-stage/io"),
  ]);
  const io = ioModule as unknown as MolvisIo;
  return {
    mountMolvis,
    loadFileContent: io.loadFileContent,
    loadZarrSource: io.loadZarrSource,
  };
};

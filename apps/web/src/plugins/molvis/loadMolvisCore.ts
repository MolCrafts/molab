import type { ZarrDirectorySource } from "./host-zarr";

type LoadFileContent = typeof import("@molcrafts/molvis-stage/io")["loadFileContent"];
type MolvisApp = Parameters<LoadFileContent>[0];

type DirectoryLoader = (
  app: MolvisApp,
  source: ZarrDirectorySource,
  filename: string,
) => Promise<void>;

type MolvisIo = {
  loadFileContent: LoadFileContent;
  /** Current name. molvis 0.4 renamed the directory ingress. */
  loadMrecSource?: DirectoryLoader;
  /** Previous name, kept so an older stage build still opens a store. */
  loadZarrSource?: DirectoryLoader;
};

export const directoryLoader = (
  io: Pick<MolvisIo, "loadMrecSource" | "loadZarrSource">,
): DirectoryLoader | undefined => io.loadMrecSource ?? io.loadZarrSource;

export const loadMolvisCore = async (): Promise<{
  mountMolvis: typeof import("@molcrafts/molvis-stage")["mountMolvis"];
  loadFileContent: LoadFileContent;
  loadDirectory: DirectoryLoader | undefined;
}> => {
  const [{ mountMolvis }, ioModule] = await Promise.all([
    import("@molcrafts/molvis-stage"),
    import("@molcrafts/molvis-stage/io"),
  ]);
  const io = ioModule as unknown as MolvisIo;
  return {
    mountMolvis,
    loadFileContent: io.loadFileContent,
    loadDirectory: directoryLoader(io),
  };
};

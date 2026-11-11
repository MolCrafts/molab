import type { ZarrDirectorySource } from "./host-zarr";

type Stage = typeof import("@molcrafts/molvis-stage");
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

export interface MolvisCore {
  mountMolvis: Stage["mountMolvis"];
  loadFileContent: LoadFileContent;
  loadDirectory: DirectoryLoader | undefined;
  /** The stage's representation presets — the only models a view offers. */
  representations: Stage["REPRESENTATIONS"];
  findRepresentation: Stage["findRepresentation"];
  ColorByPropertyModifier: Stage["ColorByPropertyModifier"];
}

export const loadMolvisCore = async (): Promise<MolvisCore> => {
  const [stage, ioModule] = await Promise.all([
    import("@molcrafts/molvis-stage"),
    import("@molcrafts/molvis-stage/io"),
  ]);
  const io = ioModule as unknown as MolvisIo;
  return {
    mountMolvis: stage.mountMolvis,
    loadFileContent: io.loadFileContent,
    loadDirectory: directoryLoader(io),
    representations: stage.REPRESENTATIONS,
    findRepresentation: stage.findRepresentation,
    ColorByPropertyModifier: stage.ColorByPropertyModifier,
  };
};

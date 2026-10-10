/**
 * The app's single import face for `@molcrafts/molrs` (the molrs WASM build).
 *
 * Two reasons it exists rather than each plugin importing the package:
 *
 * 1. **One WASM instance.** The module is stateful and multi-megabyte; two
 *    import paths mean two instances in the bundle.
 * 2. **No plugin depends on another.** molvis reaches molrs for structures,
 *    molplot reaches it for solver logs. Routing either through the other's
 *    package would make a chart product depend on a 3D viewer.
 *
 * Everything is feature-detected. The installed binding may predate a given
 * export, and a missing one must degrade to "this format is unavailable"
 * rather than crashing the app at import time — so callers ask
 * {@link molrsCapabilities} before offering a format.
 */

export interface ThermoTable {
  /** Position of the `run` block in the log. A restart appends rather than
   * resets, so this separates one continuation from the next. */
  runIndex: number;
  /** Column names exactly as the solver printed them (`Step`, `Temp`, …). */
  columns: string[];
  /** Row-major values, one inner array per thermo row. */
  rows: number[][];
}

interface MolrsModule {
  readLammpsLogThermo?: (text: string) => ThermoTable[];
  isLammpsLog?: (text: string) => boolean;
}

let loading: Promise<MolrsModule | null> | null = null;

/**
 * Load the WASM binding once. Resolves to `null` when it is unavailable, so a
 * browser without it still renders everything that does not need it.
 */
export const loadMolrs = (): Promise<MolrsModule | null> => {
  if (!loading) {
    loading = import("@molcrafts/molrs")
      .then((module) => module as unknown as MolrsModule)
      .catch(() => null);
  }
  return loading;
};

/** Which molrs-backed formats this build can actually read. */
export interface MolrsCapabilities {
  lammpsLog: boolean;
}

/**
 * What the loaded binding supports.
 *
 * An export added to molrs after the installed package was built simply
 * reports `false` here; the format is then not offered, instead of being
 * offered and failing when a user clicks it.
 */
export const molrsCapabilities = async (): Promise<MolrsCapabilities> => {
  const molrs = await loadMolrs();
  return { lammpsLog: typeof molrs?.readLammpsLogThermo === "function" };
};

/**
 * Parse a LAMMPS log's thermo tables in the browser.
 *
 * @throws When the installed binding has no LAMMPS log reader — check
 *   {@link molrsCapabilities} before offering the format.
 */
export const readLammpsLogThermo = async (text: string): Promise<ThermoTable[]> => {
  const molrs = await loadMolrs();
  if (typeof molrs?.readLammpsLogThermo !== "function") {
    throw new Error(
      "This @molcrafts/molrs build has no LAMMPS log reader; upgrade the WASM package.",
    );
  }
  return molrs.readLammpsLogThermo(text);
};

/** Cheap content check for a LAMMPS log, when the binding offers one. */
export const isLammpsLog = async (text: string): Promise<boolean> => {
  const molrs = await loadMolrs();
  if (typeof molrs?.isLammpsLog === "function") {
    return molrs.isLammpsLog(text);
  }
  // The thermo marker is what makes a log plottable — a run that died during
  // setup prints the banner and nothing to draw.
  return text.includes("Per MPI rank memory allocation");
};

/** Forget the cached module so a test can load a stub (tests only). */
export const resetMolrsForTests = (): void => {
  loading = null;
};

/**
 * The app's single import face for `@molcrafts/molwasm`.
 *
 * Two reasons it exists rather than each plugin importing the package:
 *
 * 1. **One WASM instance.** The module is stateful and multi-megabyte; two
 *    import paths mean two instances in the bundle.
 * 2. **No plugin depends on another.** molvis reaches the binding for
 *    structures, molplot reaches it for solver logs. Routing either through
 *    the other's package would make a chart product depend on a 3D viewer.
 *
 * Everything is feature-detected. A missing export degrades to "this format
 * is unavailable" rather than crashing the app at import time — callers ask
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

interface LammpsThermo {
  columns: string[];
  rows: number[][];
}

interface LammpsRun {
  index: number;
  thermo?: LammpsThermo;
}

interface LammpsLog {
  runs?: LammpsRun[];
}

interface MolwasmModule {
  readLammpsLog?: (text: string) => LammpsLog;
  isLammpsLog?: (text: string) => boolean;
}

let loading: Promise<MolwasmModule | null> | null = null;

/**
 * Load the WASM binding once. Resolves to `null` when it is unavailable, so a
 * browser without it still renders everything that does not need it.
 */
export const loadMolrs = (): Promise<MolwasmModule | null> => {
  if (!loading) {
    loading = import("@molcrafts/molwasm")
      .then((module) => module as unknown as MolwasmModule)
      .catch(() => null);
  }
  return loading;
};

/** Which WASM-backed formats this build can actually read. */
export interface MolrsCapabilities {
  lammpsLog: boolean;
}

/**
 * What the loaded binding supports.
 *
 * An export added after the installed package was built reports `false`
 * here; the format is then not offered.
 */
export const molrsCapabilities = async (): Promise<MolrsCapabilities> => {
  const wasm = await loadMolrs();
  return { lammpsLog: typeof wasm?.readLammpsLog === "function" };
};

/**
 * Parse a LAMMPS log's thermo tables in the browser.
 *
 * `readLammpsLog` returns one record per run. Tables are the runs that
 * printed thermo, keyed by that run's index.
 *
 * @throws When the installed binding has no LAMMPS log reader — check
 *   {@link molrsCapabilities} before offering the format.
 */
export const readLammpsLogThermo = async (text: string): Promise<ThermoTable[]> => {
  const wasm = await loadMolrs();
  if (typeof wasm?.readLammpsLog !== "function") {
    throw new Error(
      "This @molcrafts/molwasm build has no LAMMPS log reader; upgrade the WASM package.",
    );
  }
  const log = wasm.readLammpsLog(text);
  return (log.runs ?? []).flatMap((run) =>
    run.thermo ? [{ runIndex: run.index, columns: run.thermo.columns, rows: run.thermo.rows }] : [],
  );
};

/** Cheap content check for a LAMMPS log, when the binding offers one. */
export const isLammpsLog = async (text: string): Promise<boolean> => {
  const wasm = await loadMolrs();
  if (typeof wasm?.isLammpsLog === "function") {
    return wasm.isLammpsLog(text);
  }
  // The thermo marker is what makes a log plottable — a run that died during
  // setup prints the banner and nothing to draw.
  return text.includes("Per MPI rank memory allocation");
};

/** Forget the cached module so a test can load a stub (tests only). */
export const resetMolrsForTests = (): void => {
  loading = null;
};

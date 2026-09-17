import type { MolabPluginModule, PluginAPI } from "@molcrafts/molab-plugin";
import { registerMetricReaderContribution } from "@/lib/contribution-runtime";
import type {
  MetricReaderContribution,
  MetricReadRequest,
  MetricRecordSample,
  MetricSourceInput,
} from "@/lib/contribution-types";
import { molrsCapabilities, readLammpsLogThermo, type ThermoTable } from "@/lib/molrs";
import { thermoRecords, walRecords } from "./formats";

/**
 * The formats molrs owns, contributed to whoever is drawing.
 *
 * molplot registers nothing and parses nothing — it displays. molrs owns the
 * solver formats and reads them **in the browser via WASM**, so a chart comes
 * straight from `log.lammps` with no server-side conversion and no
 * intermediate file. Any other package contributes a format the same way, and
 * molplot treats it identically — molab's own WAL included.
 *
 * The LAMMPS reader is registered only when the installed WASM build actually
 * exports it: offering a format that then fails on click is worse than not
 * offering it at all.
 */

/**
 * Parsed tables, kept so a stride change re-slices instead of re-parsing.
 *
 * A 3 MB log costs ~800 ms to parse but nothing to slice, and a chart re-reads
 * on every zoom. Keyed by path plus revision so a live file that grew is
 * re-parsed while a finished one is not.
 */
const parsed = new Map<string, ThermoTable[]>();

const cacheKey = (source: MetricSourceInput): string =>
  `${source.path}@${source.revision ?? source.text.length}`;

const readLammpsLog = async (
  source: MetricSourceInput,
  request: MetricReadRequest,
): Promise<MetricRecordSample[]> => {
  const key = cacheKey(source);
  let tables = parsed.get(key);
  if (!tables) {
    tables = await readLammpsLogThermo(source.text);
    // One log at a time: these tables are megabytes, and a viewer looks at
    // one attempt at a time.
    parsed.clear();
    parsed.set(key, tables);
  }
  return thermoRecords(tables, request, source.path);
};

/**
 * molab's own WAL: plain JSONL, no WASM needed, and no privilege for being
 * molab's — contributed like any other format.
 */
export const MLP_JSONL_READER: MetricReaderContribution = {
  id: "molrs:mlp-jsonl",
  pluginId: "molrs",
  format: "mlp_jsonl",
  label: "Molab metrics",
  patterns: ["**/*.mlp.jsonl"],
  tailable: true,
  claims: (text) => text.trimStart().startsWith("{"),
  read: async (source, request) => walRecords(source.text, request, source.path),
};

export const LAMMPS_LOG_READER: MetricReaderContribution = {
  id: "molrs:lammps-log",
  // Stamped explicitly: this one registers after `activate` has returned, so
  // there is no active-plugin window left to inherit from.
  pluginId: "molrs",
  format: "lammps_log",
  label: "LAMMPS log",
  // Narrow on purpose: `*.out` / `*.txt` would light up an empty chart on
  // every unrelated file. The content check has the final say.
  patterns: ["**/log.lammps", "**/*.lammps", "**/lammps*.log", "**/lammps*.out"],
  priority: 10,
  claims: (text) => text.includes("Per MPI rank memory allocation"),
  read: readLammpsLog,
};

const molrsPlugin: MolabPluginModule = {
  id: "molrs",
  name: "MolRS formats",
  version: "1.0.0",
  description: "Reads solver logs and metric files in the browser via WASM.",
  activate: (_api: PluginAPI) => {
    registerMetricReaderContribution(MLP_JSONL_READER);

    void molrsCapabilities().then((capabilities) => {
      if (!capabilities.lammpsLog) {
        return;
      }
      registerMetricReaderContribution(LAMMPS_LOG_READER);
    });
  },
};

export default molrsPlugin;

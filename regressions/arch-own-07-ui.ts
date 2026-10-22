/**
 * Hard-coded goldens for the run-mode, host-picker and molab-ref UI (arch-own-07-ui).
 *
 * No browser, no network, no third-party runtime.
 */

import {
  bypassCacheFor,
  executionModeOptions,
} from "../apps/web/src/app/runs/runLifecycle";
import { resolveMolabRef, type MolabRefTarget } from "../apps/web/src/lib/molab-ref";
import { listHostOptions } from "../apps/web/src/plugins/knowledge/knowledgeDocTree";
import { workflowEditPolicy } from "../apps/web/src/plugins/workflow/workflowEditPolicy";

const assert = (condition: boolean, message: string): void => {
  if (!condition) throw new Error(message);
};

const enabled = (attempts: number, basedOnStatus: string | null): boolean[] =>
  executionModeOptions({ attempts, basedOnStatus }).map((option) => option.enabled);

assert(
  JSON.stringify(enabled(0, null)) === JSON.stringify([true, false, false, false]),
  "{0,null} mode vector",
);
assert(
  JSON.stringify(enabled(1, "failed")) === JSON.stringify([false, true, true, false]),
  "{1,failed} mode vector",
);
assert(
  JSON.stringify(enabled(2, "succeeded")) === JSON.stringify([false, true, false, true]),
  "{2,succeeded} mode vector",
);
assert(
  JSON.stringify(enabled(5, "queued")) === JSON.stringify([false, false, false, false]),
  "{5,queued} mode vector",
);
assert(bypassCacheFor("reproduce", false) === true, "reproduce bypasses cache");

const hosts = listHostOptions(
  {
    projects: [{ path: "projects/peo", name: "PEO" }],
    experiments: [{ path: "projects/peo/experiments/tg", name: "Tg" }],
    runs: [{ path: "projects/peo/experiments/tg/runs/n=8", name: "n=8" }],
  },
  "projects/peo",
);
assert(hosts.length === 4, "four host options");
assert(hosts[0]?.hostPath === "" && hosts[0].kind === "workspace" && hosts[0].disabled === false, "root first");
assert(hosts[1]?.hostPath === "projects/peo" && hosts[1].disabled === true, "current host disabled");
assert(hosts[2]?.kind === "experiment" && hosts[3]?.kind === "run", "experiment then run");

const index = new Map<string, MolabRefTarget>([
  [
    "molab:experiment/E1/run/R1",
    { kind: "run", label: "n=8", path: "/projects/P1/experiments/E1/runs/R1" },
  ],
]);
const execution = resolveMolabRef("molab:experiment/E1/run/R1/execution/e02", index);
assert(execution?.rest === "execution/e02", "execution suffix");
assert(resolveMolabRef("molab:experiment/E1/run/R9", index) === null, "unknown run");
assert(workflowEditPolicy("code").mode === "convert", "code workflow converts");

console.log("arch-own-07-ui: ok");

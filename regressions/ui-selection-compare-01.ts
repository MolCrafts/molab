/**
 * Hard-coded goldens for the comparison bag (ui-selection-compare-01).
 *
 * No browser, no network, no third-party runtime.
 */

import { mergeIntoBag, parseStoredEntries } from "../apps/web/src/app/compare/useCompareSet";
import { itemKey } from "../apps/web/src/app/compare/types";
import type { CompareItem } from "../apps/web/src/app/compare/types";

const project: CompareItem = {
  ref: { kind: "project", workspaceKey: "lab-v3", projectId: "peo-tg" },
  executionId: null,
  workspaceLabel: "lab-v3",
  projectName: "peo-tg",
  experimentName: "",
  runName: "",
  parameters: {},
  category: null,
  addedAt: "2026-09-06T00:00:00.000Z",
};

const n8: CompareItem = {
  ref: {
    kind: "run",
    workspaceKey: "lab-v3",
    projectId: "peo-tg",
    experimentId: "n-series",
    runId: "n=8",
  },
  executionId: null,
  workspaceLabel: "lab-v3",
  projectName: "peo-tg",
  experimentName: "n-series",
  runName: "n=8",
  parameters: {},
  category: null,
  addedAt: "2026-09-06T00:00:00.000Z",
};

const n12: CompareItem = {
  ...n8,
  ref: { ...n8.ref, kind: "run", runId: "n=12" },
  runName: "n=12",
};

const assert = (condition: boolean, message: string): void => {
  if (!condition) throw new Error(message);
};

assert(
  itemKey({ kind: "project", workspaceKey: "lab-v3", projectId: "peo-tg" }) === "lab-v3/peo-tg",
  "itemKey for project peo-tg",
);

const merged = mergeIntoBag([project], [n8], {
  isSubtreeLoaded: () => true,
  siblingRuns: () => [n12],
});
assert(merged.length === 2, `expected 2 items, got ${merged.length}`);
assert(merged[0]?.ref.kind === "run" && merged[0].ref.runId === "n=12", "first sibling n=12");
assert(merged[1]?.ref.kind === "run" && merged[1].ref.runId === "n=8", "then n=8");

const parsed = parseStoredEntries(
  JSON.stringify([
    {
      ref: { workspaceKey: "lab-v3", projectId: "p", experimentId: "e", runId: "r" },
      selected: false,
    },
  ]),
);
assert(parsed.length === 1, "migrated one run");
assert(parsed[0]?.ref.kind === "run", "kind run");
assert(parsed[0]?.category === null, "category null");

console.log("ui-selection-compare-01: ok");

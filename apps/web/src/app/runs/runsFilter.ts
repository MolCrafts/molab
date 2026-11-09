// ─────────────────────────────────────────────────────────────────────────────
// The experiment Runs filter (L03): `status:failed,interrupted driver:ase
// timestep_fs>1 nve`. `status:` matches a run's latest status or its chart
// group (finalizing is running); `key:a,b` matches a parameter value; `key>n`,
// `key<n`, `key>=n`, `key<=n` compare numbers; any other word matches the title
// or the id. Every term must hold.
// ─────────────────────────────────────────────────────────────────────────────

import { chartGroupOf, normalizeStatus } from "@/app/status/vocabulary";

export type FilterTerm =
  | { kind: "status"; values: string[] }
  | { kind: "equals"; key: string; values: string[] }
  | { kind: "compare"; key: string; op: ">" | "<" | ">=" | "<="; value: number }
  | { kind: "text"; value: string };

export interface FilterableRun {
  id: string;
  title: string;
  status: string;
  parameters: Record<string, unknown>;
}

const COMPARE = /^([\w.-]+)(>=|<=|>|<)(-?\d+(?:\.\d+)?(?:e-?\d+)?)$/i;
const EQUALS = /^([\w.-]+):(.+)$/;

export const parseFilter = (text: string): FilterTerm[] =>
  text
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .map((token): FilterTerm => {
      const compare = COMPARE.exec(token);
      if (compare) {
        return {
          kind: "compare",
          key: compare[1] as string,
          op: compare[2] as ">" | "<" | ">=" | "<=",
          value: Number(compare[3]),
        };
      }
      const equals = EQUALS.exec(token);
      if (equals) {
        const values = (equals[2] as string).split(",").filter(Boolean);
        return equals[1] === "status"
          ? { kind: "status", values }
          : { kind: "equals", key: equals[1] as string, values };
      }
      return { kind: "text", value: token.toLowerCase() };
    });

const matches = (run: FilterableRun, term: FilterTerm): boolean => {
  switch (term.kind) {
    case "status": {
      const key = normalizeStatus(run.status);
      const group = chartGroupOf(key);
      return term.values.some((value) => {
        const wanted = normalizeStatus(value);
        return (
          wanted === key ||
          (group !== null &&
            chartGroupOf(wanted) === group &&
            wanted !== "pending" &&
            key !== "pending")
        );
      });
    }
    case "equals": {
      if (!(term.key in run.parameters)) return false;
      const value = String(run.parameters[term.key]);
      return term.values.includes(value);
    }
    case "compare": {
      const value = run.parameters[term.key];
      if (typeof value !== "number") return false;
      if (term.op === ">") return value > term.value;
      if (term.op === "<") return value < term.value;
      if (term.op === ">=") return value >= term.value;
      return value <= term.value;
    }
    case "text":
      return (
        run.title.toLowerCase().includes(term.value) || run.id.toLowerCase().includes(term.value)
      );
  }
};

export const filterRuns = <T extends FilterableRun>(runs: readonly T[], text: string): T[] => {
  const terms = parseFilter(text);
  return terms.length === 0
    ? [...runs]
    : runs.filter((run) => terms.every((term) => matches(run, term)));
};

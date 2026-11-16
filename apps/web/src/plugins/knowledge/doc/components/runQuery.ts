/**
 * Pure helpers behind `<molab-run-table>` and `<molab-metric-chart>`: the
 * `where` conjunction, the `columns` list, and how one cell is printed.
 */

export type WhereOp = "=" | "!=" | "<" | "<=" | ">" | ">=";

export interface WhereCondition {
  key: string;
  op: WhereOp;
  /** The value as written (unquoted). */
  value: string;
}

export interface ParsedWhere {
  conditions: WhereCondition[];
  /** Clauses that are not `key(op)value`, as written. */
  invalid: string[];
}

const CLAUSE = /^([A-Za-z_][\w.-]*)\s*(<=|>=|!=|==|=|<|>)\s*(.+)$/;
const SEPARATOR = /\s*(?:&&|&|,|\band\b)\s*/i;

const unquote = (text: string): string => text.replace(/^(["'])(.*)\1$/, "$2");

/** `a>=0.5 && b=nve` (also `,` / `&` / `and`) → conditions; anything else is `invalid`. */
export const parseWhere = (text: string | undefined): ParsedWhere => {
  const clauses = (text ?? "")
    .split(SEPARATOR)
    .map((clause) => clause.trim())
    .filter(Boolean);
  const read = clauses.map((clause) => ({ clause, condition: parseClause(clause) }));
  return {
    conditions: read.flatMap(({ condition }) => (condition ? [condition] : [])),
    invalid: read.flatMap(({ clause, condition }) => (condition ? [] : [clause])),
  };
};

const parseClause = (clause: string): WhereCondition | null => {
  const match = CLAUSE.exec(clause);
  if (!match) return null;
  const [, key = "", rawOp = "=", value = ""] = match;
  const op = (rawOp === "==" ? "=" : rawOp) as WhereOp;
  return { key, op, value: unquote(value.trim()) };
};

const asNumber = (value: unknown): number | null => {
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
};

const compare = (actual: unknown, op: WhereOp, expected: string): boolean => {
  if (actual === undefined) return false;
  const left = asNumber(actual);
  const right = asNumber(expected);
  if (left !== null && right !== null) {
    if (op === "=") return left === right;
    if (op === "!=") return left !== right;
    if (op === "<") return left < right;
    if (op === "<=") return left <= right;
    if (op === ">") return left > right;
    return left >= right;
  }
  const text = typeof actual === "string" ? actual : JSON.stringify(actual);
  if (op === "=") return text === expected;
  if (op === "!=") return text !== expected;
  // Ordering a word against a word is not a question this filter answers.
  return false;
};

/** Every condition holds for *lookup* (a parameter, else a result). */
export const matchesWhere = (
  conditions: readonly WhereCondition[],
  lookup: (key: string) => unknown,
): boolean => conditions.every(({ key, op, value }) => compare(lookup(key), op, value));

const OP_SIGN: Record<WhereOp, string> = {
  "=": "=",
  "!=": "≠",
  "<": "<",
  "<=": "≤",
  ">": ">",
  ">=": "≥",
};

/** `timestep_fs ≥ 0.5 · driver = ase` — the footer's echo of the filter. */
export const formatWhere = (conditions: readonly WhereCondition[]): string =>
  conditions.map(({ key, op, value }) => `${key} ${OP_SIGN[op]} ${value}`).join(" · ");

/** `a, b ,c` → `["a", "b", "c"]`. */
export const parseColumns = (text: string | undefined): string[] =>
  (text ?? "")
    .split(",")
    .map((column) => column.trim())
    .filter(Boolean);

/** A positive integer `limit`, else null (no limit). */
export const parseLimit = (text: string | undefined): number | null => {
  const value = Number(text);
  return Number.isInteger(value) && value > 0 ? value : null;
};

export interface Cell {
  text: string;
  numeric: boolean;
}

/** A number as a table prints it: 2 · 0.5 · 3.75e-5 · 1.50e+6. */
export const formatNumber = (value: number): string => {
  if (Number.isInteger(value) && Math.abs(value) < 1e6) return String(value);
  const abs = Math.abs(value);
  return abs !== 0 && (abs < 1e-3 || abs >= 1e6)
    ? value.toExponential(2)
    : String(Number(value.toPrecision(4)));
};

/** One cell: numbers right-aligned, a missing value as "—". */
export const formatCell = (value: unknown): Cell => {
  if (typeof value === "number" && Number.isFinite(value)) {
    return { text: formatNumber(value), numeric: true };
  }
  if (value === null || value === undefined || value === "" || typeof value === "number") {
    return { text: "—", numeric: false };
  }
  if (typeof value === "string") return { text: value, numeric: false };
  if (typeof value === "boolean") return { text: String(value), numeric: false };
  try {
    return { text: JSON.stringify(value), numeric: false };
  } catch {
    return { text: String(value), numeric: false };
  }
};

/** A run's value for *key*: its parameter, else its scalar result. */
export const runValue = (
  parameters: Readonly<Record<string, unknown>>,
  results: Readonly<Record<string, unknown>> | null | undefined,
  key: string,
): unknown => (key in parameters ? parameters[key] : results?.[key]);

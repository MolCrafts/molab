/** One axis of a parameter grid, as the sweep editor holds it. */

export const SWEEP_CELL_LIMIT = 500;

export interface AxisDraft {
  id: string;
  name: string;
  valuesText: string;
}

export interface SweepGrid {
  axes: Record<string, Array<string | number>>;
  cells: number;
}

export const axisDraft = (id: string, name = "", valuesText = ""): AxisDraft => ({
  id,
  name,
  valuesText,
});

/** Axes already stored as lists on the experiment. A scalar is not an axis. */
export const draftsFromParameterSpace = (
  space: Record<string, unknown> | undefined,
): AxisDraft[] => {
  const drafts: AxisDraft[] = [];
  for (const [name, value] of Object.entries(space ?? {})) {
    if (!Array.isArray(value) || value.length === 0) continue;
    drafts.push(axisDraft(`axis-${drafts.length}`, name, value.map(String).join(", ")));
  }
  return drafts.length > 0 ? drafts : [axisDraft("axis-0")];
};

/** Split a values field. A finite number stays a number; anything else stays text. */
export const parseAxisValues = (text: string): Array<string | number> =>
  text
    .split(/[,\s]+/)
    .map((token) => token.trim())
    .filter(Boolean)
    .map((token) => {
      const numeric = Number(token);
      return Number.isFinite(numeric) ? numeric : token;
    });

const product = (lengths: readonly number[]): number =>
  lengths.reduce((count, length) => count * length, 1);

/** The grid the server will seed, or the reason the draft cannot be sent. */
export const compileSweep = (
  drafts: readonly AxisDraft[],
): { grid: SweepGrid } | { error: string } => {
  if (drafts.length === 0) return { error: "Add an axis." };
  const axes: Record<string, Array<string | number>> = {};
  const lengths: number[] = [];
  for (const draft of drafts) {
    const name = draft.name.trim();
    if (!name) return { error: "Every axis needs a name." };
    if (Object.hasOwn(axes, name)) return { error: `Axis “${name}” is listed twice.` };
    const values = parseAxisValues(draft.valuesText);
    if (values.length === 0) return { error: `Axis “${name}” needs a value.` };
    axes[name] = values;
    lengths.push(values.length);
  }
  const cells = product(lengths);
  if (cells === 0) return { error: "Sweep has no cells." };
  if (cells > SWEEP_CELL_LIMIT) {
    return { error: `Sweep has ${cells} cells. The limit is ${SWEEP_CELL_LIMIT}.` };
  }
  return { grid: { axes, cells } };
};

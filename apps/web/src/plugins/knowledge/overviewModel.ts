/**
 * The Knowledge landing (L10-1), as data: documents edited per day and the
 * documents newest first. Pure; the view only draws it.
 */

export interface WritingDay {
  /** Local calendar day, `YYYY-MM-DD`. */
  day: string;
  /** Documents last edited that day. */
  edits: number;
}

const dayKey = (ms: number): string => {
  const date = new Date(ms);
  const pad = (value: number): string => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
};

/** Documents last edited on each of the *days* days up to *now*, oldest first. */
export const writingDays = (
  notes: readonly { updatedAt?: string | null }[],
  now: number,
  days = 14,
): WritingDay[] => {
  const counts = new Map<string, number>();
  for (const note of notes) {
    const at = note.updatedAt ? Date.parse(note.updatedAt) : Number.NaN;
    if (Number.isFinite(at)) counts.set(dayKey(at), (counts.get(dayKey(at)) ?? 0) + 1);
  }
  return Array.from({ length: days }, (_, index) => {
    const day = dayKey(now - (days - 1 - index) * 86_400_000);
    return { day, edits: counts.get(day) ?? 0 };
  });
};

/** Newest edit first; documents without a time keep their order at the end. */
export const byRecent = <T extends { updatedAt?: string | null; name: string }>(
  notes: readonly T[],
): T[] =>
  [...notes].sort((a, b) => {
    const at = (note: T): number => (note.updatedAt ? Date.parse(note.updatedAt) : -1);
    return at(b) - at(a) || a.name.localeCompare(b.name);
  });

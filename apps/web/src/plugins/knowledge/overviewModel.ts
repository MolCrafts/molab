/**
 * The Knowledge landing (L10-1), as data: what is open (blocked todos,
 * delegations waiting on a person, open milestones), the milestone and todo
 * counts the instruments draw, and documents per class. Pure; the view only
 * draws it.
 */

import type { NoteSummary } from "@/api/generated/models/NoteSummary";
import { emptyCounts, type StatusCounts } from "@/app/status/vocabulary";
import { KNOWLEDGE_CLASSES, type KnowledgeClass, knowledgeClassOf } from "./knowledgeClass";
import { planningView } from "./planningModel";

/** Classes whose record the landing reads. */
export const RECORD_CLASSES: ReadonlySet<KnowledgeClass> = new Set([
  "Todo",
  "Milestone",
  "Delegation",
]);

export interface OpenWorkRow {
  key: string;
  /** StatusIcon status: interrupted = blocked, pending = open. */
  status: "interrupted" | "pending";
  title: string;
  context: string;
  relPath: string;
}

export interface TodoTally {
  done: number;
  open: number;
  blocked: number;
}

export interface KnowledgeOverview {
  verdict: { status: string; subject: string; evidence: string | null };
  milestones: StatusCounts;
  milestoneMet: number;
  milestoneTotal: number;
  todos: TodoTally;
  openWork: OpenWorkRow[];
  byClass: { cls: KnowledgeClass; count: number }[];
}

const plural = (count: number, one: string, many: string): string =>
  `${count} ${count === 1 ? one : many}`;

const asRecord = (value: unknown): Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};

const delegationAsk = (record: Record<string, unknown>): string => {
  const questions = Array.isArray(record.questions) ? record.questions : [];
  const last = questions[questions.length - 1];
  if (typeof last === "string" && last) return last;
  return typeof record.goal === "string" && record.goal ? record.goal : "Waiting for a person";
};

interface Collected {
  todos: TodoTally;
  milestones: StatusCounts;
  met: number;
  total: number;
  rows: OpenWorkRow[];
}

const collect = (
  notes: readonly NoteSummary[],
  records: ReadonlyMap<string, unknown>,
): Collected => {
  const out: Collected = {
    todos: { done: 0, open: 0, blocked: 0 },
    milestones: emptyCounts(),
    met: 0,
    total: 0,
    rows: [],
  };
  for (const note of notes) {
    const cls = knowledgeClassOf(note);
    const record = records.get(note.relPath);
    if (record === undefined) continue;
    const view = planningView(cls, record);
    if (view?.kind === "todo") {
      for (const item of view.items) {
        if (item.status === "done") out.todos.done += 1;
        else if (item.status === "blocked") out.todos.blocked += 1;
        else out.todos.open += 1;
        if (item.status === "done") continue;
        const blocked = item.status === "blocked";
        out.rows.push({
          key: `${note.relPath}#${item.id}`,
          status: blocked ? "interrupted" : "pending",
          title: item.title,
          context: blocked ? `blocked · ${note.name}` : note.name,
          relPath: note.relPath,
        });
      }
    } else if (view?.kind === "milestone") {
      out.total += 1;
      out.milestones.total += 1;
      if (view.status === "met") {
        out.met += 1;
        out.milestones.succeeded += 1;
      } else if (view.status === "missed") {
        out.milestones.failed += 1;
      } else {
        out.milestones.queued += 1;
        out.rows.push({
          key: note.relPath,
          status: "pending",
          title: note.name,
          context: view.criterion ? `milestone · ${view.criterion}` : "milestone",
          relPath: note.relPath,
        });
      }
    } else if (cls === "Delegation") {
      const delegation = asRecord(record);
      if (delegation.state === "blocked") {
        out.rows.push({
          key: note.relPath,
          status: "interrupted",
          title: delegationAsk(delegation),
          context: `${note.name} · waits for you`,
          relPath: note.relPath,
        });
      }
    }
  }
  return out;
};

const RANK = { interrupted: 0, pending: 1 } as const;

export const knowledgeOverview = (
  notes: readonly NoteSummary[],
  records: ReadonlyMap<string, unknown>,
): KnowledgeOverview => {
  const { todos, milestones, met, total, rows } = collect(notes, records);
  const waiting = rows.filter(
    (row) => row.status === "interrupted" && row.context.endsWith("waits for you"),
  ).length;
  const blocked = todos.blocked;
  const subject: string[] = [];
  if (blocked > 0) subject.push(plural(blocked, "blocked todo", "blocked todos"));
  if (waiting > 0)
    subject.push(plural(waiting, "delegation waits for you", "delegations wait for you"));
  const firstBlocked = rows.find((row) => row.status === "interrupted");
  const verdict =
    notes.length === 0
      ? { status: "pending", subject: "No documents yet", evidence: null }
      : subject.length > 0
        ? {
            status: "interrupted",
            subject: subject.join(" · "),
            evidence: firstBlocked ? `${firstBlocked.title} — ${firstBlocked.context}` : null,
          }
        : todos.open > 0
          ? {
              status: "running",
              subject: plural(todos.open, "open todo", "open todos"),
              evidence: rows[0] ? `Next: ${rows[0].title} — ${rows[0].context}` : null,
            }
          : { status: "succeeded", subject: "Nothing open", evidence: null };
  const byClass = KNOWLEDGE_CLASSES.map((cls) => ({
    cls,
    count: notes.filter((note) => knowledgeClassOf(note) === cls).length,
  })).filter((row) => row.count > 0);
  return {
    verdict,
    milestones,
    milestoneMet: met,
    milestoneTotal: total,
    todos,
    openWork: [...rows].sort((a, b) => RANK[a.status] - RANK[b.status]),
    byClass,
  };
};

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

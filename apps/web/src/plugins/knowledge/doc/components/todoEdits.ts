/**
 * Pure edits of a Todo record (`items: [{ id, title, status, stage? }]`).
 * Every edit returns a new record and keeps the record's other keys; an item
 * carries only the keys the class accepts (the server forbids extras).
 */

import { planningView, type TodoItemView } from "../../planningModel";

export type TodoRecord = Readonly<Record<string, unknown>>;

/**
 * The record's items: `[]` when it has none yet, `null` when `items` exists
 * but is not a list of `{ id, title }` (a write would destroy it).
 */
export const readTodoItems = (record: TodoRecord): TodoItemView[] | null => {
  const raw = record.items;
  if (raw === undefined || raw === null) return [];
  if (Array.isArray(raw) && raw.length === 0) return [];
  const view = planningView("Todo", record);
  return view?.kind === "todo" ? view.items : null;
};

const serialize = (item: TodoItemView): Record<string, unknown> =>
  item.stage
    ? { id: item.id, title: item.title, status: item.status, stage: item.stage }
    : { id: item.id, title: item.title, status: item.status };

const withItems = (
  record: TodoRecord,
  items: readonly TodoItemView[],
): Record<string, unknown> => ({
  ...record,
  items: items.map(serialize),
});

/** open ↔ done; a blocked item reopens. */
export const nextTodoStatus = (status: string): "open" | "done" =>
  status === "open" ? "done" : "open";

export const toggleTodo = (
  record: TodoRecord,
  items: readonly TodoItemView[],
  id: string,
): Record<string, unknown> =>
  withItems(
    record,
    items.map((item) => (item.id === id ? { ...item, status: nextTodoStatus(item.status) } : item)),
  );

/** `"Bind the workflow!"` → `"bind-the-workflow"`; empty → `"todo"`. */
export const slugTitle = (title: string): string => {
  const slug = title
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[^\p{Letter}\p{Number}]+/gu, "-")
    .replace(/^-+|-+$/g, "");
  return slug || "todo";
};

/** The title's slug, suffixed `-2`, `-3` … until no item uses it. */
export const uniqueTodoId = (title: string, taken: readonly string[]): string => {
  const base = slugTitle(title);
  const used = new Set(taken);
  if (!used.has(base)) return base;
  let n = 2;
  while (used.has(`${base}-${n}`)) n += 1;
  return `${base}-${n}`;
};

export const addTodo = (
  record: TodoRecord,
  items: readonly TodoItemView[],
  title: string,
): Record<string, unknown> => {
  const clean = title.trim();
  const id = uniqueTodoId(
    clean,
    items.map((item) => item.id),
  );
  return withItems(record, [...items, { id, title: clean, status: "open" }]);
};

/** Move item *id* to position *to* (index in the list after removal). */
export const moveTodo = (
  record: TodoRecord,
  items: readonly TodoItemView[],
  id: string,
  to: number,
): Record<string, unknown> | null => {
  const from = items.findIndex((item) => item.id === id);
  if (from < 0) return null;
  const rest = items.filter((item) => item.id !== id);
  const at = Math.max(0, Math.min(to, rest.length));
  if (at === from) return null;
  const moved = items[from] as TodoItemView;
  return withItems(record, [...rest.slice(0, at), moved, ...rest.slice(at)]);
};

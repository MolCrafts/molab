import { describe, expect, it } from "@rstest/core";
import {
  addTodo,
  moveTodo,
  nextTodoStatus,
  readTodoItems,
  slugTitle,
  toggleTodo,
  uniqueTodoId,
} from "./todoEdits";

const RECORD = {
  owner: "roy",
  items: [
    { id: "prepare", title: "Prepare NVE inputs", status: "done", stage: "prepare" },
    { id: "bind", title: "Bind the workflow", status: "open", stage: "bind" },
    { id: "compare", title: "Compare", status: "blocked" },
  ],
};
const ITEMS = readTodoItems(RECORD) ?? [];

describe("readTodoItems", () => {
  it("reads items, [] for none, null for a malformed list", () => {
    expect(ITEMS.map((item) => item.id)).toEqual(["prepare", "bind", "compare"]);
    expect(readTodoItems({})).toEqual([]);
    expect(readTodoItems({ items: [] })).toEqual([]);
    expect(readTodoItems({ items: [{ title: "no id" }] })).toBeNull();
    expect(readTodoItems({ items: "x" })).toBeNull();
  });
});

describe("toggleTodo", () => {
  it("flips open and done, reopens blocked, keeps other keys and the input", () => {
    expect(nextTodoStatus("open")).toBe("done");
    expect(nextTodoStatus("done")).toBe("open");
    expect(nextTodoStatus("blocked")).toBe("open");
    const next = toggleTodo(RECORD, ITEMS, "bind");
    expect(next.owner).toBe("roy");
    expect(next.items).toEqual([
      { id: "prepare", title: "Prepare NVE inputs", status: "done", stage: "prepare" },
      { id: "bind", title: "Bind the workflow", status: "done", stage: "bind" },
      { id: "compare", title: "Compare", status: "blocked" },
    ]);
    expect(RECORD.items[1]?.status).toBe("open");
  });
});

describe("todo ids", () => {
  it("slugs a title", () => {
    expect(slugTitle("Bind the workflow!")).toBe("bind-the-workflow");
    expect(slugTitle("  ")).toBe("todo");
    expect(slugTitle("Δt = 2 fs")).toBe("δt-2-fs");
  });
  it("suffixes until unique", () => {
    expect(uniqueTodoId("Bind", ["bind", "bind-2"])).toBe("bind-3");
    expect(uniqueTodoId("New", ["bind"])).toBe("new");
  });
});

describe("addTodo", () => {
  it("appends an open item with a unique id", () => {
    const next = addTodo(RECORD, ITEMS, "  Bind  ");
    expect((next.items as unknown[]).at(-1)).toEqual({
      id: "bind-2",
      title: "Bind",
      status: "open",
    });
    expect(RECORD.items).toHaveLength(3);
  });
});

describe("moveTodo", () => {
  const ids = (record: Record<string, unknown> | null): string[] =>
    ((record?.items ?? []) as { id: string }[]).map((item) => item.id);
  it("moves an item to a position", () => {
    expect(ids(moveTodo(RECORD, ITEMS, "compare", 0))).toEqual(["compare", "prepare", "bind"]);
    expect(ids(moveTodo(RECORD, ITEMS, "prepare", 2))).toEqual(["bind", "compare", "prepare"]);
  });
  it("returns null for no move or an unknown id", () => {
    expect(moveTodo(RECORD, ITEMS, "bind", 1)).toBeNull();
    expect(moveTodo(RECORD, ITEMS, "nope", 0)).toBeNull();
  });
});

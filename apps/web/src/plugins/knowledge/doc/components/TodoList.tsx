/**
 * `<molab-todo-list>` (L10, Figma v2_02): a Todo record's items as 32px rows —
 * a box to check, the title, the stage at the right; a blocked item carries
 * the interrupted glyph. A grip on hover drags to reorder, and the last row
 * adds a todo on ↵. The state is the record: every change writes it whole.
 */

import { Check, GripVertical, ListTodo, Plus } from "lucide-react";
import { type DragEvent, type JSX, type KeyboardEvent, useState } from "react";
import { StatusIcon } from "@/app/components/entity";
import { cn } from "@/lib/utils";
import type { TodoItemView } from "../../planningModel";
import type { DocComponentProps, DocComponentSpec } from "../context";
import { ComponentFrame, ComponentLoading, ComponentNotice } from "../frame";
import { addTodo, moveTodo, readTodoItems, toggleTodo } from "./todoEdits";
import { useRecordSource } from "./useRecordSource";

const NAME = "molab-todo-list";

const TodoBox = ({
  item,
  disabled,
  onToggle,
}: {
  item: TodoItemView;
  disabled: boolean;
  onToggle: () => void;
}): JSX.Element => {
  const done = item.status === "done";
  return (
    <span className="relative inline-flex size-4 flex-none items-center justify-center">
      <input
        type="checkbox"
        checked={done}
        aria-label={item.title}
        disabled={disabled}
        onChange={onToggle}
        className={cn(
          "size-4 cursor-pointer appearance-none rounded-checkbox border outline-none",
          "focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-default",
          done && "border-status-completed bg-status-completed",
          !done && item.status === "blocked" && "border-status-warning bg-surface",
          !done && item.status !== "blocked" && "border-input bg-surface hover:border-foreground",
        )}
      />
      {done ? (
        <Check
          aria-hidden
          strokeWidth={3}
          className="pointer-events-none absolute size-3 text-accent-foreground"
        />
      ) : null}
    </span>
  );
};

interface RowProps {
  item: TodoItemView;
  writable: boolean;
  dragging: boolean;
  onToggle: () => void;
  onDragStart: (event: DragEvent<HTMLButtonElement>) => void;
  onDragEnd: () => void;
  onDrop: () => void;
  onNudge: (step: -1 | 1) => void;
}

const TodoRow = ({ item, writable, dragging, ...on }: RowProps): JSX.Element => {
  const done = item.status === "done";
  const blocked = item.status === "blocked";
  const nudge = (event: KeyboardEvent<HTMLButtonElement>): void => {
    if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
    event.preventDefault();
    on.onNudge(event.key === "ArrowUp" ? -1 : 1);
  };
  return (
    <li
      className={cn(
        "group flex h-8 items-center gap-2 border-b border-border pr-3 pl-1 hover:bg-surface-subtle",
        dragging && "opacity-60",
      )}
      onDragOver={(event) => event.preventDefault()}
      onDrop={(event) => {
        event.preventDefault();
        on.onDrop();
      }}
    >
      <button
        type="button"
        draggable={writable}
        disabled={!writable}
        aria-label={`Move ${item.title}`}
        title="Drag to reorder"
        onDragStart={on.onDragStart}
        onDragEnd={on.onDragEnd}
        onKeyDown={nudge}
        className="inline-flex size-4 flex-none cursor-grab items-center justify-center text-muted-foreground opacity-0 outline-none focus-visible:opacity-100 group-hover:opacity-100 disabled:invisible"
      >
        <GripVertical aria-hidden className="size-icon-sm" />
      </button>
      <TodoBox item={item} disabled={!writable} onToggle={on.onToggle} />
      <span
        className={cn(
          "min-w-0 flex-1 truncate text-body",
          done ? "text-muted-foreground line-through" : "text-foreground",
        )}
      >
        {item.title}
      </span>
      {blocked ? <StatusIcon status="interrupted" label="Blocked" /> : null}
      {item.stage ? (
        <span className="flex-none truncate text-label text-muted-foreground">{item.stage}</span>
      ) : null}
    </li>
  );
};

const AddRow = ({
  disabled,
  onAdd,
}: {
  disabled: boolean;
  onAdd: (title: string) => void;
}): JSX.Element => {
  const [title, setTitle] = useState("");
  return (
    <li className="flex h-8 items-center gap-2 pr-3 pl-6 text-muted-foreground">
      <Plus aria-hidden className="size-icon-sm flex-none" />
      <input
        value={title}
        disabled={disabled}
        aria-label="Add a todo"
        placeholder="Add a todo · ↵"
        onChange={(event) => setTitle(event.target.value)}
        onKeyDown={(event) => {
          if (event.key !== "Enter" || event.nativeEvent.isComposing || !title.trim()) return;
          event.preventDefault();
          onAdd(title);
          setTitle("");
        }}
        className="h-7 min-w-0 flex-1 bg-transparent text-body text-foreground outline-none placeholder:text-muted-foreground disabled:cursor-default"
      />
    </li>
  );
};

export const TodoList = ({ attrs }: DocComponentProps): JSX.Element => {
  const source = useRecordSource(attrs.src);
  const [dragId, setDragId] = useState<string | null>(null);
  if (source.state === "loading") return <ComponentLoading name={NAME} />;
  if (source.state === "missing")
    return <ComponentNotice name={NAME}>{source.message}</ComponentNotice>;
  if (!attrs.src && source.cls !== "Todo") {
    return <ComponentNotice name={NAME}>Set src to the path of a Todo document.</ComponentNotice>;
  }
  const items = readTodoItems(source.record);
  if (!items) {
    return (
      <ComponentNotice name={NAME}>The record&apos;s items are not a todo list.</ComponentNotice>
    );
  }
  const { record, writable, commit } = source;
  const drop = (targetId: string): void => {
    const to = items.findIndex((item) => item.id === targetId);
    const next = dragId ? moveTodo(record, items, dragId, to) : null;
    setDragId(null);
    if (next) commit(next);
  };
  const nudge = (id: string, step: -1 | 1): void => {
    const from = items.findIndex((item) => item.id === id);
    const next = moveTodo(record, items, id, from + step);
    if (next) commit(next);
  };
  return (
    <ComponentFrame
      label="Todo list"
      footer={attrs.src ? <span className="truncate font-mono">{attrs.src}</span> : undefined}
    >
      <ul>
        {items.map((item) => (
          <TodoRow
            key={item.id}
            item={item}
            writable={writable}
            dragging={dragId === item.id}
            onToggle={() => commit(toggleTodo(record, items, item.id))}
            onDragStart={(event) => {
              event.dataTransfer.effectAllowed = "move";
              event.dataTransfer.setData("text/plain", item.id);
              const row = event.currentTarget.closest("li");
              if (row) event.dataTransfer.setDragImage(row, 0, 0);
              setDragId(item.id);
            }}
            onDragEnd={() => setDragId(null)}
            onDrop={() => drop(item.id)}
            onNudge={(step) => nudge(item.id, step)}
          />
        ))}
        <AddRow disabled={!writable} onAdd={(title) => commit(addTodo(record, items, title))} />
      </ul>
      {source.error ? (
        <p
          role="alert"
          className="border-t border-border px-3 py-1 text-label text-status-failed-foreground"
        >
          {source.error}
        </p>
      ) : null}
    </ComponentFrame>
  );
};

export const todoListSpec: DocComponentSpec = {
  name: NAME,
  label: "Todo list",
  description: "A Todo record's items: check, drag to order, ↵ adds.",
  keywords: ["todo", "task", "checklist", "check"],
  icon: ListTodo,
  template: {},
  Component: TodoList,
};

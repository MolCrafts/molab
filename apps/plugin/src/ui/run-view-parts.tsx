/**
 * The building blocks of a run view (L14): the files list, the style panel and
 * its rows, the in-view menu button, choice toggles, chart panels, key / value
 * facts and the shared states. Every run plugin composes these inside
 * `<RunView>`; none draws its own chrome.
 */

import { type JSX, type ReactNode, useEffect, useRef, useState } from "react";
import { cn } from "../utils";

// ── icons (the SDK carries no icon library) ──────────────────────────────────
const svg = (d: ReactNode, className = "size-4"): JSX.Element => (
  <svg
    aria-hidden
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={1.8}
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    {d}
  </svg>
);
export const IconCheck = ({ className }: { className?: string }): JSX.Element =>
  svg(<path d="M20 6 9 17l-5-5" />, className);
export const IconX = ({ className }: { className?: string }): JSX.Element =>
  svg(<path d="M18 6 6 18M6 6l12 12" />, className);
export const IconPanelRight = ({ className }: { className?: string }): JSX.Element =>
  svg(
    <>
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <path d="M15 3v18" />
    </>,
    className,
  );
export const IconExpand = ({ className }: { className?: string }): JSX.Element =>
  svg(<path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7" />, className);

/** A 22px icon-only control (VS Code action); `label` is its name and tooltip. */
export const RunViewIconButton = ({
  label,
  pressed,
  onClick,
  children,
}: {
  label: string;
  pressed?: boolean;
  onClick?: () => void;
  children: ReactNode;
}): JSX.Element => (
  <button
    type="button"
    aria-label={label}
    title={label}
    aria-pressed={pressed}
    onClick={onClick}
    className={cn(
      "inline-flex size-6 items-center justify-center rounded-control text-muted-foreground hover:bg-interactive hover:text-foreground",
      pressed && "bg-accent-muted text-foreground",
    )}
  >
    {children}
  </button>
);

// ── files ─────────────────────────────────────────────────────────────────────
export interface RunViewFileItem {
  id: string;
  label: string;
  /** Muted, right-aligned (a size). */
  meta?: string;
  icon?: ReactNode;
  /** The item's legend colour (a CSS colour); the checkbox takes it. */
  color?: string;
  checked?: boolean;
  selected?: boolean;
}

export const RunViewFiles = ({
  title = "Files",
  items,
  mode,
  onToggle,
  onPick,
  empty = "No files.",
}: {
  title?: string;
  items: readonly RunViewFileItem[];
  /** `check`: include / exclude each file; `pick`: one is shown. */
  mode: "check" | "pick";
  onToggle?: (id: string) => void;
  onPick?: (id: string) => void;
  empty?: string;
}): JSX.Element => (
  <nav
    aria-label={title}
    className="flex min-h-0 w-62 flex-none flex-col border-r border-border max-md:w-full max-md:border-r-0 max-md:border-b"
  >
    <div className="flex h-8 flex-none items-center border-b border-border px-3 max-md:hidden">
      <span className="text-micro font-semibold uppercase tracking-wide text-muted-foreground">
        {title}
      </span>
    </div>
    {/* Phones: one horizontally scrolling row of the same items, above the view. */}
    <ul className="min-h-0 flex-1 overflow-auto py-1 max-md:flex max-md:flex-none max-md:gap-1 max-md:overflow-x-auto max-md:px-2">
      {items.length === 0 ? (
        <li className="px-3 py-2 text-label text-muted-foreground">{empty}</li>
      ) : null}
      {items.map((item) => (
        <li key={item.id}>
          <button
            type="button"
            aria-pressed={mode === "check" ? Boolean(item.checked) : Boolean(item.selected)}
            onClick={() => (mode === "check" ? onToggle?.(item.id) : onPick?.(item.id))}
            className={cn(
              "flex h-7 w-full items-center gap-2 px-3 text-left hover:bg-interactive",
              "max-md:w-auto max-md:flex-none max-md:rounded-control max-md:border max-md:border-border",
              item.selected && "bg-accent-muted",
            )}
          >
            {mode === "check" ? (
              <span
                aria-hidden
                className="inline-flex size-4 flex-none items-center justify-center rounded-sm border-2 text-accent-foreground"
                style={{
                  borderColor: item.checked ? (item.color ?? "currentColor") : undefined,
                  background: item.checked ? (item.color ?? "currentColor") : undefined,
                }}
              >
                {item.checked ? <IconCheck className="size-3" /> : null}
              </span>
            ) : null}
            {item.icon ? (
              <span className="flex-none text-muted-foreground">{item.icon}</span>
            ) : null}
            <span className="min-w-0 flex-1 truncate font-mono text-label">{item.label}</span>
            {item.meta ? (
              <span className="flex-none text-label tabular-nums text-muted-foreground">
                {item.meta}
              </span>
            ) : null}
          </button>
        </li>
      ))}
    </ul>
  </nav>
);

// ── style panel ───────────────────────────────────────────────────────────────
export const RunViewStyleGroup = ({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}): JSX.Element => (
  <section className="pt-2">
    <h4 className="px-3 pb-1 text-label font-semibold text-foreground">{title}</h4>
    {children}
  </section>
);

export const RunViewStyleRow = ({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}): JSX.Element => (
  <div className="flex min-h-8 items-center gap-3 px-3 text-body">
    <span className="w-24 flex-none text-foreground">{label}</span>
    <div className="flex min-w-0 flex-1 items-center gap-2">{children}</div>
  </div>
);

/** VS Code toggles: 22px words, the chosen one washed. */
export const RunViewChoice = <V extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: V;
  options: readonly { value: V; label: string }[];
  onChange: (next: V) => void;
}): JSX.Element => (
  <fieldset aria-label={label} className="flex items-center gap-hairline">
    {options.map((option) => (
      <button
        key={option.value}
        type="button"
        aria-pressed={option.value === value}
        onClick={() => onChange(option.value)}
        className={cn(
          "inline-flex h-shell-action items-center rounded-action px-2 text-label",
          option.value === value
            ? "bg-accent-muted text-foreground"
            : "text-muted-foreground hover:bg-interactive hover:text-foreground",
        )}
      >
        {option.label}
      </button>
    ))}
  </fieldset>
);

export const RunViewSwitch = ({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (next: boolean) => void;
}): JSX.Element => (
  <button
    type="button"
    role="switch"
    aria-label={label}
    aria-checked={checked}
    onClick={() => onChange(!checked)}
    className={cn(
      "relative inline-flex h-4 w-7 flex-none items-center rounded-full transition-colors",
      checked ? "bg-accent" : "bg-input",
    )}
  >
    <span
      className={cn(
        "absolute size-3 rounded-full bg-surface transition-transform",
        checked ? "translate-x-3.5" : "translate-x-0.5",
      )}
    />
  </button>
);

// ── in-view menu (e.g. Group by) ──────────────────────────────────────────────
export const RunViewMenu = <V extends string>({
  label,
  icon,
  value,
  options,
  onChange,
}: {
  label: string;
  icon: ReactNode;
  value: V;
  options: readonly { value: V; label: string }[];
  onChange: (next: V) => void;
}): JSX.Element => {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (event: Event): void => {
      if (event instanceof KeyboardEvent && event.key !== "Escape") return;
      if (event instanceof PointerEvent && root.current?.contains(event.target as Node)) return;
      setOpen(false);
    };
    document.addEventListener("pointerdown", close, true);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("pointerdown", close, true);
      document.removeEventListener("keydown", close);
    };
  }, [open]);
  return (
    <div ref={root} className="relative">
      <RunViewIconButton label={label} pressed={open} onClick={() => setOpen((v) => !v)}>
        {icon}
      </RunViewIconButton>
      {open ? (
        <div
          role="menu"
          aria-label={label}
          className="absolute top-7 right-0 z-20 w-48 rounded-control border border-border bg-surface p-1 shadow-overlay"
        >
          <div className="px-2 py-1 text-label text-muted-foreground">{label}</div>
          {options.map((option) => (
            <button
              key={option.value}
              type="button"
              role="menuitemradio"
              aria-checked={option.value === value}
              onClick={() => {
                onChange(option.value);
                setOpen(false);
              }}
              className={cn(
                "flex h-7 w-full items-center rounded-sm px-2 text-left text-body hover:bg-interactive",
                option.value === value && "bg-accent-muted",
              )}
            >
              <span className="flex-1">{option.label}</span>
              {option.value === value ? <IconCheck className="size-icon-sm" /> : null}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
};

// ── content blocks ────────────────────────────────────────────────────────────
/** A chart's chrome: name, unit, last value (mono), enlarge. */
export const RunViewPanel = ({
  title,
  unit,
  value,
  note,
  onEnlarge,
  children,
}: {
  title: string;
  unit?: string;
  value?: string;
  /** Muted, after the unit (e.g. "figure"). */
  note?: string;
  onEnlarge?: () => void;
  children: ReactNode;
}): JSX.Element => (
  <section
    aria-label={title}
    className="flex min-w-0 flex-col gap-1 rounded-control border border-border bg-surface px-3 pt-2 pb-1"
  >
    <header className="flex items-center gap-2">
      <span className="truncate text-body font-medium">{title}</span>
      {unit ? <span className="text-label text-muted-foreground">{unit}</span> : null}
      {note ? <span className="text-label text-muted-foreground">{note}</span> : null}
      <span className="flex-1" />
      {value ? <span className="font-mono text-label tabular-nums">{value}</span> : null}
      {onEnlarge ? (
        <RunViewIconButton label={`Enlarge ${title}`} onClick={onEnlarge}>
          <IconExpand className="size-3" />
        </RunViewIconButton>
      ) : null}
    </header>
    {children}
  </section>
);

/** Panels in a responsive grid: as many 16rem columns as fit. */
export const RunViewGrid = ({ children }: { children: ReactNode }): JSX.Element => (
  <div className="grid grid-cols-[repeat(auto-fill,minmax(16rem,1fr))] gap-3">{children}</div>
);

export const RunViewFacts = ({
  rows,
}: {
  rows: readonly (readonly [string, ReactNode])[];
}): JSX.Element => (
  <dl className="divide-y divide-border border-y border-border">
    {rows.map(([key, value]) => (
      <div key={key} className="flex h-7 items-center text-body">
        <dt className="w-40 flex-none text-muted-foreground">{key}</dt>
        <dd className="min-w-0 truncate font-mono">{value}</dd>
      </div>
    ))}
  </dl>
);

export type RunViewStateSpec =
  | { kind: "loading" }
  | { kind: "empty"; title: string; detail?: string }
  | { kind: "error"; title: string; detail?: string; onRetry?: () => void };

export const RunViewState = ({ state }: { state: RunViewStateSpec }): JSX.Element => {
  if (state.kind === "loading") {
    return (
      <div aria-busy className="flex flex-col gap-3 p-6">
        {[90, 70, 80, 50].map((width) => (
          <div key={width} className="h-3 rounded-sm bg-muted" style={{ width: `${width}%` }} />
        ))}
      </div>
    );
  }
  return (
    <div
      role={state.kind === "error" ? "alert" : "status"}
      className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center"
    >
      <span className="text-body font-medium">{state.title}</span>
      {state.detail ? (
        <span className="max-w-96 text-label text-muted-foreground">{state.detail}</span>
      ) : null}
      {state.kind === "error" && state.onRetry ? (
        <button
          type="button"
          onClick={state.onRetry}
          className="mt-1 inline-flex h-6 items-center rounded-control bg-secondary px-3 text-body hover:bg-secondary/80"
        >
          Retry
        </button>
      ) : null}
    </div>
  );
};

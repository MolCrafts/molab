// ─────────────────────────────────────────────────────────────────────────────
// GlobalCommandPalette
//
//   ⌘K / Ctrl+K        → Go to… (projects / experiments / runs / …)
//   ⌘⇧P / Ctrl+Shift+P → Commands (reload, reconnect, …)  — same as molvis
// ─────────────────────────────────────────────────────────────────────────────

import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  Dialog,
  DialogContent,
  DialogTitle,
  Kbd,
} from "@molcrafts/ui";
import { type JSX, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { StatusIcon } from "@/app/components/entity/StatusIcon";
import { buildCatalog, type CatalogEntry, searchCatalog } from "@/app/entities/catalog";
import { type EntityRef, entityMeta } from "@/app/entities/kinds";
import { entityPath } from "@/app/entities/paths";
import { usePreview } from "@/app/preview/PreviewContext";
import type { PreviewTarget } from "@/app/preview/target";
import type { WorkspaceSnapshot } from "@/app/types";
import { WorkbenchOperationState, WorkbenchRetryAction } from "@/components/workbench";

import { listCommands, useWorkbenchGeneration } from "@/plugins/contributions/workbench";
import { useKnowledgeListQuery } from "@/plugins/knowledge/queries";
export interface PaletteCommand {
  id: string;
  label: string;
  detail?: string;
  /** Registry spelling ("alt+b"); shown as ⌥B. */
  keybinding?: string;
  run: () => void;
}

interface GlobalCommandPaletteProps {
  snapshot: WorkspaceSnapshot;
  /** Host actions for ⌘⇧P (Reload, Reconnect, …). */
  commands?: PaletteCommand[];
}

export type PaletteMode = "goto" | "commands";

const paletteRequests = new Set<(mode: PaletteMode) => void>();

/** Open the palette from chrome (the title-bar command centre, the mobile search). */
export const openCommandPalette = (mode: PaletteMode = "goto"): void => {
  for (const request of paletteRequests) request(mode);
};

function scoreCommand(query: string, label: string, detail?: string): number {
  const q = query.trim().toLowerCase();
  if (!q) return 1;
  const hay = `${label} ${detail ?? ""}`.toLowerCase();
  if (hay === q) return 100;
  if (hay.startsWith(q)) return 80;
  if (hay.includes(q)) return 50;
  let i = 0;
  for (const ch of hay) {
    if (ch === q[i]) i += 1;
    if (i >= q.length) return 20;
  }
  return 0;
}

// ── Go to rows (L13-5) ─────────────────────────────────────────────────────────

const GROUP_ORDER: readonly { kind: string; heading: string }[] = [
  { kind: "run", heading: "Runs" },
  { kind: "experiment", heading: "Experiments" },
  { kind: "project", heading: "Projects" },
  { kind: "knowledge", heading: "Documents" },
  { kind: "asset", heading: "Assets" },
  { kind: "workflow", heading: "Workflows" },
];

const entryValue = (entry: CatalogEntry): string => `${entry.ref.kind}:${entry.ref.id}`;

/** Results grouped by kind, each group keeping the search's own order. */
const groupResults = (entries: readonly CatalogEntry[]): [string, CatalogEntry[]][] =>
  GROUP_ORDER.flatMap(({ kind, heading }) => {
    const members = entries.filter((entry) => entry.ref.kind === kind);
    return members.length > 0 ? [[heading, members] as [string, CatalogEntry[]]] : [];
  });

/** Where the entry lives, read as a path: project › experiment. */
const whereOf = (ref: EntityRef, snapshot: WorkspaceSnapshot): string => {
  if (ref.kind === "run") {
    const run = snapshot.runs.find((item) => item.id === ref.id);
    const project = snapshot.projects.find((item) => item.id === run?.projectId);
    const experiment = snapshot.experiments.find((item) => item.id === run?.experimentId);
    return [project?.name, experiment?.name, run?.id].filter(Boolean).join(" › ");
  }
  if (ref.kind === "experiment") {
    const experiment = snapshot.experiments.find((item) => item.id === ref.id);
    return snapshot.projects.find((item) => item.id === experiment?.projectId)?.name ?? "";
  }
  if (ref.kind === "knowledge") return ref.id.split("/knowledges/")[0] ?? "";
  return "";
};

/** What ⇧↵ previews; null where the kind has no Preview (workflow). */
const previewTargetOf = (ref: EntityRef, snapshot: WorkspaceSnapshot): PreviewTarget | null => {
  switch (ref.kind) {
    case "run": {
      const run = snapshot.runs.find((item) => item.id === ref.id);
      return run
        ? { kind: "run", runId: run.id, projectId: run.projectId, experimentId: run.experimentId }
        : null;
    }
    case "experiment": {
      const experiment = snapshot.experiments.find((item) => item.id === ref.id);
      return experiment
        ? { kind: "experiment", projectId: experiment.projectId, experimentId: experiment.id }
        : null;
    }
    case "project":
      return { kind: "project", projectId: ref.id };
    case "asset":
      return { kind: "asset", assetId: ref.id };
    case "knowledge":
      return { kind: "knowledge", path: ref.id };
    default:
      return null;
  }
};

const EntryGlyph = ({ entry }: { entry: CatalogEntry }): JSX.Element => {
  if (entry.ref.kind === "run" && entry.ref.status) {
    return <StatusIcon status={entry.ref.status} className="size-icon" />;
  }
  const Icon = entityMeta(entry.ref.kind).icon;
  return <Icon className="size-icon flex-none text-muted-foreground" />;
};

/** The first match of the query, marked in the link colour. */
const Marked = ({ text, query }: { text: string; query: string }): JSX.Element => {
  const needle = query.trim().toLowerCase();
  const at = needle ? text.toLowerCase().indexOf(needle) : -1;
  if (at < 0) return <>{text}</>;
  return (
    <>
      {text.slice(0, at)}
      <mark className="bg-transparent font-semibold text-link">
        {text.slice(at, at + needle.length)}
      </mark>
      {text.slice(at + needle.length)}
    </>
  );
};

const KEY_GLYPH: Record<string, string> = {
  alt: "⌥",
  option: "⌥",
  shift: "⇧",
  mod: "⌘",
  meta: "⌘",
  cmd: "⌘",
  ctrl: "⌃",
  bracketleft: "[",
  bracketright: "]",
  enter: "↵",
};

/** "alt+bracketleft" → "⌥[" — the registry's spelling, read as keys. */
export const prettyKeys = (binding: string): string =>
  binding
    .split("+")
    .map((part) => part.trim().toLowerCase())
    .map((part) => KEY_GLYPH[part] ?? part.toUpperCase())
    .join("");

export const GlobalCommandPalette = ({
  snapshot,
  commands = [],
}: GlobalCommandPaletteProps): JSX.Element => {
  useWorkbenchGeneration();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<PaletteMode>("goto");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState("");
  const preview = usePreview();

  const modeRef = useRef(mode);
  const openRef = useRef(open);
  modeRef.current = mode;
  openRef.current = open;

  useEffect(() => {
    const request = (next: PaletteMode): void => {
      setMode(next);
      setOpen(true);
    };
    paletteRequests.add(request);
    return () => {
      paletteRequests.delete(request);
    };
  }, []);

  // ⌘K → go to; ⌘⇧P → commands (molvis / VS Code parity).
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent): void => {
      const key = event.key.toLowerCase();
      const mod = event.metaKey || event.ctrlKey;
      if (!mod) return;
      if (key === "k" && !event.shiftKey) {
        event.preventDefault();
        if (openRef.current && modeRef.current === "goto") {
          setOpen(false);
        } else {
          setMode("goto");
          setOpen(true);
        }
      } else if (key === "p" && event.shiftKey) {
        event.preventDefault();
        if (openRef.current && modeRef.current === "commands") {
          setOpen(false);
        } else {
          setMode("commands");
          setOpen(true);
        }
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const knowledgeQuery = useKnowledgeListQuery({}, open && mode === "goto");
  const knowledgeDocs = knowledgeQuery.data?.notes ?? [];
  const knowledgeLoading = knowledgeQuery.isFetching;
  const knowledgeError = knowledgeQuery.error
    ? knowledgeQuery.error instanceof Error
      ? knowledgeQuery.error.message
      : "Failed to load knowledge search entries."
    : null;

  const catalog = useMemo(() => buildCatalog(snapshot, knowledgeDocs), [snapshot, knowledgeDocs]);

  // ">" in Go to switches to Commands, as in VS Code (L13-6).
  const commandMode = mode === "commands" || query.startsWith(">");
  const commandQuery = mode === "commands" ? query : query.replace(/^>\s*/, "");
  const gotoResults = useMemo(
    () => (commandMode ? [] : searchCatalog(catalog, query)),
    [catalog, query, commandMode],
  );

  const allCommands: PaletteCommand[] = [
    ...listCommands()
      .filter((command) => command.isVisible?.() ?? true)
      .map((command) => ({
        id: command.id,
        label: command.title,
        detail: command.category,
        keybinding: command.keybinding,
        run: () => {
          void command.run();
        },
      })),
    ...commands,
  ];
  const commandResults = allCommands
    .map((c) => ({ cmd: c, score: scoreCommand(commandQuery, c.label, c.detail) }))
    .filter((x) => x.score > 0)
    .sort((a, b) => b.score - a.score || a.cmd.label.localeCompare(b.cmd.label))
    .map((x) => x.cmd);

  // Each open starts clean: no query, and the top row highlighted (cmdk picks
  // the first item when nothing is selected). A mode switch starts clean too.
  // biome-ignore lint/correctness/useExhaustiveDependencies: `mode` is the trigger, not a value read
  useEffect(() => {
    if (!open) return;
    setQuery("");
    setSelected("");
  }, [open, mode]);

  const close = (): void => setOpen(false);
  const openEntry = (entry: CatalogEntry, asPreview: boolean): void => {
    const target = asPreview ? previewTargetOf(entry.ref, snapshot) : null;
    if (target) {
      preview.preview(target);
      close();
      return;
    }
    const path = entityPath(entry.ref, snapshot);
    if (!path) return;
    preview.close();
    navigate(path);
    close();
  };
  const runCommandEntry = (cmd: PaletteCommand): void => {
    close();
    cmd.run();
  };

  const groups = groupResults(gotoResults);
  const findEntry = (value: string): CatalogEntry | undefined =>
    gotoResults.find((entry) => entryValue(entry) === value);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent
        showCloseButton={false}
        aria-describedby={undefined}
        className="top-1 max-w-overlay-viewport -translate-y-0 gap-0 overflow-hidden rounded-panel p-2 sm:max-w-quick-input"
      >
        <DialogTitle className="sr-only">{commandMode ? "Commands" : "Go to"}</DialogTitle>
        <Command
          shouldFilter={false}
          loop
          value={selected}
          onValueChange={setSelected}
          className="bg-transparent"
          onKeyDown={(event) => {
            // ⇧↵ previews the highlighted entry (L12) instead of opening it.
            if (event.key === "Enter" && event.shiftKey && !commandMode) {
              const entry = findEntry(selected);
              if (entry) {
                event.preventDefault();
                openEntry(entry, true);
              }
            }
          }}
        >
          {/* The field chrome is the palette's own (L13-5): the shared input's
              wrapper loses its border, height and icon here. */}
          <div
            className={`flex h-control-compact items-center gap-2 rounded-hairline border border-accent px-2 ring-1 ring-accent [&_[data-slot=command-input-wrapper]]:h-full [&_[data-slot=command-input-wrapper]]:min-w-0 [&_[data-slot=command-input-wrapper]]:flex-1 [&_[data-slot=command-input-wrapper]]:border-0 [&_[data-slot=command-input-wrapper]]:px-0 ${commandMode ? "[&_[data-slot=command-input-wrapper]_svg]:hidden" : ""}`}
          >
            {commandMode ? (
              <span className="font-mono text-label text-muted-foreground" aria-hidden>
                &gt;
              </span>
            ) : null}
            <CommandInput
              value={query}
              onValueChange={setQuery}
              placeholder={
                commandMode ? "Type a command" : "Go to a project, experiment, run, document…"
              }
              aria-label={commandMode ? "Run a command" : "Go to"}
              className="h-full"
            />
            {commandMode ? null : (
              <span className="hidden flex-none text-label text-muted-foreground sm:inline">
                type <span className="font-mono">&gt;</span> for commands
              </span>
            )}
          </div>
          {!commandMode && knowledgeError ? (
            <WorkbenchOperationState
              kind="error"
              density="compact"
              title="Documents unavailable"
              detail={`${knowledgeError} Projects, experiments, runs and assets are still searched.`}
              action={<WorkbenchRetryAction onClick={() => void knowledgeQuery.refetch()} />}
            />
          ) : null}
          <CommandList className="mt-1 max-h-scroll-compact">
            <CommandEmpty>
              <WorkbenchOperationState
                kind={!commandMode && knowledgeLoading ? "loading" : "empty"}
                density="compact"
                title={
                  commandMode
                    ? commandQuery
                      ? "No matching commands"
                      : "No commands registered"
                    : knowledgeLoading
                      ? "Searching…"
                      : "No matches"
                }
                detail={commandMode || knowledgeLoading ? undefined : "Try another name or id."}
              />
            </CommandEmpty>
            {commandMode
              ? commandResults.map((cmd) => (
                  <CommandItem
                    key={cmd.id}
                    value={`command:${cmd.id}`}
                    onSelect={() => runCommandEntry(cmd)}
                    className="h-shell-button gap-2 rounded-hairline px-2 data-[selected=true]:bg-accent-muted data-[selected=true]:text-foreground"
                  >
                    {cmd.detail ? (
                      <span className="flex-none text-label text-muted-foreground">
                        {cmd.detail}:
                      </span>
                    ) : null}
                    <span className="min-w-0 flex-1 truncate">{cmd.label}</span>
                    {cmd.keybinding ? <Kbd>{prettyKeys(cmd.keybinding)}</Kbd> : null}
                  </CommandItem>
                ))
              : groups.map(([heading, entries]) => (
                  <CommandGroup
                    key={heading}
                    heading={heading}
                    className="[&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:pt-2 [&_[cmdk-group-heading]]:pb-1 [&_[cmdk-group-heading]]:text-micro [&_[cmdk-group-heading]]:text-muted-foreground"
                  >
                    {entries.map((entry) => (
                      <CommandItem
                        key={entryValue(entry)}
                        value={entryValue(entry)}
                        onSelect={() => openEntry(entry, false)}
                        className="h-shell-button gap-2 rounded-hairline px-2 data-[selected=true]:bg-accent-muted data-[selected=true]:text-foreground"
                      >
                        <EntryGlyph entry={entry} />
                        <span
                          className={`flex-none truncate ${entry.ref.kind === "run" ? "font-mono text-label" : ""}`}
                        >
                          <Marked text={entry.ref.label ?? entry.ref.id} query={query} />
                        </span>
                        <span className="min-w-0 flex-1 truncate text-label text-muted-foreground">
                          {whereOf(entry.ref, snapshot)}
                        </span>
                      </CommandItem>
                    ))}
                  </CommandGroup>
                ))}
          </CommandList>
          <div className="mt-1 flex h-7 items-center gap-3 border-t border-border px-2 text-label text-muted-foreground">
            <span className="flex items-center gap-1">
              <Kbd>↑↓</Kbd> move
            </span>
            <span className="flex items-center gap-1">
              <Kbd>↵</Kbd> {commandMode ? "run" : "open"}
            </span>
            {commandMode ? null : (
              <span className="flex items-center gap-1">
                <Kbd>⇧↵</Kbd> preview
              </span>
            )}
            <span className="flex items-center gap-1">
              <Kbd>Esc</Kbd> close
            </span>
          </div>
        </Command>
      </DialogContent>
    </Dialog>
  );
};

/**
 * Logs view (Figma L04-8): one attempt's `stdout`, `stderr` or `run.log`, one
 * stream at a time, with line numbers, find, ↑↓ between error and warning
 * lines, and download. Opened at a line (the evidence's "Open in Logs at line
 * N") it scrolls there and marks it. The attempt is the page's; this view
 * never chooses one. Lines render in a window, so a 2 MB log stays fast.
 */

import { ChevronDown, ChevronUp, Download, Search } from "lucide-react";
import {
  type JSX,
  type KeyboardEvent,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  classifyLines,
  findLines,
  type LineKind,
  lineStops,
  stepTo,
} from "@/app/renderers/logLines";
import {
  type ExecutionLogCoords,
  LOG_STREAMS,
  type LogStream,
  logFileOf,
  useExecutionLog,
} from "@/app/state/executionLog";
import { WorkbenchIconAction } from "@/components/workbench";
import { cn } from "@/lib/utils";

const ROW = 20;
const OVERSCAN = 30;

const STREAM_LABEL: Record<LogStream, string> = {
  stdout: "stdout",
  stderr: "stderr",
  run: "run.log",
};

interface RunLogsPanelProps {
  /** The attempt to follow; null when the run has none. */
  execution: ExecutionLogCoords | null;
  /** The attempt is active: follow its logs as they grow. */
  live?: boolean;
  /** The stream shown first. */
  defaultStream?: LogStream;
  /** 1-based line to open at, in the stream shown first. */
  line?: number | null;
  /** Open one of the attempt's files (attempt-relative path) in the file view. */
  onOpenFile?: (path: string) => void;
}

const StreamSwitch = ({
  stream,
  onChange,
}: {
  stream: LogStream;
  onChange: (next: LogStream) => void;
}): JSX.Element => (
  <fieldset
    aria-label="Log stream"
    className="flex h-6 items-center gap-hairline rounded-hairline bg-muted p-hairline"
  >
    {LOG_STREAMS.map((item) => (
      <button
        key={item}
        type="button"
        aria-pressed={item === stream}
        onClick={() => onChange(item)}
        className={cn(
          "h-full rounded-hairline px-2 font-mono text-label text-muted-foreground",
          "hover:text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
          item === stream && "bg-background text-foreground",
        )}
      >
        {STREAM_LABEL[item]}
      </button>
    ))}
  </fieldset>
);

const KIND_CLASS: Record<Exclude<LineKind, null>, string> = {
  error: "text-status-failed-foreground",
  warning: "text-status-warning-foreground",
};

/** Lines in a fixed-height window: only what is on screen (plus a margin) is in the DOM. */
const LogLines = ({
  lines,
  kinds,
  marked,
  matches,
  query,
  scrollRef,
  onScroll,
}: {
  lines: readonly string[];
  kinds: readonly LineKind[];
  /** 0-based line drawn as the current one. */
  marked: number | null;
  matches: ReadonlySet<number>;
  query: string;
  scrollRef: React.RefObject<HTMLDivElement | null>;
  onScroll: () => void;
}): JSX.Element => {
  const [view, setView] = useState({ top: 0, height: 600 });
  const measure = useCallback(() => {
    const element = scrollRef.current;
    if (element) setView({ top: element.scrollTop, height: element.clientHeight || 600 });
  }, [scrollRef]);
  useLayoutEffect(() => {
    measure();
    const element = scrollRef.current;
    if (!element || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [measure, scrollRef]);
  const first = Math.max(0, Math.floor(view.top / ROW) - OVERSCAN);
  const last = Math.min(lines.length, Math.ceil((view.top + view.height) / ROW) + OVERSCAN);
  const gutter = `${String(lines.length).length + 1}ch`;
  const needle = query.trim().toLowerCase();
  const paint = (text: string): JSX.Element | string => {
    if (!needle) return text || " ";
    const at = text.toLowerCase().indexOf(needle);
    if (at < 0) return text || " ";
    return (
      <>
        {text.slice(0, at)}
        <mark className="rounded-hairline bg-accent-muted text-inherit">
          {text.slice(at, at + needle.length)}
        </mark>
        {text.slice(at + needle.length)}
      </>
    );
  };
  return (
    <div
      ref={scrollRef}
      onScroll={() => {
        measure();
        onScroll();
      }}
      className="min-h-0 flex-1 overflow-auto bg-background font-mono text-label"
    >
      <div style={{ height: lines.length * ROW }} className="relative min-w-max">
        {lines.slice(first, last).map((text, offset) => {
          const index = first + offset;
          const kind = kinds[index] ?? null;
          return (
            <div
              key={index}
              data-line={index + 1}
              className={cn(
                "absolute inset-x-0 flex whitespace-pre pr-4",
                index === marked && "bg-status-failed-soft",
                index !== marked && matches.has(index) && "bg-interactive",
              )}
              style={{ top: index * ROW, height: ROW, lineHeight: `${ROW}px` }}
            >
              <span
                aria-hidden
                className="sticky left-0 shrink-0 select-none bg-inherit pr-4 pl-4 text-right text-muted-foreground"
                style={{ width: `calc(${gutter} + 2rem)` }}
              >
                {index + 1}
              </span>
              <span className={kind ? KIND_CLASS[kind] : "text-foreground"}>{paint(text)}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export const RunLogsPanel = ({
  execution,
  live = false,
  defaultStream = "run",
  line = null,
  onOpenFile,
}: RunLogsPanelProps): JSX.Element => {
  const [stream, setStream] = useState<LogStream>(defaultStream);
  const [query, setQuery] = useState("");
  const [marked, setMarked] = useState<number | null>(line ? line - 1 : null);
  const log = useExecutionLog(
    execution?.projectId ?? "",
    execution?.experimentId ?? "",
    execution?.runId ?? "",
    execution?.executionId ?? "",
    stream,
    { live, enabled: Boolean(execution) },
  );
  const text = log.data?.text ?? null;
  const lines = useMemo(() => (text ? text.replace(/\n$/, "").split("\n") : []), [text]);
  const kinds = useMemo(() => classifyLines(lines), [lines]);
  const { errors, warnings, stops } = useMemo(() => lineStops(kinds), [kinds]);
  const found = useMemo(() => findLines(lines, query), [lines, query]);
  const matchSet = useMemo(() => new Set(found), [found]);

  const scrollRef = useRef<HTMLDivElement | null>(null);
  const pinned = useRef(line === null);
  const scrollTo = useCallback((index: number) => {
    const element = scrollRef.current;
    if (!element) return;
    pinned.current = false;
    element.scrollTop = Math.max(0, index * ROW - element.clientHeight / 3);
  }, []);

  // A new target line (from the evidence) re-opens run.log at it.
  useEffect(() => {
    if (line === null) return;
    setStream(defaultStream);
    setMarked(line - 1);
  }, [line, defaultStream]);
  // Once the lines are in, go to the marked one; while live and at the bottom, follow.
  // biome-ignore lint/correctness/useExhaustiveDependencies: scroll when the text arrives or grows
  useEffect(() => {
    const element = scrollRef.current;
    if (!element) return;
    if (marked !== null && lines.length > marked && !pinned.current) {
      scrollTo(marked);
      return;
    }
    if (live && pinned.current) element.scrollTop = element.scrollHeight;
  }, [lines.length, live]);
  useEffect(() => {
    if (marked !== null) scrollTo(marked);
  }, [marked, scrollTo]);

  const onScroll = (): void => {
    const element = scrollRef.current;
    if (element)
      pinned.current = element.scrollHeight - element.scrollTop - element.clientHeight < ROW;
  };
  const go = (targets: readonly number[], direction: 1 | -1): void => {
    const next = stepTo(targets, marked, direction);
    if (next !== null) setMarked(next);
  };
  const onFindKey = (event: KeyboardEvent<HTMLInputElement>): void => {
    if (event.key === "Enter") {
      event.preventDefault();
      go(found, event.shiftKey ? -1 : 1);
    } else if (event.key === "Escape" && query) {
      event.stopPropagation();
      setQuery("");
    }
  };
  const download = (): void => {
    if (!text) return;
    const url = URL.createObjectURL(new Blob([text], { type: "text/plain" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${execution?.executionId ?? "attempt"}-${logFileOf(stream)}`;
    anchor.click();
    URL.revokeObjectURL(url);
  };
  const stopsText = [
    errors > 0 ? `${errors} ${errors === 1 ? "error" : "errors"}` : null,
    warnings > 0 ? `${warnings} ${warnings === 1 ? "warning" : "warnings"}` : null,
  ]
    .filter(Boolean)
    .join(" · ");
  const findText = query.trim()
    ? found.length === 0
      ? "No results"
      : `${marked !== null && matchSet.has(marked) ? found.indexOf(marked) + 1 : "?"} of ${found.length}`
    : null;

  return (
    <div className="flex h-full min-h-0 flex-1 flex-col overflow-hidden bg-background text-foreground">
      <div className="flex h-8 shrink-0 items-center gap-3 border-b border-border px-6">
        <StreamSwitch
          stream={stream}
          onChange={(next) => {
            setStream(next);
            setMarked(null);
            pinned.current = true;
          }}
        />
        <label className="flex h-6 w-56 items-center gap-1 rounded-hairline border border-border bg-background px-2 focus-within:border-ring">
          <Search aria-hidden className="size-icon-sm shrink-0 text-muted-foreground" />
          <input
            type="search"
            aria-label="Find in log"
            placeholder="Find in log"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={onFindKey}
            className="min-w-0 flex-1 bg-transparent text-label text-foreground outline-none placeholder:text-muted-foreground"
          />
        </label>
        {findText ? (
          <span className="text-label tabular-nums text-muted-foreground">{findText}</span>
        ) : null}
        <span className="ml-auto text-label text-muted-foreground">{stopsText}</span>
        <WorkbenchIconAction
          label="Previous error or warning"
          disabled={stops.length === 0}
          onClick={() => go(stops, -1)}
        >
          <ChevronUp aria-hidden className="size-icon" />
        </WorkbenchIconAction>
        <WorkbenchIconAction
          label="Next error or warning"
          disabled={stops.length === 0}
          onClick={() => go(stops, 1)}
        >
          <ChevronDown aria-hidden className="size-icon" />
        </WorkbenchIconAction>
        <WorkbenchIconAction
          label={`Download ${logFileOf(stream)}`}
          disabled={!text}
          onClick={download}
        >
          <Download aria-hidden className="size-icon" />
        </WorkbenchIconAction>
      </div>
      {log.data?.truncated ? (
        <p className="shrink-0 border-b border-border px-6 py-1 text-label text-muted-foreground">
          Showing the last 2 MB; line numbers count from there.
          {onOpenFile ? (
            <>
              {" "}
              <button
                type="button"
                className="text-accent hover:underline"
                onClick={() => onOpenFile(logFileOf(stream))}
              >
                Open {logFileOf(stream)}
              </button>
            </>
          ) : null}
        </p>
      ) : null}
      {!execution ? (
        <p className="px-6 py-4 text-body text-muted-foreground">No attempt yet.</p>
      ) : log.error ? (
        <p role="alert" className="px-6 py-4 text-body text-status-failed-foreground">
          {log.error instanceof Error ? log.error.message : "Failed to load logs"}
        </p>
      ) : !log.data ? (
        <p className="px-6 py-4 text-body italic text-muted-foreground">Loading logs…</p>
      ) : lines.length === 0 ? (
        <p className="px-6 py-4 text-body italic text-muted-foreground">
          Nothing in {STREAM_LABEL[stream]}.
        </p>
      ) : (
        <LogLines
          lines={lines}
          kinds={kinds}
          marked={marked}
          matches={matchSet}
          query={query}
          scrollRef={scrollRef}
          onScroll={onScroll}
        />
      )}
    </div>
  );
};

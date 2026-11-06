/**
 * RunLogsPanel — one attempt's logs: `stdout`, `stderr` and the attempt's own
 * `run.log`, one stream at a time. Renders the header strip (stream switch,
 * attempt label, "view latest") and the scrolling log body; the caller owns
 * the outer container so each viewer can host it in its own layout.
 *
 * Given an `execution`, each stream is followed incrementally through
 * `useExecutionLog` (`…/logs/{stream}?offset=`). A caller that holds only
 * whole-file `{stdout, stderr}` passes `logs` instead and gets those two.
 */

import { RotateCcw, Terminal } from "lucide-react";
import { type JSX, type Ref, useEffect, useRef, useState } from "react";
import {
  type ExecutionLogCoords,
  LOG_STREAMS,
  type LogStream,
  logFileOf,
  useExecutionLog,
} from "@/app/state/executionLog";
import { WorkbenchIconAction } from "@/components/workbench";
import { cn } from "@/lib/utils";

interface RunLogsPanelProps {
  /**
   * The attempt to follow; `null` when the run has none to show. Leave it
   * out to render the whole-file `logs` instead.
   */
  execution?: ExecutionLogCoords | null;
  /** The attempt is active: follow its logs as they grow. */
  live?: boolean;
  /** Whole-file logs, for a caller with no execution route. */
  logs?: { stdout?: string | null; stderr?: string | null } | null;
  logsError?: string | null;
  selectedExecutionId: string | null;
  /** Caption shown after the stream switch (e.g. "latest attempt (#2)"). */
  attemptLabel: string;
  onViewLatest: () => void;
  /** Open one of the attempt's files (attempt-relative path) in the file view. */
  onOpenFile?: (path: string) => void;
  /** The stream shown first. */
  defaultStream?: LogStream;
}

/** What the body shows for one stream. */
export interface LogBody {
  text: string | null;
  error: string | null;
  truncated: boolean;
}

const errorText = (error: unknown): string | null =>
  error ? (error instanceof Error ? error.message : "Failed to load logs") : null;

/** The whole-file fallback: two streams, no `run`. */
const FALLBACK_STREAMS: readonly LogStream[] = ["stdout", "stderr"];

const StreamSwitch = ({
  streams,
  stream,
  onChange,
}: {
  streams: readonly LogStream[];
  stream: LogStream;
  onChange: (next: LogStream) => void;
}): JSX.Element => (
  <fieldset aria-label="Log stream" className="flex items-center gap-hairline">
    {streams.map((item) => (
      <button
        key={item}
        type="button"
        aria-pressed={item === stream}
        onClick={() => onChange(item)}
        className={cn(
          "rounded-control px-2 py-hairline font-mono text-micro text-muted-foreground",
          "hover:bg-interactive/50 hover:text-foreground",
          "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
          item === stream && "bg-interactive text-foreground",
        )}
      >
        {item}
      </button>
    ))}
  </fieldset>
);

/**
 * Pin the view to the bottom while the log grows, unless the reader has
 * scrolled up — then leave them where they are until they scroll back down.
 */
const useStickToBottom = (text: string | null, follow: boolean) => {
  const ref = useRef<HTMLDivElement | null>(null);
  const pinned = useRef(true);
  useEffect(() => {
    void text;
    const el = ref.current;
    if (el && follow && pinned.current) el.scrollTop = el.scrollHeight;
  }, [text, follow]);
  const onScroll = (): void => {
    const el = ref.current;
    if (el) pinned.current = el.scrollHeight - el.scrollTop - el.clientHeight < 24;
  };
  return { ref, onScroll };
};

export const RunLogsPanel = ({
  execution,
  live = false,
  logs = null,
  logsError = null,
  selectedExecutionId,
  attemptLabel,
  onViewLatest,
  onOpenFile,
  defaultStream = "stdout",
}: RunLogsPanelProps): JSX.Element => {
  const followed = execution !== undefined;
  const streams = followed ? LOG_STREAMS : FALLBACK_STREAMS;
  const [picked, setPicked] = useState<LogStream>(defaultStream);
  const stream = streams.includes(picked) ? picked : streams[0];
  const log = useExecutionLog(
    execution?.projectId ?? "",
    execution?.experimentId ?? "",
    execution?.runId ?? "",
    execution?.executionId ?? "",
    stream,
    { live, enabled: Boolean(execution) },
  );

  const body: LogBody | null = followed
    ? !execution
      ? { text: null, error: null, truncated: false }
      : log.data
        ? { text: log.data.text, error: null, truncated: log.data.truncated }
        : log.error
          ? { text: null, error: errorText(log.error), truncated: false }
          : null
    : logsError
      ? { text: null, error: logsError, truncated: false }
      : logs
        ? { text: stream === "run" ? null : (logs[stream] ?? null), error: null, truncated: false }
        : null;

  const { ref, onScroll } = useStickToBottom(body?.text ?? null, live);

  return (
    <>
      <div className="flex items-center justify-between gap-2 border-b border-border bg-muted/40 px-3 py-1 font-mono text-micro text-muted-foreground">
        <div className="flex min-w-0 items-center gap-2">
          <Terminal className="h-3 w-3 shrink-0" />
          <StreamSwitch streams={streams} stream={stream} onChange={setPicked} />
          <span className="text-muted-foreground/60">·</span>
          <span className="truncate text-foreground">{attemptLabel}</span>
        </div>
        {selectedExecutionId && (
          <WorkbenchIconAction
            label="View latest execution logs"
            className="size-6 text-muted-foreground"
            onClick={onViewLatest}
          >
            <RotateCcw className="size-3" />
          </WorkbenchIconAction>
        )}
      </div>
      <RunLogsBody
        stream={stream}
        body={body}
        scrollRef={ref}
        onScroll={onScroll}
        onOpenFile={onOpenFile}
      />
    </>
  );
};

/** The scrolling body for one stream: its text, or why there is none. */
export const RunLogsBody = ({
  stream,
  body,
  scrollRef,
  onScroll,
  onOpenFile,
}: {
  stream: LogStream;
  body: LogBody | null;
  scrollRef?: Ref<HTMLDivElement>;
  onScroll?: () => void;
  onOpenFile?: (path: string) => void;
}): JSX.Element => (
  <div
    ref={scrollRef}
    onScroll={onScroll}
    data-stream={stream}
    className="flex-1 overflow-auto bg-muted/20 p-3 font-mono text-label"
  >
    {body === null ? (
      <div className="italic text-muted-foreground">Loading logs...</div>
    ) : body.error ? (
      <div className="text-destructive">{body.error}</div>
    ) : body.text ? (
      <>
        {body.truncated ? (
          <p className="mb-2 font-sans text-micro text-muted-foreground">
            Showing the last 2 MB
            {onOpenFile ? (
              <>
                {" — "}
                <button
                  type="button"
                  className="underline underline-offset-2 hover:text-foreground"
                  onClick={() => onOpenFile(logFileOf(stream))}
                >
                  open {logFileOf(stream)}
                </button>
              </>
            ) : null}
            .
          </p>
        ) : null}
        <pre
          className={cn(
            "whitespace-pre-wrap",
            stream === "stderr" ? "text-destructive/90" : "text-foreground",
          )}
        >
          {body.text}
        </pre>
      </>
    ) : (
      <div className="italic text-muted-foreground">No {stream} captured.</div>
    )}
  </div>
);

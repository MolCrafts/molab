import { describe, expect, it } from "@rstest/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { RunLogsPanel } from "@/app/renderers/RunLogsPanel";
import { runKeys } from "@/app/state/entityQueries";
import type { ExecutionLogData, LogStream } from "@/app/state/executionLog";

const coords = { projectId: "p", experimentId: "x", runId: "r", executionId: "e01" };

const logData = (text: string, truncated = false): ExecutionLogData => ({
  text,
  nextOffset: text.length,
  size: text.length,
  eof: true,
  truncated,
  readWhileLive: false,
});

/** Render with each stream's log already in the cache, as a finished read leaves it. */
const renderFollowed = (
  logs: Partial<Record<LogStream, ExecutionLogData>>,
  props: { defaultStream?: LogStream; onOpenFile?: (path: string) => void; line?: number } = {},
): string => {
  const client = new QueryClient();
  for (const [stream, data] of Object.entries(logs)) {
    client.setQueryData(runKeys.log("p", "x", "r", "e01", stream as LogStream), data);
  }
  const wrap = (node: ReactNode) => (
    <QueryClientProvider client={client}>{node}</QueryClientProvider>
  );
  return renderToStaticMarkup(wrap(<RunLogsPanel execution={coords} {...props} />));
};

const pressed = (html: string): string[] =>
  [...html.matchAll(/<button[^>]*aria-pressed="true"[^>]*>([^<]+)<\/button>/g)].map(
    (match) => match[1],
  );

describe("RunLogsPanel", () => {
  it("offers stdout, stderr and run.log, opening on run.log", () => {
    const logs = {
      stdout: logData("epoch 1\n"),
      stderr: logData("warning: drift\n"),
      run: logData("attempt started\n"),
    };
    const run = renderFollowed(logs);
    expect(run).toContain(">stdout</button>");
    expect(run).toContain(">stderr</button>");
    expect(pressed(run)).toEqual(["run.log"]);
    expect(run).toContain("attempt started");
    expect(run).not.toContain("epoch 1");

    const stderr = renderFollowed(logs, { defaultStream: "stderr" });
    expect(pressed(stderr)).toEqual(["stderr"]);
    expect(stderr).toContain("warning: drift");
  });

  it("numbers lines, colours errors and warnings, and counts the stops", () => {
    const text = [
      "step 1",
      "WARNING: energy drift above threshold",
      "Traceback (most recent call last):",
      '  File "md.py", line 3',
      "NumericalInstability: drift exceeded",
    ].join("\n");
    const html = renderFollowed({ run: logData(text) });
    expect(html).toContain('data-line="5"');
    expect(html).toContain("1 error · 1 warning");
    expect(html).toMatch(/text-status-warning-foreground[^"]*">WARNING/);
    expect(html).toMatch(/text-status-failed-foreground[^"]*">NumericalInstability/);
  });

  it("marks the line it was opened at", () => {
    const html = renderFollowed({ run: logData("a\nb\nc\n") }, { line: 2 });
    expect(html).toMatch(/data-line="2" class="[^"]*bg-status-failed-soft/);
  });

  it("says when a stream captured nothing", () => {
    const empty = { stdout: logData(""), stderr: logData(""), run: logData("") };
    expect(renderFollowed(empty, { defaultStream: "stdout" })).toContain("Nothing in stdout.");
    expect(renderFollowed(empty)).toContain("Nothing in run.log.");
  });

  it("shows a loading state before the first read lands", () => {
    expect(renderFollowed({})).toContain("Loading logs…");
  });

  it("links the file when the head of a long log was dropped", () => {
    const html = renderFollowed(
      { run: logData("tail line\n", true) },
      { onOpenFile: () => undefined },
    );
    expect(html).toContain("Showing the last 2 MB");
    expect(html).toContain("Open run.log");
    expect(html).toContain("tail line");
  });
});

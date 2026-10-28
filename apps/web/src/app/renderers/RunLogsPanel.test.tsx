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
  props: { defaultStream?: LogStream; onOpenFile?: (path: string) => void } = {},
): string => {
  const client = new QueryClient();
  for (const [stream, data] of Object.entries(logs)) {
    client.setQueryData(runKeys.log("p", "x", "r", "e01", stream as LogStream), data);
  }
  const wrap = (node: ReactNode) => (
    <QueryClientProvider client={client}>{node}</QueryClientProvider>
  );
  return renderToStaticMarkup(
    wrap(
      <RunLogsPanel
        execution={coords}
        selectedExecutionId="e01"
        attemptLabel="e01 (#1) · latest"
        onViewLatest={() => undefined}
        {...props}
      />,
    ),
  );
};

const pressed = (html: string): string[] =>
  [...html.matchAll(/<button[^>]*aria-pressed="true"[^>]*>([^<]+)<\/button>/g)].map(
    (match) => match[1],
  );

describe("RunLogsPanel", () => {
  it("offers stdout, stderr and run, and shows the selected stream's text", () => {
    const logs = {
      stdout: logData("epoch 1\n"),
      stderr: logData("warning: drift\n"),
      run: logData("attempt started\n"),
    };
    const stdout = renderFollowed(logs);
    expect(stdout).toContain(">stdout</button>");
    expect(stdout).toContain(">stderr</button>");
    expect(stdout).toContain(">run</button>");
    expect(pressed(stdout)).toEqual(["stdout"]);
    expect(stdout).toContain("epoch 1");
    expect(stdout).not.toContain("warning: drift");
    expect(stdout).toContain("e01 (#1) · latest");

    const stderr = renderFollowed(logs, { defaultStream: "stderr" });
    expect(pressed(stderr)).toEqual(["stderr"]);
    expect(stderr).toContain("warning: drift");
    expect(stderr).not.toContain("epoch 1");
    // stderr keeps its destructive tint.
    expect(stderr).toMatch(/<pre class="[^"]*text-destructive\/90[^"]*">warning: drift/);

    const run = renderFollowed(logs, { defaultStream: "run" });
    expect(pressed(run)).toEqual(["run"]);
    expect(run).toContain("attempt started");
  });

  it("says when a stream captured nothing", () => {
    const empty = { stdout: logData(""), stderr: logData(""), run: logData("") };
    expect(renderFollowed(empty)).toContain("No stdout captured.");
    expect(renderFollowed(empty, { defaultStream: "stderr" })).toContain("No stderr captured.");
    expect(renderFollowed(empty, { defaultStream: "run" })).toContain("No run captured.");
  });

  it("shows a loading state before the first read lands", () => {
    expect(renderFollowed({})).toContain("Loading logs...");
  });

  it("links the file when the head of a long log was dropped", () => {
    const html = renderFollowed(
      { stdout: logData("tail line\n", true) },
      { onOpenFile: () => undefined },
    );
    expect(html).toContain("Showing the last 2 MB");
    expect(html).toContain("open stdout.log");
    expect(html).toContain("tail line");
  });

  it("keeps a whole-file prop path for a caller with no execution route", () => {
    const client = new QueryClient();
    const html = renderToStaticMarkup(
      <QueryClientProvider client={client}>
        <RunLogsPanel
          logs={{ stdout: "printed", stderr: null }}
          logsError={null}
          selectedExecutionId={null}
          attemptLabel="latest"
          onViewLatest={() => undefined}
        />
      </QueryClientProvider>,
    );
    expect(html).toContain("printed");
    expect(html).toContain(">stdout</button>");
    expect(html).not.toContain(">run</button>");
    const stderr = renderToStaticMarkup(
      <QueryClientProvider client={client}>
        <RunLogsPanel
          logs={{ stdout: "printed", stderr: null }}
          selectedExecutionId={null}
          attemptLabel="latest"
          onViewLatest={() => undefined}
          defaultStream="stderr"
        />
      </QueryClientProvider>,
    );
    expect(stderr).toContain("No stderr captured.");
    // Nothing is fetched on this path.
    expect(client.getQueryCache().findAll({ fetchStatus: "fetching" })).toHaveLength(0);
  });
});

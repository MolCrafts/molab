/**
 * Polling contract.
 *
 * Every periodic refresh must be a query's `refetchInterval` (which the shared
 * client pauses on hidden tabs) and every server push must arrive on the one
 * workspace change stream. Hand-rolled `setInterval` loops and stray
 * `EventSource`s are what made the app hammer the backend from background tabs,
 * so they are banned here rather than re-reviewed each time.
 */

import { readdirSync, readFileSync } from "node:fs";
import { dirname, extname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "@rstest/core";

const here = dirname(fileURLToPath(import.meta.url));
const srcRoot = resolve(here, "../../../..");
const appRoot = resolve(srcRoot, "app");

const walkSource = (directory: string): string[] =>
  readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) return walkSource(path);
    if (![".ts", ".tsx"].includes(extname(entry.name))) return [];
    if (entry.name.includes(".test.") || entry.name.includes(".spec.")) return [];
    return [path];
  });

const rel = (path: string): string => relative(srcRoot, path).replace(/\\/g, "/");

/**
 * The only modules allowed to construct an `EventSource`.
 *
 * `changeStream` is the workspace push channel; `queries/agent` holds the one
 * ref-counted approvals connection (until the server republishes approval
 * changes on the workspace bus); `api.ts` exposes the per-session agent
 * transcript stream, which is a genuine long-lived stream, not polling.
 */
const EVENT_SOURCE_ALLOWLIST = new Set([
  "app/state/queries/changeStream.ts",
  "app/state/queries/agent.ts",
  "app/state/api.ts",
]);

/**
 * `setInterval` is allowed only where the timer drives rendering, not fetching.
 * `useVisibleInterval` is the shared primitive; it pauses on hidden tabs.
 */
const SET_INTERVAL_ALLOWLIST = new Set([
  "app/state/queries/useVisibleInterval.ts",
  // Render-only clock ticks (elapsed-time labels), already visibility-gated
  // through useVisibleInterval or local to a chart's animation frame.
  "app/runs/RunsGanttChart.tsx",
  // Not a network poll: watches `popup.closed` on the OAuth window, for which
  // the browser fires no event. Bounded and cleaned up on settle.
  "app/renderers/agent_settings/McpServersTab.tsx",
]);

describe("polling contract", () => {
  const files = walkSource(appRoot);

  it("finds app sources to scan", () => {
    expect(files.length).toBeGreaterThan(50);
  });

  it("constructs EventSource only in the stream modules", () => {
    const offenders = files
      .filter((path) => /new\s+EventSource\s*\(/.test(readFileSync(path, "utf8")))
      .map(rel)
      .filter((path) => !EVENT_SOURCE_ALLOWLIST.has(path));

    expect(offenders).toEqual([]);
  });

  it("has no hand-rolled setInterval outside the visibility-gated primitive", () => {
    const offenders = files
      .filter((path) => /\bsetInterval\s*\(/.test(readFileSync(path, "utf8")))
      .map(rel)
      .filter((path) => !SET_INTERVAL_ALLOWLIST.has(path));

    expect(offenders).toEqual([]);
  });

  it("keeps the agent viewer free of self-rescheduling timers", () => {
    // A `setTimeout` chain that reschedules itself cannot be cleaned up on
    // unmount; the previous one kept firing (and calling setState) for 24s
    // after the user navigated away.
    const source = readFileSync(resolve(appRoot, "renderers/AgentViewer.tsx"), "utf8");
    expect(source).not.toMatch(/setTimeout\s*\(\s*tick/);
    expect(source).not.toMatch(/\bsetInterval\s*\(/);
  });

  it("does not refresh the whole workspace when an agent task is opened", () => {
    const source = readFileSync(resolve(appRoot, "renderers/AgentViewer.tsx"), "utf8");
    // The session-load effect must not call the global refresh: opening a task
    // reads a task, it does not change the workspace.
    const loadEffect = source.slice(
      source.indexOf("Load session when the selected task changes"),
      source.indexOf("Live statuses that should keep an event stream open"),
    );
    expect(loadEffect.length).toBeGreaterThan(0);
    expect(loadEffect).not.toMatch(/onRefresh\s*\(\s*\)/);
  });
});

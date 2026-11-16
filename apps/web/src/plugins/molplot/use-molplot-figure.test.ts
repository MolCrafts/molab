import type { RunAttempt } from "@molcrafts/molab-plugin";
import { describe, expect, it } from "@rstest/core";
import { PALETTE } from "./scalar-series";
import { figureState, viewFiles } from "./use-molplot-figure";

const attempt: RunAttempt = {
  projectId: "p",
  experimentId: "x",
  runId: "r",
  executionId: "e02",
  status: "succeeded",
  isLatest: true,
  isRunResult: true,
  dir: null,
};

const FILES = [
  { name: "lammps-0.out", relPath: "jobs/lammps-0.out", type: "file", size: 10 },
  { name: "log.lammps", relPath: "out/log.lammps", type: "file", size: 1_200_000 },
  { name: "energy.mlp.vl.json", relPath: "out/energy.mlp.vl.json", type: "file", size: 2048 },
];

const source = (path: string, error?: string) => ({
  path,
  format: "f",
  label: "f",
  revision: 1,
  tailable: false,
  records: [],
  ...(error ? { error } : {}),
});

describe("viewFiles", () => {
  it("lists every matched file before the read, figures last", () => {
    expect(viewFiles(FILES, undefined).map((file) => file.label)).toEqual([
      "lammps-0.out",
      "log.lammps",
      "energy.mlp.vl.json",
    ]);
  });

  it("after the read, keeps the sources a reader took, with colours and sizes", () => {
    const files = viewFiles(FILES, { sources: [source("out/log.lammps")], records: [] });
    expect(files.map((file) => [file.path, file.color, file.size, file.figure])).toEqual([
      ["out/log.lammps", PALETTE[0], 1_200_000, false],
      ["out/energy.mlp.vl.json", PALETTE[1], 2048, true],
    ]);
  });

  it("marks a file its reader failed on", () => {
    const [file] = viewFiles(FILES, { sources: [source("out/log.lammps", "bad")], records: [] });
    expect(file.error).toBe("bad");
  });
});

const base = {
  attempt,
  pending: false,
  error: null,
  read: { sources: [source("out/log.lammps")], records: [] },
  allSeries: 3,
  figures: 0,
  drawn: 3,
  task: null,
  retry: () => undefined,
};

describe("figureState", () => {
  it("is loading while the read is pending", () => {
    expect(figureState({ ...base, pending: true })).toEqual({ kind: "loading" });
  });

  it("fails with the reader's message and a retry when nothing could be read", () => {
    const state = figureState({
      ...base,
      read: { sources: [source("out/log.lammps", "no WASM reader")], records: [] },
      allSeries: 0,
    });
    expect(state).toMatchObject({
      kind: "error",
      title: "MolPlot could not read e02",
      detail: "no WASM reader",
    });
  });

  it("names the attempt when it has nothing to show", () => {
    expect(figureState({ ...base, allSeries: 0, drawn: 0 })).toEqual({
      kind: "empty",
      title: "No metrics in e02",
    });
  });

  it("explains an empty figure from unchecked files or a task", () => {
    expect(figureState({ ...base, drawn: 0 })).toMatchObject({ title: "Nothing checked" });
    expect(figureState({ ...base, drawn: 0, task: "md" })).toMatchObject({
      title: "No metrics from md",
    });
  });

  it("is null when there is a figure", () => {
    expect(figureState(base)).toBeNull();
  });
});

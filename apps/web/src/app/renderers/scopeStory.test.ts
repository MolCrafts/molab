import { describe, expect, it } from "@rstest/core";
import { outcomeByGroup, PROJECTS, runsHref, scopeVerdict } from "./scopeStory";

const experiments = [
  { id: "bench", name: "Integrator Benchmark" },
  { id: "thermo", name: "Thermostat Validation" },
];

const run = (id: string, status: string, timestep: number, groupId = "bench") => ({
  id,
  status,
  groupId,
  parameters: { driver: "ase", timestep_fs: timestep },
});

describe("scope story", () => {
  it("says an empty scope has no children, in the scope's own noun", () => {
    const verdict = scopeVerdict([], []);
    expect([verdict.word, verdict.subject]).toEqual(["Empty", "No experiments yet"]);
    expect(scopeVerdict([], [], PROJECTS).subject).toBe("No projects yet");
  });

  it("says a project with experiments but no runs has no runs", () => {
    expect(scopeVerdict([], experiments).subject).toBe("No runs yet");
  });

  it("names the one group the failing runs sit in and the values they share", () => {
    const runs = [
      run("a", "succeeded", 0.5),
      run("b", "succeeded", 1),
      { ...run("c", "failed", 2), errorMessage: "Energy drift exceeded the tolerance\ntrace" },
      run("d", "interrupted", 2),
      run("e", "running", 1),
    ];
    const verdict = scopeVerdict(runs, experiments);
    expect(verdict.word).toBe("Failed");
    expect(verdict.subject).toBe("1 failed · 1 interrupted of 5 runs");
    expect(verdict.aside).toBe("1 active");
    expect(verdict.evidence).toBe(
      "Both in Integrator Benchmark, at timestep_fs = 2 fs · Energy drift exceeded the tolerance",
    );
  });

  it("counts each group when the failures are spread across them, busiest first", () => {
    const projects = [
      { id: "nve", name: "NVE Drift" },
      { id: "pf", name: "Protein Folding" },
    ];
    const runs = [
      run("a", "failed", 1, "pf"),
      run("b", "failed", 1, "nve"),
      run("c", "interrupted", 2, "nve"),
      run("d", "succeeded", 2, "nve"),
    ];
    expect(scopeVerdict(runs, projects, PROJECTS).evidence).toBe(
      "In 2 projects · NVE Drift 2 · Protein Folding 1",
    );
  });

  it("groups the latest status of each run, skipping groups with none", () => {
    const groups = outcomeByGroup([run("a", "failed", 1), run("b", "succeeded", 2)], experiments);
    expect(groups.map((group) => [group.label, group.counts.total, group.counts.failed])).toEqual([
      ["Integrator Benchmark", 2, 1],
    ]);
  });

  it("opens the runs with the verdict's statuses, scoped when asked", () => {
    expect(runsHref("status:failed,interrupted", "nve")).toBe(
      "/runs?projectId=nve&status=failed%2Cinterrupted",
    );
    expect(runsHref("status:running,queued")).toBe("/runs?status=running%2Cqueued");
    expect(runsHref("timestep_fs:2", "nve")).toBe("/runs?projectId=nve");
    expect(runsHref()).toBe("/runs");
  });
});

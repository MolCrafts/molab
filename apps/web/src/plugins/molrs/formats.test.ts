import { describe, expect, it } from "@rstest/core";
import type { ThermoTable } from "@/lib/molrs";
import { thermoRecords, walRecords } from "./formats";

const table: ThermoTable = {
  runIndex: 0,
  columns: ["Step", "Temp", "Density"],
  rows: [
    [0, 300, 1.05],
    [1000, 310, 1.04],
    [2000, 320, 1.03],
    [3000, 330, 1.02],
  ],
};

describe("thermoRecords", () => {
  it("emits one record per value column, carrying the step", () => {
    const records = thermoRecords([table], {}, "out/log.lammps");
    expect(records).toHaveLength(8);
    const temps = records.filter((r) => r.k === "lammps/Temp");
    expect(temps.map((r) => r.s)).toEqual([0, 1000, 2000, 3000]);
    expect(temps.map((r) => r.v)).toEqual([300, 310, 320, 330]);
  });

  it("never makes Step a series of its own", () => {
    const keys = new Set(thermoRecords([table], {}, "x").map((r) => r.k));
    expect(keys).toEqual(new Set(["lammps/Temp", "lammps/Density"]));
  });

  it("does not invent a wall clock the solver never recorded", () => {
    for (const record of thermoRecords([table], {}, "x")) {
      expect(record.w).toBeUndefined();
      expect(record.tags?.wall_time_source).toBe("read");
    }
  });

  it("thins by simulation step, keeping every curve", () => {
    const records = thermoRecords([table], { stepInterval: 2000 }, "x");
    expect(new Set(records.map((r) => r.k)).size).toBe(2);
    expect(records.filter((r) => r.k === "lammps/Temp").map((r) => r.s)).toEqual([0, 2000]);
  });

  it("samples uniformly in step even when the write frequency changes", () => {
    // A restart block that writes ten times more often must not be drawn ten
    // times denser — which is exactly what row-index striding would do.
    const dense = {
      runIndex: 1,
      columns: ["Step", "Temp"],
      rows: [
        [4000, 1],
        [4100, 2],
        [4200, 3],
        [4300, 4],
        [4400, 5],
        [6000, 6],
      ],
    };
    const steps = thermoRecords([dense], { stepInterval: 2000 }, "x").map((r) => r.s);
    expect(steps).toEqual([4000, 6000]);
  });

  it("keeps run blocks apart so a restart is not spliced onto its predecessor", () => {
    const second: ThermoTable = { ...table, runIndex: 3, rows: [[9000, 40, 1.2]] };
    const records = thermoRecords([table, second], {}, "x");
    expect(new Set(records.map((r) => r.tags?.run_index))).toEqual(new Set([0, 3]));
  });

  it("honours the viewer's key filter and limit", () => {
    expect(
      thermoRecords([table], { keys: ["lammps/Density"] }, "x").every(
        (r) => r.k === "lammps/Density",
      ),
    ).toBe(true);
    expect(thermoRecords([table], { limit: 3 }, "x")).toHaveLength(3);
  });
});

describe("walRecords", () => {
  const wal = [0, 1, 2, 3, 4, 5]
    .flatMap((step) => ["energy", "temp"].map((k) => JSON.stringify({ t: "scalar", k, v: step })))
    .join("\n");

  it("passes records through and tags their source", () => {
    const records = walRecords(wal, {}, "out/metrics.mlp.jsonl");
    expect(records).toHaveLength(12);
    expect(records.every((r) => r.tags?.source === "out/metrics.mlp.jsonl")).toBe(true);
  });

  it("thins each series on its own timeline", () => {
    // Series interleave line by line, so thinning the file rather than each
    // series would keep one key and drop the other entirely.
    const stepped = [0, 500, 1000, 1500, 2000]
      .flatMap((s) => ["energy", "temp"].map((k) => JSON.stringify({ t: "scalar", k, s, v: s })))
      .join("\n");
    const records = walRecords(stepped, { stepInterval: 1000 }, "x");
    expect(new Set(records.map((r) => r.k))).toEqual(new Set(["energy", "temp"]));
    expect(records.filter((r) => r.k === "energy").map((r) => r.s)).toEqual([0, 1000, 2000]);
  });

  it("always keeps a record that has no step", () => {
    // A one-off scalar (an atom count) is not a point on a curve; thinning it
    // away would lose the only sample there is.
    const line = JSON.stringify({ t: "scalar", k: "n_atoms", v: 7400 });
    expect(walRecords(`${line}\n${line}`, { stepInterval: 1000 }, "x")).toHaveLength(2);
  });

  it("skips a torn trailing line rather than failing", () => {
    // A live WAL is appended to while it is read; half a line is normal.
    const records = walRecords(
      `${JSON.stringify({ t: "scalar", k: "a", v: 1 })}\n{"t":"sca`,
      {},
      "x",
    );
    expect(records).toHaveLength(1);
  });

  it("does not let a reader's tag override the record's own", () => {
    const line = JSON.stringify({ t: "scalar", k: "a", v: 1, tags: { source: "original" } });
    expect(walRecords(line, {}, "x")[0].tags?.source).toBe("original");
  });
});

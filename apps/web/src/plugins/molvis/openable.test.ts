import { describe, expect, it } from "@rstest/core";

import { isMolvisOpenable, isMolvisZarr, uniqueMolvisFiles, zarrStoreRoot } from "./openable";

const file = (relPath: string) => ({
  name: relPath.split("/").pop() ?? relPath,
  relPath,
});

describe("isMolvisZarr", () => {
  it("matches a .mrec store directory", () => {
    expect(isMolvisZarr(file("growth.mrec"))).toBe(true);
  });

  it("matches a .mrec store marker", () => {
    expect(isMolvisZarr(file("growth.mrec/zarr.json"))).toBe(true);
  });

  it("does not match a packed .mrec.zip archive", () => {
    expect(isMolvisZarr(file("growth.mrec.zip"))).toBe(false);
  });

  it("does not match a bare .zarr store", () => {
    expect(isMolvisZarr(file("growth.zarr"))).toBe(false);
    expect(isMolvisZarr(file("artifacts/growth.zarr/zarr.json"))).toBe(false);
  });

  it("does not match host metrics stores", () => {
    expect(isMolvisZarr(file("metrics.mlp.zarr"))).toBe(false);
    expect(isMolvisZarr(file("metrics.mlp.zarr/zarr.json"))).toBe(false);
    expect(isMolvisZarr(file("metrics.mlp.zarr/series/n_frames/zarr.json"))).toBe(false);
  });

  it("does not match group markers without a .mrec ancestor", () => {
    expect(isMolvisZarr(file("artifacts/pkg/frame/zarr.json"))).toBe(false);
    expect(isMolvisZarr(file("artifacts/pkg/trajectory/zarr.json"))).toBe(false);
    expect(isMolvisZarr(file("artifacts/pkg/meta/zarr.json"))).toBe(false);
  });

  it("matches group markers under a .mrec store", () => {
    expect(isMolvisZarr(file("growth.mrec/frame/zarr.json"))).toBe(true);
    expect(isMolvisZarr(file("growth.mrec/trajectory/zarr.json"))).toBe(true);
    expect(isMolvisZarr(file("growth.mrec/meta/zarr.json"))).toBe(true);
  });

  it("does not match nested array metadata", () => {
    expect(isMolvisZarr(file("growth.mrec/trajectory/atoms/x/zarr.json"))).toBe(false);
  });
});

describe("zarrStoreRoot", () => {
  it("resolves a .mrec store marker to the store directory", () => {
    expect(zarrStoreRoot("foo.mrec/zarr.json")).toBe("foo.mrec");
  });

  it("resolves group markers under a .mrec store to the store directory", () => {
    expect(zarrStoreRoot("artifacts/growth.mrec/trajectory/zarr.json")).toBe(
      "artifacts/growth.mrec",
    );
    expect(zarrStoreRoot("artifacts/growth.mrec/meta/zarr.json")).toBe("artifacts/growth.mrec");
  });
});

describe("uniqueMolvisFiles", () => {
  it("collapses several group markers into one .mrec store row", () => {
    const files = uniqueMolvisFiles([
      file("artifacts/growth.mrec/trajectory/zarr.json"),
      file("artifacts/growth.mrec/meta/zarr.json"),
      file("traj.xyz"),
    ]);
    expect(files.map((f) => f.name)).toEqual(["growth.mrec", "traj.xyz"]);
    expect(files[0]?.relPath).toBe("artifacts/growth.mrec/trajectory/zarr.json");
  });

  it("still treats classic dumps as openable", () => {
    expect(isMolvisOpenable(file("dump.lammpstrj"))).toBe(true);
    expect(isMolvisOpenable(file("notes.txt"))).toBe(false);
  });

  it("leaves solver logs to molplot", () => {
    // Numbers over time are not a structure. Claiming them here would put the
    // same file behind two tabs, one of which cannot draw it.
    expect(isMolvisOpenable(file("log.lammps"))).toBe(false);
    expect(isMolvisOpenable(file("lmp.log"))).toBe(false);
  });
});

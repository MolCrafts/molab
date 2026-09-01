import { describe, expect, it } from "@rstest/core";

import type { WorkspaceDirent, WorkspaceFs } from "@/lib/workspace-fs";

import {
  collectZarrStore,
  runWorkspaceRelPath,
  scopedZarrSource,
  workspaceZarrSource,
} from "./host-zarr";

const dirent = (
  path: string,
  kind: "file" | "directory",
  children: WorkspaceDirent[] = [],
): WorkspaceDirent => ({
  name: path.split("/").pop() ?? path,
  path,
  kind,
  sizeBytes: kind === "file" ? 1 : null,
  mtime: null,
  children,
  childrenLoaded: true,
});

describe("runWorkspaceRelPath", () => {
  it("follows the run- prefix layout law", () => {
    expect(runWorkspaceRelPath("water", "md", "abcd1234")).toBe(
      "projects/water/experiments/md/runs/run-abcd1234",
    );
  });
});

describe("workspaceZarrSource", () => {
  it("lists and reads paths relative to the run directory", async () => {
    const files: Record<string, Uint8Array> = {
      "projects/p/experiments/e/runs/run-1/artifacts/pkg/zarr.json": new Uint8Array([1, 2]),
    };
    const fs: WorkspaceFs = {
      root: null,
      listdir: async (path) => {
        if (path.endsWith("artifacts/pkg")) {
          return [dirent(`${path}/zarr.json`, "file"), dirent(`${path}/frame`, "directory")];
        }
        return [];
      },
      readText: async () => {
        throw new Error("unused");
      },
      readBlob: async (path) => {
        const copy = new ArrayBuffer(files[path]?.byteLength ?? 0);
        if (files[path]) new Uint8Array(copy).set(files[path]);
        return new Blob([copy]);
      },
    };
    const source = workspaceZarrSource("projects/p/experiments/e/runs/run-1", fs);
    const listing = await source.list("artifacts/pkg");
    expect(listing.map((e) => e.name).sort()).toEqual(["frame", "zarr.json"]);
    const bytes = await source.read("artifacts/pkg/zarr.json");
    expect(Array.from(bytes)).toEqual([1, 2]);
  });

  it("scopes list/read to a store directory", async () => {
    const files: Record<string, Uint8Array> = {
      "projects/p/experiments/e/runs/run-1/artifacts/pkg/zarr.json": new Uint8Array([9]),
    };
    const fs: WorkspaceFs = {
      root: null,
      listdir: async (path) => {
        if (path.endsWith("artifacts/pkg")) {
          return [dirent(`${path}/zarr.json`, "file")];
        }
        return [];
      },
      readText: async () => {
        throw new Error("unused");
      },
      readBlob: async (path) => {
        const copy = new ArrayBuffer(files[path]?.byteLength ?? 0);
        if (files[path]) new Uint8Array(copy).set(files[path]);
        return new Blob([copy]);
      },
    };
    const source = scopedZarrSource(
      workspaceZarrSource("projects/p/experiments/e/runs/run-1", fs),
      "artifacts/pkg",
    );
    const listing = await source.list("");
    expect(listing.map((e) => e.name)).toEqual(["zarr.json"]);
    expect(Array.from(await source.read("zarr.json"))).toEqual([9]);
  });

  it("collects a scoped store as path → base64", async () => {
    const source: import("./host-zarr").ZarrDirectorySource = {
      list: async (path) => {
        if (path === "") return [{ name: "zarr.json", kind: "file" }];
        return [];
      },
      read: async () => new Uint8Array([1, 2, 3]),
    };
    const files = await collectZarrStore(source);
    expect(files["zarr.json"]).toBe(btoa(String.fromCharCode(1, 2, 3)));
  });
});

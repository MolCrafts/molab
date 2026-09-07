import { describe, expect, it } from "@rstest/core";

import type { WorkspaceDirent, WorkspaceFs } from "@/lib/workspace-fs";

import { collectZarrStore, scopedZarrSource, workspaceZarrSource } from "./host-zarr";

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

describe("what the store is rooted at", () => {
  /**
   * A discovered ``relPath`` is relative to the *attempt*, not the run.
   *
   * Rooting the source at the run directory drops the ``executions/<id>/``
   * segment, so every read resolves to a directory that does not exist and
   * molvis fails on open. The server reports the attempt's directory as
   * ``RunFilesResponse.runDir``; that is what must be passed here.
   */
  it("reads under the attempt, not the run", async () => {
    const asked: string[] = [];
    const fs: WorkspaceFs = {
      root: null,
      listdir: async (path) => {
        asked.push(path);
        return [];
      },
      readText: async () => {
        throw new Error("unused");
      },
      readBlob: async (path) => {
        asked.push(path);
        return new Blob([new ArrayBuffer(0)]);
      },
    };
    const attempt = "projects/p/experiments/e/runs/dp=5_seed=42/executions/e02";
    const source = scopedZarrSource(workspaceZarrSource(attempt, fs), "out/grow/final.mrec");

    await source.list("");
    await source.read("zarr.json");

    expect(asked).toEqual([
      `${attempt}/out/grow/final.mrec`,
      `${attempt}/out/grow/final.mrec/zarr.json`,
    ]);
    for (const path of asked) {
      expect(path).toContain("/executions/e02/");
    }
  });
});

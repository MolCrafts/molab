import { afterEach, describe, expect, it, rs } from "@rstest/core";
import { QueryClient } from "@tanstack/react-query";
import {
  artifactPreviewText,
  assetBytesQueryOptions,
  journalRefetchInterval,
  runKeys,
  structurePreviewText,
  workspaceFileBytesQueryOptions,
} from "@/app/state/entityQueries";
import { getWorkspaceQueryScope } from "../workspaceSwitchEvents";

afterEach(() => {
  rs.restoreAllMocks();
});

describe("binary preview queries", () => {
  it("preserves a workspace asset's bytes without a project or producing attempt", async () => {
    const binary = new Uint8Array([0, 255, 128, 195, 40]);
    const fetch = rs.spyOn(globalThis, "fetch").mockResolvedValue(new Response(binary));
    const client = new QueryClient();
    try {
      expect(await client.fetchQuery(assetBytesQueryOptions("", "a"))).toEqual(binary);
      expect(fetch).toHaveBeenCalledWith("/api/assets/a/download", {
        credentials: "same-origin",
      });
    } finally {
      client.clear();
    }
  });

  it("requests arbitrary workspace binary files through the download route", async () => {
    const binary = new Uint8Array([0, 255, 128, 195, 40]);
    const fetch = rs.spyOn(globalThis, "fetch").mockResolvedValue(new Response(binary));
    const client = new QueryClient();
    try {
      expect(await client.fetchQuery(workspaceFileBytesQueryOptions("out/a.dcd"))).toEqual(binary);
      expect(fetch).toHaveBeenCalledWith("/api/workspace/file/blob?path=out%2Fa.dcd&download=true");
    } finally {
      client.clear();
    }
  });

  it("reports failed binary reads instead of returning empty bytes", async () => {
    rs.spyOn(globalThis, "fetch").mockImplementation(
      async () => new Response(null, { status: 403 }),
    );
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    try {
      await expect(client.fetchQuery(assetBytesQueryOptions("p", "a"))).rejects.toThrow("403");
      await expect(client.fetchQuery(workspaceFileBytesQueryOptions("a.dcd"))).rejects.toThrow(
        "403",
      );
    } finally {
      client.clear();
    }
  });
});

describe("runKeys.journal", () => {
  it("keys one execution journal", () => {
    expect(runKeys.journal("p", "e", "r", "e01")).toEqual([
      "runs",
      getWorkspaceQueryScope(),
      "p",
      "e",
      "r",
      "e01",
      "journal",
    ]);
  });
});

describe("runKeys.artifactContent", () => {
  it("keys one artifact's bytes", () => {
    expect(runKeys.artifactContent("p", "e", "r", "e01", "a1")).toEqual([
      "runs",
      getWorkspaceQueryScope(),
      "p",
      "e",
      "r",
      "e01",
      "assets",
      "a1",
      "content",
    ]);
  });
});

describe("journalRefetchInterval", () => {
  it("polls while an attempt is queued or running", () => {
    expect(journalRefetchInterval("running")).toBe(1500);
    expect(journalRefetchInterval("queued")).toBe(1500);
    expect(journalRefetchInterval("finalizing")).toBe(1500);
  });

  it("stops for a terminal or missing status", () => {
    expect(journalRefetchInterval("failed")).toBe(false);
    expect(journalRefetchInterval(undefined)).toBe(false);
  });
});

describe("artifactPreviewText", () => {
  it("passes a string through", () => {
    expect(artifactPreviewText("abc")).toBe("abc");
  });

  it("pretty-prints an object", () => {
    expect(artifactPreviewText({ a: 1 })).toBe('{\n  "a": 1\n}');
  });

  it("turns null into an empty string", () => {
    expect(artifactPreviewText(null)).toBe("");
  });

  it("caps the preview at 300 000 characters", () => {
    expect(artifactPreviewText("x".repeat(300_001))).toHaveLength(300_000);
  });
});

describe("structurePreviewText", () => {
  it("keeps a structure that the log preview would cut", () => {
    const text = "BOND\n".repeat(80_000);
    expect(text.length).toBeGreaterThan(300_000);
    expect(structurePreviewText(text)).toBe(text);
  });

  it("refuses a structure past the whole-file limit", () => {
    expect(() => structurePreviewText("x".repeat(8_000_001))).toThrow(/preview limit/);
  });
});

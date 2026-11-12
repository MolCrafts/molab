import { afterEach, beforeEach, describe, expect, it, rs } from "@rstest/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderToStaticMarkup } from "react-dom/server";
import { AssetContent } from "@/app/assets/AssetContent";
import {
  assetBytesQueryOptions,
  assetTextQueryOptions,
  workspaceFileBytesQueryOptions,
} from "@/app/state/entityQueries";
import type { AssetSummary } from "@/app/types";
import { TextEditor } from "@/plugins/editor/TextEditor";
import { filePreviewPluginRegistry } from "./file-preview-plugins";

rs.mock("@/app/shell/useUnsavedEdits", () => ({ useUnsavedEdits: () => null }));

const asset: AssetSummary = {
  id: "a",
  name: "trajectory",
  file: "payload.dcd",
  projectId: "p",
  kind: "data",
  status: "active",
  summary: "",
  updatedAt: "2026-11-10T00:00:00Z",
  sizeBytes: 5,
};

beforeEach(() => {
  filePreviewPluginRegistry.clear();
  filePreviewPluginRegistry.register({
    id: "binary-preview",
    name: "Binary preview",
    extensions: [".dcd"],
    payload: "bytes",
    Component: ({ content, bytes }) => (
      <output>{bytes ? Array.from(bytes).join(",") : `text:${content}`}</output>
    ),
  });
});

afterEach(() => filePreviewPluginRegistry.clear());

describe("file preview hosts", () => {
  it("passes binary asset content intact to the plugin", () => {
    const client = new QueryClient();
    client.setQueryData(
      assetBytesQueryOptions("p", "a").queryKey,
      new Uint8Array([0, 255, 128, 195, 40]),
    );
    try {
      const html = renderToStaticMarkup(
        <QueryClientProvider client={client}>
          <AssetContent asset={asset} kind="data" mode="full" />
        </QueryClientProvider>,
      );
      expect(html).toContain("<output>0,255,128,195,40</output>");
    } finally {
      client.clear();
    }
  });

  it("opens a binary workspace file directly in its preview", () => {
    const client = new QueryClient();
    const path = "out/a.dcd";
    client.setQueryData(
      workspaceFileBytesQueryOptions(path).queryKey,
      new Uint8Array([0, 255, 128, 195, 40]),
    );
    try {
      const html = renderToStaticMarkup(
        <QueryClientProvider client={client}>
          <TextEditor
            selection={{
              objectType: "workspace-file",
              objectId: path,
              filePath: path,
              fileKind: "unknown",
            }}
            snapshot={{
              projects: [],
              experiments: [],
              runs: [],
              assets: [],
              workflows: [],
              workspaces: [],
            }}
            inspectorTarget={{ kind: "object", objectType: "workspace-file", objectId: path }}
            onInspectorTargetChange={() => {}}
            onRefresh={() => {}}
          />
        </QueryClientProvider>,
      );
      expect(html).toContain("<output>0,255,128,195,40</output>");
      expect(html).not.toContain("Loading editor");
      expect(html).not.toContain('aria-label="Preview to the side"');
    } finally {
      client.clear();
    }
  });

  it("keeps whole-text plugin input beyond the ordinary text cap", () => {
    filePreviewPluginRegistry.register({
      id: "whole-preview",
      name: "Whole preview",
      extensions: [".custom"],
      whole: true,
      Component: ({ content }) => <output>{content.length}</output>,
    });
    const client = new QueryClient();
    client.setQueryData(assetTextQueryOptions("p", "a", Number.MAX_SAFE_INTEGER).queryKey, {
      text: "x".repeat(300_001),
      partial: false,
    });
    try {
      const html = renderToStaticMarkup(
        <QueryClientProvider client={client}>
          <AssetContent asset={{ ...asset, file: "payload.custom" }} kind="data" mode="full" />
        </QueryClientProvider>,
      );
      expect(html).toContain("<output>300001</output>");
    } finally {
      client.clear();
    }
  });
});

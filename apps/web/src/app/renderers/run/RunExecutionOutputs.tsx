import { Archive, File, FileOutput, Folder, Terminal } from "lucide-react";
import { type JSX, useEffect, useState } from "react";
import { runsApi } from "@/api";
import type { ExecutionOutputsResponse } from "@/api/generated/models/ExecutionOutputsResponse";
import type { RunFileNode } from "@/api/generated/models/RunFileNode";
import { EmptyState } from "@/app/components/entity";
import { type TreeNode, TreeView } from "@/app/panels/TreeView";
import { WorkbenchIconAction } from "@/components/workbench";

type SelectedOutput =
  | { kind: "artifact"; id: string }
  | { kind: "file"; path: string }
  | { kind: "stdio"; name: "stdout" | "stderr" | "runtime" };

interface RunExecutionOutputsProps {
  outputs: ExecutionOutputsResponse | null;
  error: string | null;
  projectId: string;
  experimentId: string;
  runId: string;
  selectedExecutionId: string | null;
  onPromoted?: () => void;
}

const artifactUrl = (
  projectId: string,
  experimentId: string,
  runId: string,
  executionId: string,
  artifactId: string,
): string =>
  `/api/projects/${encodeURIComponent(projectId)}/experiments/${encodeURIComponent(experimentId)}/runs/${encodeURIComponent(runId)}/executions/${encodeURIComponent(executionId)}/artifacts/${encodeURIComponent(artifactId)}/content`;

const formatSize = (size: number | null | undefined): string | undefined =>
  size == null ? undefined : `${size} B`;

const buildFileTree = (rows: RunFileNode[], onSelect: (path: string) => void): TreeNode[] => {
  const roots: TreeNode[] = [];
  const dirs = new Map<string, TreeNode>();
  for (const row of rows) {
    const parts = row.relPath.split("/").filter(Boolean);
    const leaf: TreeNode = {
      id: `file:${row.relPath}`,
      label: parts[parts.length - 1] ?? row.name,
      icon: File,
      meta: formatSize(row.size),
      onSelect: () => onSelect(row.relPath),
    };
    let siblings = roots;
    let currentPath = "";
    for (let index = 0; index < parts.length - 1; index += 1) {
      currentPath = currentPath ? `${currentPath}/${parts[index]}` : parts[index];
      const dirId = `dir:${currentPath}`;
      let dir = dirs.get(dirId);
      if (!dir) {
        dir = { id: dirId, label: parts[index], icon: Folder, children: [] };
        dirs.set(dirId, dir);
        siblings.push(dir);
      }
      siblings = dir.children ?? (dir.children = []);
    }
    siblings.push(leaf);
  }
  return roots;
};

export const RunExecutionOutputs = ({
  outputs,
  error,
  projectId,
  experimentId,
  runId,
  selectedExecutionId,
  onPromoted,
}: RunExecutionOutputsProps): JSX.Element => {
  const [selected, setSelected] = useState<SelectedOutput | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);

  useEffect(() => {
    setSelected(null);
    setPreview(null);
    setPreviewError(null);
  }, [selectedExecutionId]);

  useEffect(() => {
    let cancelled = false;
    setPreview(null);
    setPreviewError(null);
    if (!selectedExecutionId || !outputs || !selected) return;

    if (selected.kind === "stdio") {
      setPreview(outputs[selected.name] ?? `No ${selected.name} captured.`);
      return;
    }
    if (selected.kind === "artifact") {
      fetch(artifactUrl(projectId, experimentId, runId, selectedExecutionId, selected.id))
        .then((response) => {
          if (!response.ok) throw new Error(`HTTP ${response.status}`);
          return response.text();
        })
        .then((value) => {
          if (!cancelled) setPreview(value.slice(0, 300_000));
        })
        .catch((reason: unknown) => {
          if (!cancelled)
            setPreviewError(reason instanceof Error ? reason.message : "Preview unavailable");
        });
      return () => {
        cancelled = true;
      };
    }
    runsApi
      .getRunFileText(projectId, experimentId, runId, selectedExecutionId, selected.path)
      .then((response) => {
        if (!cancelled) setPreview(response.content);
      })
      .catch((reason: unknown) => {
        if (!cancelled)
          setPreviewError(reason instanceof Error ? reason.message : "Preview unavailable");
      });
    return () => {
      cancelled = true;
    };
  }, [experimentId, projectId, runId, selected, selectedExecutionId, outputs]);

  if (!selectedExecutionId) {
    return (
      <div className="flex h-chart-lg items-center justify-center rounded-md border border-border bg-canvas">
        <EmptyState title="Select an execution" description="Outputs belong to one execution." />
      </div>
    );
  }
  if (error) {
    return <p className="text-label text-destructive">{error}</p>;
  }
  if (!outputs) {
    return <p className="text-label text-muted-foreground">Loading outputs…</p>;
  }

  const artifacts = outputs.artifacts ?? [];
  const files = outputs.unregistered ?? [];
  const selectedArtifact =
    selected?.kind === "artifact"
      ? (artifacts.find((item) => item.id === selected.id) ?? null)
      : null;

  const artifactNodes: TreeNode[] = artifacts.map((item) => ({
    id: `artifact:${item.id}`,
    label: item.name,
    icon: Archive,
    meta: `${item.size} B`,
    right: item.semanticType ? (
      <span className="uppercase tracking-tight text-micro text-muted-foreground">
        {item.semanticType}
      </span>
    ) : undefined,
    onSelect: () => setSelected({ kind: "artifact", id: item.id }),
  }));

  const stdioNodes: TreeNode[] = (["stdout", "stderr", "runtime"] as const).map((name) => ({
    id: `stdio:${name}`,
    label: name,
    icon: Terminal,
    onSelect: () => setSelected({ kind: "stdio", name }),
  }));

  const nodes: TreeNode[] = [
    ...(artifactNodes.length > 0
      ? [
          {
            id: "artifacts",
            label: "Artifacts",
            icon: Archive,
            children: artifactNodes,
          } satisfies TreeNode,
        ]
      : []),
    ...(files.length > 0
      ? [
          {
            id: "files",
            label: "Files",
            icon: Folder,
            children: buildFileTree(files, (path) => setSelected({ kind: "file", path })),
          } satisfies TreeNode,
        ]
      : []),
    {
      id: "stdio",
      label: "StdIO",
      icon: Terminal,
      children: stdioNodes,
    },
  ];

  const activeId = selected
    ? selected.kind === "artifact"
      ? `artifact:${selected.id}`
      : selected.kind === "file"
        ? `file:${selected.path}`
        : `stdio:${selected.name}`
    : undefined;

  return (
    <div className="grid h-chart-lg min-h-0 grid-cols-[minmax(240px,34%)_1fr] overflow-hidden rounded-md border border-border bg-canvas">
      <div className="min-h-0 overflow-auto border-r border-border p-2">
        <TreeView
          nodes={nodes}
          activeId={activeId}
          expandPath={["artifacts", "files", "stdio"]}
          emptyTitle="No outputs"
        />
      </div>
      <div className="relative min-h-0 overflow-auto">
        {selectedArtifact && (
          <div className="absolute right-2 top-2 z-10">
            <WorkbenchIconAction
              label="Promote to project asset"
              onClick={() => {
                void runsApi
                  .promoteArtifact(
                    projectId,
                    experimentId,
                    runId,
                    selectedExecutionId,
                    selectedArtifact.id,
                    { createdBy: "ui" },
                  )
                  .then(() => onPromoted?.());
              }}
            >
              <Archive className="size-icon-sm" />
            </WorkbenchIconAction>
          </div>
        )}
        <Preview value={preview} error={previewError} empty="Select an output" />
      </div>
    </div>
  );
};

const Preview = ({
  value,
  error,
  empty,
}: {
  value: string | null;
  error: string | null;
  empty: string;
}): JSX.Element => {
  if (error) return <p className="p-4 text-label text-destructive">{error}</p>;
  if (value === null) {
    return (
      <div className="flex h-full items-center justify-center text-label text-muted-foreground">
        <FileOutput className="mr-2 size-icon" />
        {empty}
      </div>
    );
  }
  return (
    <pre className="h-full overflow-auto whitespace-pre-wrap break-words p-4 font-mono text-micro leading-relaxed text-foreground">
      {value}
    </pre>
  );
};

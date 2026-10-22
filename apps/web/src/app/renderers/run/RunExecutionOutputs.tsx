import { useQuery } from "@tanstack/react-query";
import { Archive, File, FileOutput, Folder, Terminal } from "lucide-react";
import { type JSX, useEffect, useState } from "react";
import { runsApi } from "@/api";
import { ApiError } from "@/api/generated";
import type { ExecutionOutputsResponse } from "@/api/generated/models/ExecutionOutputsResponse";
import type { RunFileNode } from "@/api/generated/models/RunFileNode";
import { EmptyState } from "@/app/components/entity";
import { type TreeNode, TreeView } from "@/app/panels/TreeView";
import {
  artifactContentQueryOptions,
  runFileBlobQueryOptions,
  runFileTextQueryOptions,
} from "@/app/state/entityQueries";
import { WorkbenchIconAction } from "@/components/workbench";
import { formatBytes } from "@/lib/format-bytes";

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

const formatSize = (size: number | null | undefined): string | undefined =>
  size == null ? undefined : formatBytes(size);

/** Open each tier and its task folders (`out/<task>`) so products are one click away. */
const taskDirIds = (rows: RunFileNode[]): string[] => {
  const ids = new Set<string>();
  for (const row of rows) {
    const parts = row.relPath.split("/").filter(Boolean);
    if (parts.length > 1) ids.add(`dir:${parts[0]}`);
    if (parts.length > 2) ids.add(`dir:${parts[0]}/${parts[1]}`);
  }
  return [...ids];
};

/** Files a browser draws itself; everything else previews as text. */
type BinaryKind = "image" | "pdf";
const binaryKindOf = (path: string): BinaryKind | null => {
  const ext = path.slice(path.lastIndexOf(".") + 1).toLowerCase();
  if (["png", "jpg", "jpeg", "gif", "webp"].includes(ext)) return "image";
  if (ext === "pdf") return "pdf";
  return null;
};

/** An object URL for a blob, revoked when the blob changes or the view unmounts. */
const useObjectUrl = (blob: Blob | undefined): string | null => {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!blob) {
      setUrl(null);
      return;
    }
    const next = URL.createObjectURL(blob);
    setUrl(next);
    return () => URL.revokeObjectURL(next);
  }, [blob]);
  return url;
};

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
      if (!dir.children) dir.children = [];
      siblings = dir.children;
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
  const [picked, setPicked] = useState<{
    executionId: string;
    selected: SelectedOutput;
  } | null>(null);
  const selected =
    picked && selectedExecutionId !== null && picked.executionId === selectedExecutionId
      ? picked.selected
      : null;
  const choose = (next: SelectedOutput): void => {
    if (!selectedExecutionId) return;
    setPicked({ executionId: selectedExecutionId, selected: next });
  };

  const artifactId = selected?.kind === "artifact" ? selected.id : "";
  const filePath = selected?.kind === "file" ? selected.path : "";
  const artifactQuery = useQuery({
    ...artifactContentQueryOptions(
      projectId,
      experimentId,
      runId,
      selectedExecutionId ?? "",
      artifactId,
    ),
    enabled: selected?.kind === "artifact" && selectedExecutionId !== null,
  });
  const binaryKind = selected?.kind === "file" ? binaryKindOf(filePath) : null;
  const fileQuery = useQuery({
    ...runFileTextQueryOptions(projectId, experimentId, runId, selectedExecutionId ?? "", filePath),
    enabled: selected?.kind === "file" && binaryKind === null && selectedExecutionId !== null,
  });
  const blobQuery = useQuery({
    ...runFileBlobQueryOptions(projectId, experimentId, runId, selectedExecutionId ?? "", filePath),
    enabled: binaryKind !== null && selectedExecutionId !== null,
  });
  const blobUrl = useObjectUrl(binaryKind ? blobQuery.data : undefined);
  const fileError = binaryKind ? blobQuery.error : fileQuery.error;

  const previewError =
    selected?.kind === "artifact"
      ? artifactQuery.error instanceof ApiError && artifactQuery.error.status === 404
        ? "Artifact bytes not found for this execution."
        : artifactQuery.error instanceof Error
          ? artifactQuery.error.message
          : artifactQuery.error
            ? "Preview unavailable"
            : null
      : selected?.kind === "file"
        ? fileError instanceof Error
          ? fileError.message
          : fileError
            ? "Preview unavailable"
            : null
        : null;
  const preview =
    selected?.kind === "stdio"
      ? (outputs?.[selected.name] ?? `No ${selected.name} captured.`)
      : selected?.kind === "artifact"
        ? (artifactQuery.data ?? null)
        : selected?.kind === "file"
          ? (fileQuery.data ?? null)
          : null;

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
    meta: formatBytes(item.size),
    right: item.semanticType ? (
      <span className="uppercase tracking-tight text-micro text-muted-foreground">
        {item.semanticType}
      </span>
    ) : undefined,
    onSelect: () => choose({ kind: "artifact", id: item.id }),
  }));

  const stdioNodes: TreeNode[] = (["stdout", "stderr", "runtime"] as const).map((name) => ({
    id: `stdio:${name}`,
    label: name,
    icon: Terminal,
    onSelect: () => choose({ kind: "stdio", name }),
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
            children: buildFileTree(files, (path) => choose({ kind: "file", path })),
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
          expandPath={["artifacts", "files", "stdio", ...taskDirIds(files)]}
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
        {binaryKind && !previewError ? (
          <BinaryPreview kind={binaryKind} url={blobUrl} name={filePath} />
        ) : (
          <Preview value={preview} error={previewError} empty="Select an output" />
        )}
      </div>
    </div>
  );
};

const BinaryPreview = ({
  kind,
  url,
  name,
}: {
  kind: BinaryKind;
  url: string | null;
  name: string;
}): JSX.Element => {
  if (!url) {
    return (
      <div className="flex h-full items-center justify-center text-label text-muted-foreground">
        Loading preview…
      </div>
    );
  }
  if (kind === "pdf") {
    return <iframe title={name} src={url} className="h-full w-full border-0 bg-background" />;
  }
  return (
    <div className="flex min-h-full items-center justify-center bg-background p-4">
      <img src={url} alt={name} className="max-h-full max-w-full object-contain" />
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

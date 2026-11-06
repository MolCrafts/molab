import { useQuery } from "@tanstack/react-query";
import { Archive, File, FileOutput, Folder, Terminal } from "lucide-react";
import { type JSX, Suspense, useMemo, useState } from "react";
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
import { useContributionGeneration } from "@/lib/contribution-runtime";
import { filePreviewPluginRegistry } from "@/lib/file-preview-plugins";
import { formatBytes } from "@/lib/format-bytes";
import { isChemicalStructureName, structureRank } from "@/lib/structure-files";
import { useObjectUrl } from "@/lib/use-object-url";

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
  /** Fill the parent instead of the fixed chart height. */
  fill?: boolean;
  /**
   * Open this output until the user picks one for the current execution.
   * A later click wins, and survives switching away and back.
   */
  preferred?: SelectedOutput | null;
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
  fill = false,
  preferred = null,
}: RunExecutionOutputsProps): JSX.Element => {
  const [picked, setPicked] = useState<{
    executionId: string;
    selected: SelectedOutput;
  } | null>(null);
  const userPick =
    picked && selectedExecutionId !== null && picked.executionId === selectedExecutionId
      ? picked.selected
      : null;
  const contributionGeneration = useContributionGeneration();
  const defaultStructure = useMemo((): SelectedOutput | null => {
    if (!outputs || !selectedExecutionId) return null;
    const ranked: { rank: number; selected: SelectedOutput }[] = [];
    for (const item of outputs.assets ?? []) {
      if (!isChemicalStructureName(item.title)) continue;
      ranked.push({ rank: structureRank(item.title), selected: { kind: "artifact", id: item.id } });
    }
    for (const row of outputs.unregistered ?? []) {
      if (!isChemicalStructureName(row.name)) continue;
      ranked.push({
        rank: structureRank(row.name),
        selected: { kind: "file", path: row.relPath },
      });
    }
    ranked.sort((left, right) => left.rank - right.rank);
    return ranked[0]?.selected ?? null;
  }, [outputs, selectedExecutionId]);
  const selected =
    userPick ?? (selectedExecutionId !== null ? (preferred ?? defaultStructure) : null);
  const frameClass = fill ? "h-full min-h-0" : "h-chart-lg";
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
        ? "Asset bytes not found for this execution."
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
  const previewName =
    selected?.kind === "artifact"
      ? (outputs?.assets?.find((item) => item.id === selected.id)?.title ?? "")
      : selected?.kind === "file"
        ? (selected.path.split("/").pop() ?? selected.path)
        : "";
  const structurePlugin = useMemo(() => {
    void contributionGeneration;
    if (!previewName || !isChemicalStructureName(previewName)) return null;
    return filePreviewPluginRegistry.getPluginForFile(previewName, previewName);
  }, [contributionGeneration, previewName]);

  if (!selectedExecutionId) {
    return (
      <div
        className={`flex ${frameClass} items-center justify-center rounded-md border border-border bg-canvas`}
      >
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

  const registered = outputs.assets ?? [];
  const files = outputs.unregistered ?? [];

  const assetNodes: TreeNode[] = registered.map((item) => ({
    id: `artifact:${item.id}`,
    label: item.title,
    icon: Archive,
    meta: formatBytes(item.size),
    right: item.mediaType ? (
      <span className="uppercase tracking-tight text-micro text-muted-foreground">
        {item.mediaType}
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
    ...(assetNodes.length > 0
      ? [
          {
            id: "assets",
            label: "Assets",
            icon: Archive,
            children: assetNodes,
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
    <div
      className={`grid ${frameClass} min-h-0 grid-cols-[minmax(240px,34%)_1fr] overflow-hidden rounded-md border border-border bg-canvas`}
    >
      <div className="min-h-0 overflow-auto border-r border-border p-2">
        <TreeView
          nodes={nodes}
          activeId={activeId}
          expandPath={["assets", "files", "stdio", ...taskDirIds(files)]}
          emptyTitle="No outputs"
        />
      </div>
      <div className="relative min-h-0 overflow-auto">
        {binaryKind && !previewError ? (
          <BinaryPreview kind={binaryKind} url={blobUrl} name={filePath} />
        ) : structurePlugin &&
          typeof preview === "string" &&
          preview.length > 0 &&
          !previewError ? (
          <Suspense
            fallback={
              <div className="flex h-full items-center justify-center text-label text-muted-foreground">
                Loading structure…
              </div>
            }
          >
            <structurePlugin.Component
              content={preview}
              name={previewName}
              path={previewName}
              folderId=""
            />
          </Suspense>
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

import { Atom, FileText } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { EmptyState } from "@/app/components/entity";
import type { RendererProps } from "@/app/types";
import { WorkbenchAction } from "@/components/workbench";
import { formatBytes } from "@/lib/format-bytes";
import type { DiscoveredFile } from "@/plugins/types";
import { MolvisErrorBoundary } from "./MolvisErrorBoundary";
import {
  isMolvisTrajectory,
  isMolvisTrajectoryName,
  isMolvisZarr,
  uniqueMolvisFiles,
} from "./openable";
import { TrajectoryViewer } from "./TrajectoryViewer";

type MolvisTabProps = RendererProps & { discoveredFiles?: DiscoveredFile[] };

interface FileListProps {
  files: DiscoveredFile[];
  active: string | null;
  onSelect: (relPath: string) => void;
}

const FileList = ({ files, active, onSelect }: FileListProps): JSX.Element => {
  return (
    <aside className="flex w-56 flex-none flex-col border-r border-border bg-surface-subtle">
      <div className="flex h-toolbar-compact items-center gap-2 border-b border-border px-3">
        <Atom className="size-icon text-accent" />
        <span className="text-label font-medium text-foreground">MolVis</span>
        <span className="ml-auto font-mono text-micro text-muted-foreground">{files.length}</span>
      </div>
      <div className="min-h-0 flex-1 overflow-auto p-1">
        {files.map((file) => (
          <WorkbenchAction
            kind="ghost"
            size="content"
            key={file.relPath}
            type="button"
            onClick={() => onSelect(file.relPath)}
            className={`flex w-full items-center gap-2 rounded-none px-2 py-row-pad text-left font-mono text-micro transition-colors ${
              file.relPath === active
                ? "bg-accent-muted text-accent-muted-foreground"
                : "text-muted-foreground hover:bg-interactive hover:text-foreground"
            }`}
          >
            <FileText className="size-icon-sm flex-none" aria-hidden />
            <span className="truncate" title={file.relPath}>
              {file.name}
            </span>
          </WorkbenchAction>
        ))}
      </div>
    </aside>
  );
};

interface PreviewPaneProps {
  projectId: string;
  experimentId: string;
  runId: string;
  executionDir: string;
  executionId: string;
  file: DiscoveredFile | null;
}

/**
 * Right-hand content area. Fills the blank space (with padding) and renders the
 * selected file as a space-filling 3D canvas, or a friendly notice for
 * anything molvis cannot draw. Solver logs are not molvis's: they are numbers
 * over time, and charts are molplot's alone.
 */
const PreviewPane = ({
  projectId,
  experimentId,
  runId,
  executionDir,
  executionId,
  file,
}: PreviewPaneProps): JSX.Element => {
  if (!file) {
    return (
      <div className="flex flex-1 items-center justify-center p-6">
        <EmptyState
          icon={<Atom className="h-6 w-6" />}
          title="Select a file"
          description="Pick a PDB, XYZ, LAMMPS dump, or Zarr store to preview."
        />
      </div>
    );
  }

  const header = (
    <div className="flex flex-none items-center gap-2 px-4 pt-4 text-label text-muted-foreground">
      <span className="truncate font-mono text-foreground" title={file.relPath}>
        {file.relPath}
      </span>
      <span className="ml-auto flex-none tabular-nums">{formatBytes(file.size)}</span>
    </div>
  );

  if (isMolvisTrajectory(file)) {
    return (
      <div className="flex min-h-0 flex-1 flex-col">
        {header}
        <div className="min-h-0 flex-1 p-4">
          <MolvisErrorBoundary key={file.relPath}>
            <TrajectoryViewer
              projectId={projectId}
              experimentId={experimentId}
              runId={runId}
              executionDir={executionDir}
              executionId={executionId}
              file={file}
              className="h-full"
            />
          </MolvisErrorBoundary>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-1 items-center justify-center p-6">
      <EmptyState
        icon={<FileText className="h-6 w-6" />}
        title="Cannot open in MolVis"
        description={`${file.name} is not a molvis trajectory or Zarr store.`}
      />
    </div>
  );
};

export const MolvisTab = ({
  selection,
  snapshot,
  discoveredFiles = [],
  executionId,
  executionDir,
}: MolvisTabProps): JSX.Element => {
  const run = useMemo(
    () => snapshot.runs.find((r) => r.id === selection.objectId) ?? null,
    [snapshot.runs, selection.objectId],
  );
  const [activeFile, setActiveFile] = useState<string | null>(null);
  const openableFiles = useMemo(() => uniqueMolvisFiles(discoveredFiles), [discoveredFiles]);

  const defaultRelPath = useMemo(() => {
    const trajectory = openableFiles.find((file) => isMolvisTrajectoryName(file.name));
    const zarr = openableFiles.find((file) => isMolvisZarr(file));
    return (trajectory ?? zarr ?? openableFiles[0])?.relPath ?? null;
  }, [openableFiles]);

  useEffect(() => {
    if (!activeFile && defaultRelPath) {
      setActiveFile(defaultRelPath);
    }
  }, [activeFile, defaultRelPath]);

  if (!run || !executionId || !executionDir) {
    return (
      <div className="flex h-full items-center justify-center bg-background">
        <EmptyState
          icon={<Atom className="h-6 w-6" />}
          title={run ? "Select an execution" : "Run not found"}
          description={
            run
              ? "MolVis files belong to one physical execution."
              : "The selected run is unavailable."
          }
        />
      </div>
    );
  }

  if (openableFiles.length === 0) {
    return (
      <div className="flex h-full items-center justify-center bg-background">
        <EmptyState
          icon={<Atom className="h-6 w-6" />}
          title="Nothing MolVis can open"
          description="This run has no PDB, XYZ, LAMMPS dump, or Zarr trajectory."
        />
      </div>
    );
  }

  const selectedFile = openableFiles.find((file) => file.relPath === activeFile) ?? null;

  return (
    <div className="flex min-h-0 flex-1 bg-background">
      <FileList files={openableFiles} active={activeFile} onSelect={setActiveFile} />
      <main className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <PreviewPane
          projectId={run.projectId}
          experimentId={run.experimentId}
          runId={run.id}
          executionDir={executionDir}
          executionId={executionId}
          file={selectedFile}
        />
      </main>
    </div>
  );
};

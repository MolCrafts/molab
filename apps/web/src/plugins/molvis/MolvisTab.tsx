import { Atom, FileText } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { LammpsLogResponse, LammpsThermoStage } from "@/api";
import { runsApi } from "@/api";
import { EmptyState } from "@/app/components/entity";
import type { RendererProps } from "@/app/types";
import { WorkbenchAction } from "@/components/workbench";
import { CHART_SERIES_PALETTE } from "@/lib/chart-tokens";
import { formatBytes } from "@/lib/format-bytes";
import { MolplotLineChart } from "@/plugins/molplot";
import type { DiscoveredFile } from "@/plugins/types";
import { MolvisErrorBoundary } from "./MolvisErrorBoundary";
import {
  isMolvisLog,
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
      <div className="flex h-[35px] items-center gap-2 border-b border-border px-3">
        <Atom className="h-4 w-4 text-accent" />
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
            className={`flex w-full items-center gap-2 rounded-none px-2 py-1.5 text-left font-mono text-micro transition-colors ${
              file.relPath === active
                ? "bg-accent-muted text-accent-muted-foreground"
                : "text-muted-foreground hover:bg-interactive hover:text-foreground"
            }`}
          >
            <FileText className="size-3.5 flex-none" aria-hidden />
            <span className="truncate" title={file.relPath}>
              {file.name}
            </span>
          </WorkbenchAction>
        ))}
      </div>
    </aside>
  );
};

interface ThermoChartProps {
  stage: LammpsThermoStage;
  columnIndex: number;
  color: string;
}

const ThermoChart = ({ stage, columnIndex, color }: ThermoChartProps): JSX.Element => {
  // Defaults live inside useMemo so a missing ``stage.columns``/``rows``
  // doesn't materialise a fresh ``[]`` per render and invalidate the
  // memo, which would tear down + re-mount the plotly chart on every
  // parent update.
  const config = useMemo(() => {
    const columns = stage.columns ?? [];
    const rows = stage.rows ?? [];
    const stepIndex = columns.indexOf("Step");
    return {
      series: [
        {
          id: columns[columnIndex] ?? `col${columnIndex}`,
          label: columns[columnIndex],
          color,
          initialPoints: rows.map((row, idx) => ({
            x: stepIndex >= 0 ? row[stepIndex] : idx,
            y: row[columnIndex],
          })),
        },
      ],
      xAxis: { label: "Step" },
      hovertemplate: "%{y:.6g}<extra></extra>",
      hovermode: "x unified" as const,
      modebar: true,
      modebarRemove: ["lasso2d", "select2d", "toggleSpikelines"],
      theme: "auto" as const,
    };
  }, [color, stage, columnIndex]);

  return (
    <MolplotLineChart
      config={config}
      style={{ width: "100%", height: "var(--spacing-chart-md)" }}
    />
  );
};

interface ThermoStageProps {
  stage: LammpsThermoStage;
}

const ThermoStageView = ({ stage }: ThermoStageProps): JSX.Element => {
  const columns = stage.columns ?? [];
  const rows = stage.rows ?? [];
  const stepIndex = columns.indexOf("Step");
  const seriesColumns = columns
    .map((name, index) => ({ name, index }))
    .filter(({ index }) => index !== stepIndex);

  if (seriesColumns.length === 0) {
    return (
      <div className="bg-surface/60 px-3 py-6 text-center text-body-lg text-muted-foreground">
        Stage parsed but contains no plottable columns.
      </div>
    );
  }

  return (
    <div className="grid gap-3 lg:grid-cols-2">
      {seriesColumns.map(({ name, index }, paletteIdx) => {
        const lastValue = rows[rows.length - 1]?.[index];
        return (
          <section key={name} className="min-w-0 bg-surface/65 p-3">
            <div className="flex items-baseline justify-between gap-3">
              <div className="min-w-0 truncate text-body-lg font-medium text-foreground">
                {name}
              </div>
              <div className="font-mono text-label text-muted-foreground">
                {Number.isFinite(lastValue) ? lastValue.toPrecision(4) : "—"}
              </div>
            </div>
            <ThermoChart
              stage={stage}
              columnIndex={index}
              color={CHART_SERIES_PALETTE[paletteIdx % CHART_SERIES_PALETTE.length]}
            />
          </section>
        );
      })}
    </div>
  );
};

interface LogPreviewProps {
  projectId: string;
  experimentId: string;
  runId: string;
  executionId: string;
  file: DiscoveredFile;
}

const LogPreview = ({ projectId, experimentId, runId, executionId, file }: LogPreviewProps): JSX.Element => {
  const [response, setResponse] = useState<LammpsLogResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setResponse(null);
    setError(null);

    runsApi
      .getRunLammpsLog(projectId, experimentId, runId, executionId, file.relPath)
      .then((value) => {
        if (!cancelled) setResponse(value);
      })
      .catch((reason) => {
        if (!cancelled) {
          setError(reason instanceof Error ? reason.message : "Failed to load log");
        }
      });

    return () => {
      cancelled = true;
    };
  }, [projectId, experimentId, runId, executionId, file.relPath]);

  if (error) {
    return (
      <EmptyState
        icon={<FileText className="h-6 w-6" />}
        title="Cannot read log"
        description={error}
      />
    );
  }

  if (response === null) {
    return <div className="text-body-lg text-muted-foreground">Loading {file.relPath}…</div>;
  }

  const stages = response.stages ?? [];
  if ((response.nStages ?? 0) === 0 || stages.length === 0) {
    return (
      <EmptyState
        icon={<FileText className="h-6 w-6" />}
        title="No thermo data found"
        description={`molpy parsed ${file.relPath} but found no Per-MPI-rank thermo blocks.`}
      />
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {stages.map((stage, idx) => {
        const firstStep = stage.rows?.[0]?.[stage.columns?.indexOf("Step") ?? -1];
        const stageKey = `${file.relPath}:${Number.isFinite(firstStep) ? firstStep : idx}`;
        return (
          <div key={stageKey} className="flex flex-col gap-2">
            {stages.length > 1 && (
              <div className="text-label uppercase tracking-wide text-muted-foreground">
                Stage {idx + 1}
              </div>
            )}
            <ThermoStageView stage={stage} />
          </div>
        );
      })}
    </div>
  );
};

interface PreviewPaneProps {
  projectId: string;
  experimentId: string;
  runId: string;
  executionId: string;
  file: DiscoveredFile | null;
}

/**
 * Right-hand content area. Fills the blank space (with padding) and renders the
 * selected file: thermo charts for LAMMPS logs, a space-filling 3D canvas for
 * trajectories, a friendly notice for anything molvis cannot draw.
 */
const PreviewPane = ({ projectId, experimentId, runId, executionId, file }: PreviewPaneProps): JSX.Element => {
  if (!file) {
    return (
      <div className="flex flex-1 items-center justify-center p-6">
        <EmptyState
          icon={<Atom className="h-6 w-6" />}
          title="Select a file"
          description="Pick a PDB, XYZ, LAMMPS dump, Zarr store, or LAMMPS log to preview."
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

  if (isMolvisLog(file.name)) {
    return (
      <div className="flex min-h-0 flex-1 flex-col">
        {header}
        <div className="min-h-0 flex-1 overflow-auto p-4">
          <LogPreview projectId={projectId} experimentId={experimentId} runId={runId}
            executionId={executionId} file={file} />
        </div>
      </div>
    );
  }

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
        description={`${file.name} is not a molvis log, trajectory, or Zarr store.`}
      />
    </div>
  );
};

export const MolvisTab = ({
  selection,
  snapshot,
  discoveredFiles = [],
  executionId,
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
    const log = openableFiles.find((file) => isMolvisLog(file.name));
    return (trajectory ?? zarr ?? log ?? openableFiles[0])?.relPath ?? null;
  }, [openableFiles]);

  useEffect(() => {
    if (!activeFile && defaultRelPath) {
      setActiveFile(defaultRelPath);
    }
  }, [activeFile, defaultRelPath]);

  if (!run || !executionId) {
    return (
      <div className="flex h-full items-center justify-center bg-background">
        <EmptyState
          icon={<Atom className="h-6 w-6" />}
          title={run ? "Select an execution" : "Run not found"}
          description={run ? "MolVis files belong to one physical execution." : "The selected run is unavailable."}
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
          description="This run has no PDB, XYZ, LAMMPS dump, Zarr trajectory, or LAMMPS log."
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
          executionId={executionId}
          file={selectedFile}
        />
      </main>
    </div>
  );
};

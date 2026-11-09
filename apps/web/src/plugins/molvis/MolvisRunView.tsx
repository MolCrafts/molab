/**
 * MolVis on the run page (L14): the attempt's structure files | the scene |
 * style. One view, no tabs, no toolbar row, no summary line. `<RunView>`
 * lays the files and style out for a phone itself.
 */

import type { AttemptFile, RunViewProps } from "@molcrafts/molab-plugin";
import { RunView, type RunViewStateSpec, useAttemptText } from "@molcrafts/molab-plugin/ui";
import { Atom } from "lucide-react";
import { useMemo, useState } from "react";
import { formatBytes } from "@/lib/format-bytes";
import { MolvisErrorBoundary } from "./MolvisErrorBoundary";
import { defaultMolvisFile, isMolvisZarr, uniqueMolvisFiles, zarrStoreRoot } from "./openable";
import { StylePanel } from "./StylePanel";
import { DEFAULT_STYLE, type MolvisStyle } from "./sceneStyle";
import { type SceneInfo, type SceneSource, TrajectoryViewer } from "./TrajectoryViewer";

const fileIcon = <Atom aria-hidden className="size-icon-sm" />;

/** The scene's source for *file*, or the state that stands in for it. */
const useSceneSource = (
  file: AttemptFile | null,
  attemptDir: string | null,
): { source: SceneSource | null; state: RunViewStateSpec | null } => {
  const zarr = file ? isMolvisZarr(file) : false;
  const text = useAttemptText(file && !zarr ? file.relPath : null);
  if (!file) return { source: null, state: { kind: "empty", title: "Nothing MolVis can open" } };
  if (zarr) {
    if (!attemptDir) {
      return {
        source: null,
        state: {
          kind: "error",
          title: `Cannot open ${file.name}`,
          detail: "The attempt has no directory.",
        },
      };
    }
    const storeRoot = zarrStoreRoot(file.relPath);
    return { source: { kind: "mrec", name: file.name, storeRoot, attemptDir }, state: null };
  }
  if (text.error) {
    return {
      source: null,
      state: {
        kind: "error",
        title: `Cannot read ${file.name}`,
        detail: text.error,
        onRetry: text.refetch,
      },
    };
  }
  if (text.data === undefined) return { source: null, state: { kind: "loading" } };
  if (text.data.length === 0) {
    return { source: null, state: { kind: "empty", title: `${file.name} is empty` } };
  }
  return { source: { kind: "text", name: file.name, content: text.data }, state: null };
};

export const MolvisRunView = ({ attempt, files }: RunViewProps): JSX.Element => {
  const openable = useMemo(() => uniqueMolvisFiles(files), [files]);
  const [picked, setPicked] = useState<string | null>(null);
  const [style, setStyle] = useState<MolvisStyle>(DEFAULT_STYLE);
  const [info, setInfo] = useState<SceneInfo | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [attemptKey, setAttemptKey] = useState(0);

  const file =
    openable.find((candidate) => candidate.relPath === picked) ?? defaultMolvisFile(openable);
  const { source, state } = useSceneSource(file, attempt.dir);

  const pick = (relPath: string): void => {
    setPicked(relPath);
    setInfo(null);
    setFailure(null);
  };
  const retry = (): void => {
    setFailure(null);
    setAttemptKey((key) => key + 1);
  };

  const failedState: RunViewStateSpec | null =
    failure && file
      ? { kind: "error", title: `Cannot open ${file.name}`, detail: failure, onRetry: retry }
      : null;

  const items = openable.map((candidate) => ({
    id: candidate.relPath,
    label: candidate.name,
    meta: isMolvisZarr(candidate) ? undefined : formatBytes(candidate.size),
    icon: fileIcon,
    selected: candidate.relPath === file?.relPath,
  }));

  return (
    <RunView
      files={<RunView.Files mode="pick" items={items} onPick={pick} />}
      style={<StylePanel style={style} info={info} onChange={setStyle} />}
      state={failedState ?? state}
    >
      {source ? (
        <MolvisErrorBoundary key={`${source.name}:${attemptKey}`}>
          <TrajectoryViewer
            key={attemptKey}
            source={source}
            style={style}
            onLoaded={setInfo}
            onFailed={setFailure}
          />
        </MolvisErrorBoundary>
      ) : null}
    </RunView>
  );
};

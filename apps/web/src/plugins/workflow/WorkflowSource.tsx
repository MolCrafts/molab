/**
 * The Workflow view's Source (Figma L06-4, L06-5, decision 4): the bound file
 * in the editor. A document workflow is its IR JSON, editable — the view saves
 * it like a graph edit; a code workflow is its `.py`, read only.
 */

import { useQuery } from "@tanstack/react-query";
import { type JSX, Suspense } from "react";
import { workspaceFileTextQueryOptions } from "@/app/state/entityQueries";
import { WorkbenchOperationState, WorkbenchRetryAction } from "@/components/workbench";
import { useUiTheme } from "@/lib/ui-theme";
import { MonacoEditor } from "@/plugins/editor";

const EDITOR_OPTIONS = {
  minimap: { enabled: false },
  scrollBeyondLastLine: false,
  lineNumbers: "on",
} as const;

export const DocumentSource = ({
  text,
  onChange,
  readOnly,
}: {
  text: string;
  onChange: (next: string) => void;
  readOnly: boolean;
}): JSX.Element => {
  const theme = useUiTheme();
  return (
    <Suspense fallback={<WorkbenchOperationState kind="loading" title="Loading source editor…" />}>
      <MonacoEditor
        height="100%"
        language="json"
        value={text}
        theme={theme === "dark" ? "vs-dark" : "light"}
        onChange={(next) => onChange(next ?? "")}
        options={{ ...EDITOR_OPTIONS, readOnly }}
      />
    </Suspense>
  );
};

export const CodeSource = ({ path }: { path: string }): JSX.Element => {
  const theme = useUiTheme();
  const query = useQuery({ ...workspaceFileTextQueryOptions(path), enabled: Boolean(path) });
  if (!path) {
    return (
      <WorkbenchOperationState
        kind="disabled"
        title="No source file"
        detail="This workflow records no file to show."
      />
    );
  }
  if (query.isPending) {
    return <WorkbenchOperationState kind="loading" title="Loading workflow source…" />;
  }
  if (query.isError) {
    return (
      <WorkbenchOperationState
        kind="error"
        title="Could not load workflow source"
        detail={query.error instanceof Error ? query.error.message : path}
        action={<WorkbenchRetryAction onClick={() => void query.refetch()} />}
      />
    );
  }
  return (
    <Suspense fallback={<WorkbenchOperationState kind="loading" title="Loading source editor…" />}>
      <MonacoEditor
        height="100%"
        language="python"
        value={query.data}
        theme={theme === "dark" ? "vs-dark" : "light"}
        options={{ ...EDITOR_OPTIONS, readOnly: true }}
      />
    </Suspense>
  );
};

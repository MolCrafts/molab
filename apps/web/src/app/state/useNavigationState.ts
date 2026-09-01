import { useCallback, useMemo } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { experimentPath, projectPath } from "@/app/entities/paths";
import { getNavigationContribution, leftPanelViewFromPath } from "@/app/navigation/sections";
import type {
  ExperimentView,
  LeftPanelView,
  ObjectView,
  ProjectView,
  RendererSnapshot,
  Selection,
} from "@/app/types";

type NavigationSnapshot = Pick<RendererSnapshot, "experiments" | "runs" | "workflows">;

const buildWorkspaceFileSelection = (searchParams: URLSearchParams): Selection | null => {
  const filePath = searchParams.get("file");
  const fileKind = searchParams.get("fileKind");

  if (!filePath || !fileKind) {
    return null;
  }

  const assetId = searchParams.get("assetId");
  return {
    objectType: "workspace-file",
    objectId: filePath,
    filePath,
    fileKind:
      fileKind === "yaml" ||
      fileKind === "json" ||
      fileKind === "python" ||
      fileKind === "markdown" ||
      fileKind === "text" ||
      fileKind === "image"
        ? fileKind
        : "unknown",
    assetId: assetId ?? undefined,
    hasPreviewSidecar: searchParams.get("hasPreviewSidecar") === "1",
  };
};

export { leftPanelViewFromPath as getLeftPanelViewFromPath } from "@/app/navigation/sections";

const parseObjectView = (raw: string | null): ObjectView | undefined => {
  if (!raw || !/^[a-z0-9][a-z0-9:_-]{0,63}$/i.test(raw)) return undefined;
  return raw;
};

const parseExperimentView = (raw: string | undefined): ExperimentView | undefined => {
  if (raw === "workflow" || raw === "runs" || raw === "compare") return raw;
  return undefined;
};

const parseProjectView = (raw: string | undefined): ProjectView | undefined => {
  if (raw === "experiments" || raw === "assets" || raw === "settings") return raw;
  return undefined;
};

export const buildSelectionFromLocation = (
  pathname: string,
  searchParams: URLSearchParams,
): Selection | null => {
  const objectView = parseObjectView(searchParams.get("tab"));

  const taskMatch = pathname.match(
    /^\/projects\/([^/]+)\/experiments\/([^/]+)\/runs\/([^/]+)\/tasks\/([^/]+)$/,
  );
  if (taskMatch) {
    return {
      objectType: "task",
      taskId: decodeURIComponent(taskMatch[4]),
      runId: decodeURIComponent(taskMatch[3]),
      objectId: decodeURIComponent(taskMatch[4]),
    };
  }

  const projectRunMatch = pathname.match(
    /^\/projects\/([^/]+)\/experiments\/([^/]+)\/runs\/([^/]+)$/,
  );
  if (projectRunMatch) {
    return {
      objectType: "run",
      objectId: decodeURIComponent(projectRunMatch[3]),
      objectView,
    };
  }

  const experimentViewMatch = pathname.match(
    /^\/projects\/([^/]+)\/experiments\/([^/]+)\/(workflow|runs|compare)$/,
  );
  if (experimentViewMatch) {
    return {
      objectType: "experiment",
      objectId: decodeURIComponent(experimentViewMatch[2]),
      experimentView: parseExperimentView(experimentViewMatch[3]),
    };
  }

  const experimentMatch = pathname.match(/^\/projects\/([^/]+)\/experiments\/([^/]+)$/);
  if (experimentMatch) {
    return {
      objectType: "experiment",
      objectId: decodeURIComponent(experimentMatch[2]),
    };
  }

  const projectViewMatch = pathname.match(/^\/projects\/([^/]+)\/(experiments|assets|settings)$/);
  if (projectViewMatch) {
    return {
      objectType: "project",
      objectId: decodeURIComponent(projectViewMatch[1]),
      projectView: parseProjectView(projectViewMatch[2]),
    };
  }

  const projectMatch = pathname.match(/^\/projects\/([^/]+)$/);
  if (projectMatch) {
    return {
      objectType: "project",
      objectId: decodeURIComponent(projectMatch[1]),
    };
  }

  const workflowMatch = pathname.match(/^\/workflows\/([^/]+)$/);
  if (workflowMatch) {
    return {
      objectType: "workflow",
      objectId: decodeURIComponent(workflowMatch[1]),
      workflowId: decodeURIComponent(workflowMatch[1]),
    };
  }

  const assetMatch = pathname.match(/^\/assets\/([^/]+)$/);
  if (assetMatch) {
    return {
      objectType: "asset",
      objectId: decodeURIComponent(assetMatch[1]),
    };
  }

  if (pathname === "/agent-tasks/new") {
    const projectId = searchParams.get("project");
    return {
      objectType: "agent",
      objectId: "new",
      scope: projectId
        ? {
            projectId,
            experimentId: searchParams.get("experiment") ?? undefined,
            runId: searchParams.get("run") ?? undefined,
          }
        : undefined,
    };
  }

  const agentMatch = pathname.match(/^\/agent-tasks\/([^/]+)$/);
  if (agentMatch) {
    return {
      objectType: "agent",
      objectId: decodeURIComponent(agentMatch[1]),
    };
  }

  if (pathname === "/knowledge" || pathname.startsWith("/knowledge/")) {
    // The concept's bundle-relative path (which may contain "/") is the rest
    // after "/knowledge/"; bare "/knowledge" is the browse overview.
    const rest = pathname === "/knowledge" ? "" : pathname.slice("/knowledge/".length);
    return { objectType: "knowledge", objectId: decodeURIComponent(rest) };
  }

  if (pathname.startsWith("/workspace")) {
    return buildWorkspaceFileSelection(searchParams);
  }

  return null;
};

export const getSelectionPath = (
  selection: Selection | null,
  snapshot: NavigationSnapshot,
): string => {
  if (!selection) {
    return "/projects";
  }

  switch (selection.objectType) {
    case "project":
      return projectPath(selection.objectId, selection.projectView ?? "overview");
    case "experiment": {
      const experiment = snapshot.experiments.find((item) => item.id === selection.objectId);
      if (!experiment) {
        return "/projects";
      }
      return experimentPath(
        experiment.projectId,
        experiment.id,
        selection.experimentView ?? "overview",
      );
    }
    case "run": {
      const run = snapshot.runs.find((item) => item.id === selection.objectId);
      if (!run) {
        return "/projects";
      }
      const path = `/projects/${encodeURIComponent(run.projectId)}/experiments/${encodeURIComponent(run.experimentId)}/runs/${encodeURIComponent(run.id)}`;
      if (!selection.objectView) {
        return path;
      }
      const params = new URLSearchParams({ tab: selection.objectView });
      return `${path}?${params.toString()}`;
    }
    case "task": {
      const run = snapshot.runs.find((item) => item.id === selection.runId);
      if (!run) {
        return "/projects";
      }
      return `/projects/${encodeURIComponent(run.projectId)}/experiments/${encodeURIComponent(run.experimentId)}/runs/${encodeURIComponent(run.id)}/tasks/${encodeURIComponent(selection.taskId)}`;
    }
    case "workflow": {
      const workflow = snapshot.workflows.find((item) => item.id === selection.workflowId);
      const experiment = workflow
        ? snapshot.experiments.find((item) => item.id === workflow.experimentId)
        : undefined;
      return experiment
        ? experimentPath(experiment.projectId, experiment.id, "workflow")
        : `/workflows/${encodeURIComponent(selection.workflowId)}`;
    }
    case "asset":
      return `/assets/${encodeURIComponent(selection.objectId)}`;
    case "agent": {
      if (selection.objectId !== "new") {
        return `/agent-tasks/${encodeURIComponent(selection.objectId)}`;
      }
      const scope = selection.scope;
      if (!scope) {
        return "/agent-tasks/new";
      }
      const params = new URLSearchParams({ project: scope.projectId });
      if (scope.experimentId) params.set("experiment", scope.experimentId);
      if (scope.runId) params.set("run", scope.runId);
      return `/agent-tasks/new?${params.toString()}`;
    }
    case "knowledge":
      // objectId is a bundle-relative path (may contain "/"); keep the slashes
      // readable in the URL by encoding each segment, not the whole string.
      return selection.objectId
        ? `/knowledge/${selection.objectId.split("/").map(encodeURIComponent).join("/")}`
        : "/knowledge";
    case "workspace-file": {
      const params = new URLSearchParams({
        file: selection.filePath,
        fileKind: selection.fileKind,
      });
      if (selection.assetId) {
        params.set("assetId", selection.assetId);
      }
      if (selection.hasPreviewSidecar) {
        params.set("hasPreviewSidecar", "1");
      }
      return `/workspace?${params.toString()}`;
    }
  }
};

export interface HierarchyRouteContext {
  projectId: string;
  experimentId: string | null;
}

/**
 * Parent coordinates encoded in canonical Project/Experiment/Run URLs.
 * Unlike a Selection, this information is available before the lazy entity
 * catalog has loaded, so direct links can hydrate their parent chain.
 */
export const hierarchyRouteContextFromPath = (pathname: string): HierarchyRouteContext | null => {
  const match = pathname.match(/^\/projects\/([^/]+)(?:\/experiments\/([^/]+))?(?:\/|$)/);
  if (!match) return null;
  return {
    projectId: decodeURIComponent(match[1]),
    experimentId: match[2] ? decodeURIComponent(match[2]) : null,
  };
};

export interface NavigationState {
  leftPanelView: LeftPanelView;
  selection: Selection | null;
  setLeftPanelView: (view: LeftPanelView) => void;
  setSelection: (selection: Selection | null) => void;
}

export const useNavigationState = (snapshot: NavigationSnapshot): NavigationState => {
  const location = useLocation();
  const navigate = useNavigate();

  const searchParams = useMemo(() => new URLSearchParams(location.search), [location.search]);

  const leftPanelView = useMemo(
    () => leftPanelViewFromPath(location.pathname),
    [location.pathname],
  );

  const selection = useMemo(
    () => buildSelectionFromLocation(location.pathname, searchParams),
    [location.pathname, searchParams],
  );

  const setSelection = useCallback(
    (nextSelection: Selection | null): void => {
      navigate(getSelectionPath(nextSelection, snapshot));
    },
    [navigate, snapshot],
  );

  const setLeftPanelView = useCallback(
    (view: LeftPanelView): void => {
      const contribution = getNavigationContribution(view);
      if (selection && contribution.retainSelectionFor.includes(selection.objectType)) {
        navigate(getSelectionPath(selection, snapshot));
        return;
      }

      navigate(contribution.route);
    },
    [navigate, selection, snapshot],
  );

  return {
    leftPanelView,
    selection,
    setLeftPanelView,
    setSelection,
  };
};

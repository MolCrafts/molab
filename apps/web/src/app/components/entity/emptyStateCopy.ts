export const EMPTY_COPY = {
  experiments: {
    title: "No experiments",
    description: "Create one to begin.",
  },
  runs: {
    title: "No runs",
    description: "New run or Sweep above.",
  },
  projectRuns: {
    title: "No runs",
    description: "Start one from an experiment.",
  },
  assets: {
    title: "No assets",
    description: "Import a file to keep it with this project.",
  },
  entries: {
    title: "Nothing here",
  },
  projectsFilter: {
    title: "No matches",
    description: "Clear the filter to see every project.",
  },
  workspace: {
    title: "No files",
    description: "This workspace has no files yet.",
  },
  emptyFolder: {
    title: "Empty folder",
    description: "Nothing in this folder.",
  },
} as const;

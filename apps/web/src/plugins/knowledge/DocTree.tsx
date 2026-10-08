import { useQueryClient } from "@tanstack/react-query";
import {
  Blocks,
  BookOpen,
  Check,
  FileText,
  Filter,
  FlaskConical,
  FolderInput,
  NotebookPen,
  Pencil,
  PlayCircle,
  Plus,
  Search,
  Trash2,
  X,
} from "lucide-react";
import { type ComponentType, type JSX, useEffect, useState } from "react";
import { knowledgeApi } from "@/api";
import type { KnowledgeSearchRow } from "@/api/generated/models/KnowledgeSearchRow";
import { StatusBadge } from "@/app/components/entity";
import type { TreeNode, TreeNodeAction } from "@/app/panels/TreeView";
import { TreeView } from "@/app/panels/TreeView";
import type { Selection, WorkspaceSnapshot } from "@/app/types";
import { useConfirm } from "@/components/ConfirmDialog";
import { usePrompt } from "@/components/PromptDialog";
import { Code as InlineCode } from "@/components/ui/code";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  WorkbenchAction,
  WorkbenchDismissAction,
  WorkbenchIconAction,
  WorkbenchOperationState,
  WorkbenchRetryAction,
} from "@/components/workbench";
import { cn } from "@/lib/utils";
import { HostPickerDialog } from "./HostPickerDialog";
import { buildDocTree, type DocTreeNode, KB_GROUP_ID, listHostOptions } from "./knowledgeDocTree";
import { knowledgeNoteQueryOptions } from "./queries";
import { isTexDocument } from "./texDocument";
import { useKnowledgeDocs, useKnowledgeFacets } from "./useKnowledgeDocs";

interface KnowledgeFilterProps {
  tags: string[];
  statuses: string[];
  tag: string | null;
  status: string | null;
  disabled?: boolean;
  onTagChange: (tag: string | null) => void;
  onStatusChange: (status: string | null) => void;
}

/**
 * Tag/status filter for the knowledge tree — a popover command list of the
 * available facets. Selecting a facet drives `listKnowledge(?tag=&status=)`
 * server-side (06 query support) so the tree narrows to matching notes; the
 * same selection toggles off to clear.
 */
const KnowledgeFilter = ({
  tags,
  statuses,
  tag,
  status,
  disabled = false,
  onTagChange,
  onStatusChange,
}: KnowledgeFilterProps): JSX.Element => {
  const active = tag !== null || status !== null;
  return (
    <Popover>
      <PopoverTrigger asChild>
        <WorkbenchIconAction label="Filter knowledge" disabled={disabled}>
          <Filter className="size-3.5" />
          {active && <span className="h-1.5 w-1.5 rounded-full bg-info" />}
        </WorkbenchIconAction>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-56 p-0">
        <Command>
          <CommandInput placeholder="Filter by tag / status…" />
          <CommandList>
            <CommandEmpty>No facets yet.</CommandEmpty>
            {statuses.length > 0 && (
              <CommandGroup heading="Status">
                {statuses.map((s) => (
                  <CommandItem
                    key={s}
                    value={`status ${s}`}
                    onSelect={() => onStatusChange(status === s ? null : s)}
                  >
                    <Check
                      className={cn("size-icon", status === s ? "opacity-100" : "opacity-0")}
                    />
                    <StatusBadge status={s} size="sm" />
                  </CommandItem>
                ))}
              </CommandGroup>
            )}
            {tags.length > 0 && (
              <CommandGroup heading="Tags">
                {tags.map((t) => (
                  <CommandItem
                    key={t}
                    value={`tag ${t}`}
                    onSelect={() => onTagChange(tag === t ? null : t)}
                  >
                    <Check className={cn("size-icon", tag === t ? "opacity-100" : "opacity-0")} />
                    <span className="truncate">{t}</span>
                  </CommandItem>
                ))}
              </CommandGroup>
            )}
            {active && (
              <>
                <CommandSeparator />
                <CommandGroup>
                  <CommandItem
                    value="clear filters"
                    onSelect={() => {
                      onTagChange(null);
                      onStatusChange(null);
                    }}
                  >
                    <X className="size-icon" /> Clear filters
                  </CommandItem>
                </CommandGroup>
              </>
            )}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
};

interface DocTreeProps {
  snapshot: WorkspaceSnapshot;
  /** The currently-selected Note's bundle-relative path (drives active row). */
  activeId?: string;
  onSelect: (selection: Selection) => void;
}

const groupPresentation = (
  snapshot: WorkspaceSnapshot,
  hostPath: string,
): { label: string; icon: ComponentType<{ className?: string }> } => {
  const project = snapshot.projects.find((row) => row.path === hostPath);
  if (project) return { label: project.name, icon: Blocks };
  const experiment = snapshot.experiments.find((row) => row.path === hostPath);
  if (experiment) return { label: experiment.name, icon: FlaskConical };
  const run = snapshot.runs.find((row) => row.path === hostPath);
  if (run) return { label: run.name, icon: PlayCircle };
  return { label: hostPath, icon: BookOpen };
};

const collectExpandIds = (nodes: DocTreeNode[], acc: string[]): string[] => {
  for (const node of nodes) {
    if (node.children.length > 0) {
      acc.push(node.id);
      collectExpandIds(node.children, acc);
    }
  }
  return acc;
};

export const DocTree = ({ snapshot, activeId, onSelect }: DocTreeProps): JSX.Element => {
  const queryClient = useQueryClient();
  const [tag, setTag] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const { notes, loading, error, reload, createDoc, renameDoc, moveDoc, deleteDoc } =
    useKnowledgeDocs({ tag, status });
  const {
    tags,
    statuses,
    loading: facetsLoading,
    error: facetsError,
    reload: reloadFacets,
  } = useKnowledgeFacets();
  const filtering = tag !== null || status !== null;
  // Body-aware search (vision-loop-08): a non-empty query switches the tree to
  // a flat hit list served by GET /knowledge/search (Knowledge.search).
  const [search, setSearch] = useState("");
  const [searchHits, setSearchHits] = useState<KnowledgeSearchRow[]>([]);
  const [searchTruncated, setSearchTruncated] = useState(false);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [searchRequestVersion, setSearchRequestVersion] = useState(0);
  useEffect(() => {
    void searchRequestVersion;
    const query = search.trim();
    if (!query) {
      setSearchHits([]);
      setSearchTruncated(false);
      setSearchLoading(false);
      setSearchError(null);
      return;
    }
    let cancelled = false;
    setSearchLoading(true);
    setSearchError(null);
    const handle = window.setTimeout(() => {
      void knowledgeApi
        .searchKnowledge(query)
        .then((response) => {
          if (cancelled) return;
          setSearchHits(response.hits);
          setSearchTruncated(response.truncated);
        })
        .catch((err) => {
          if (!cancelled) {
            setSearchError(
              err instanceof Error ? err.message : "Failed to search knowledge documents",
            );
          }
        })
        .finally(() => {
          if (!cancelled) setSearchLoading(false);
        });
    }, 300);
    return () => {
      cancelled = true;
      window.clearTimeout(handle);
    };
  }, [search, searchRequestVersion]);
  const searching = search.trim().length > 0;
  const handleSearchChange = (value: string): void => {
    setSearch(value);
    setSearchError(null);
    if (value.trim()) {
      setSearchLoading(true);
      return;
    }
    setSearchLoading(false);
    setSearchHits([]);
    setSearchTruncated(false);
  };
  const { prompt, dialog: promptDialog } = usePrompt();
  const { confirm, dialog: confirmDialog } = useConfirm();
  const [operationLabel, setOperationLabel] = useState<string | null>(null);
  const [operationError, setOperationError] = useState<string | null>(null);
  const [operationSuccess, setOperationSuccess] = useState<string | null>(null);
  const [operationRetry, setOperationRetry] = useState<{
    runningLabel: string;
    successLabel: string;
    run: () => Promise<void>;
  } | null>(null);
  const [moveTarget, setMoveTarget] = useState<{ path: string; hostPath: string } | null>(null);

  useEffect(() => {
    if (!operationSuccess) return;
    const handle = window.setTimeout(() => setOperationSuccess(null), 3000);
    return () => window.clearTimeout(handle);
  }, [operationSuccess]);

  const tree = buildDocTree(
    notes.map((n) => ({ relPath: n.relPath, name: n.name, hostPath: n.hostPath ?? "" })),
  );

  const guard = async (
    runningLabel: string,
    successLabel: string,
    run: () => Promise<void>,
  ): Promise<void> => {
    setOperationLabel(runningLabel);
    setOperationError(null);
    setOperationSuccess(null);
    setOperationRetry(null);
    try {
      await run();
      setOperationSuccess(successLabel);
    } catch (err) {
      setOperationError(err instanceof Error ? err.message : String(err));
      setOperationRetry({ runningLabel, successLabel, run });
    } finally {
      setOperationLabel(null);
    }
  };

  const handleCreate = async (hostPath: string): Promise<void> => {
    const name = await prompt({
      title: "New document",
      label: "Document name",
      placeholder: "My note",
      confirmLabel: "Create",
    });
    if (!name) return;
    await guard("Creating document…", "Document created.", () => createDoc(name, hostPath));
  };

  const handleRename = async (path: string, current: string): Promise<void> => {
    const name = await prompt({
      title: "Rename document",
      label: "New name",
      defaultValue: current,
      confirmLabel: "Rename",
    });
    if (!name || name === current) return;
    await guard("Renaming document…", "Document renamed.", () => renameDoc(path, name));
  };

  const handleMove = (path: string, currentHost: string): void => {
    setMoveTarget({ path, hostPath: currentHost });
  };

  const handleDelete = async (path: string, name: string): Promise<void> => {
    const confirmed = await confirm({
      title: "Delete document?",
      description: (
        <>
          Document{" "}
          <InlineCode className="rounded-control bg-muted px-1 py-1 text-label">{name}</InlineCode>{" "}
          will be permanently removed.
        </>
      ),
      confirmLabel: "Delete",
      destructive: true,
    });
    if (!confirmed) return;
    await guard("Deleting document…", "Document deleted.", () => deleteDoc(path));
  };

  const docActions = (node: DocTreeNode): TreeNodeAction[] => {
    if (node.relPath === null || isTexDocument(node.relPath)) return [];
    const path = node.relPath;
    return [
      {
        id: "rename",
        label: "Rename",
        icon: Pencil,
        disabled: operationLabel !== null,
        onSelect: () => void handleRename(path, node.name),
      },
      {
        id: "move",
        label: "Move",
        icon: FolderInput,
        disabled: operationLabel !== null,
        onSelect: () => void handleMove(path, node.hostPath),
      },
      {
        id: "delete",
        label: "Delete",
        icon: Trash2,
        disabled: operationLabel !== null,
        destructive: true,
        separatorBefore: true,
        onSelect: () => void handleDelete(path, node.name),
      },
    ];
  };

  const toTreeNode = (node: DocTreeNode): TreeNode => {
    if (node.kind === "doc" && node.relPath) {
      const path = node.relPath;
      return {
        id: node.id,
        label: node.name,
        icon: isTexDocument(path) ? FileText : NotebookPen,
        iconClassName: "text-muted-foreground",
        onPrefetch: () => {
          void import("./KnowledgeViewer");
          void queryClient.prefetchQuery(knowledgeNoteQueryOptions(path));
        },
        onSelect: () => onSelect({ objectType: "knowledge", objectId: path }),
        actions: docActions(node),
      };
    }
    const presented =
      node.id === KB_GROUP_ID
        ? { label: node.name, icon: BookOpen }
        : groupPresentation(snapshot, node.hostPath);
    return {
      id: node.id,
      label: presented.label,
      icon: presented.icon,
      iconClassName: "text-muted-foreground",
      labelClassName: "font-semibold",
      actions: [
        {
          id: "new-doc",
          label: "New document",
          icon: Plus,
          disabled: operationLabel !== null,
          onSelect: () => void handleCreate(node.hostPath),
        },
      ],
      children: node.children.map(toTreeNode),
    };
  };

  const nodes = tree.map(toTreeNode);
  const expandPath = collectExpandIds(tree, []);
  const emptyTitle = filtering ? "No matching documents" : "No documents yet";
  const emptyDetail = filtering
    ? "No documents match the current tag/status filter."
    : "Create a document to start your knowledge base.";
  const treeContent =
    nodes.length === 0 ? (
      <WorkbenchOperationState
        kind="empty"
        density="compact"
        title={emptyTitle}
        detail={emptyDetail}
      />
    ) : (
      <TreeView nodes={nodes} activeId={activeId} expandPath={expandPath} />
    );

  return (
    <div className="space-y-2" aria-busy={loading || searchLoading || operationLabel !== null}>
      {/* Same action density as LeftExplorer title actions (gap-hairline, compact icons). */}
      <div className="flex items-center justify-between gap-hairline">
        <div className="flex items-center gap-hairline">
          <KnowledgeFilter
            tags={tags}
            statuses={statuses}
            tag={tag}
            status={status}
            disabled={operationLabel !== null}
            onTagChange={setTag}
            onStatusChange={setStatus}
          />
          <Popover>
            <PopoverTrigger asChild>
              <WorkbenchIconAction label="Search knowledge" disabled={operationLabel !== null}>
                <Search className="size-3.5" />
                {searching ? <span className="size-1.5 rounded-full bg-info" /> : null}
              </WorkbenchIconAction>
            </PopoverTrigger>
            <PopoverContent align="start" className="w-72 p-2">
              <Input
                value={search}
                onChange={(event) => handleSearchChange(event.target.value)}
                placeholder="Search notes…"
                className="h-control-compact text-label"
                aria-label="Search knowledge"
                autoFocus
              />
            </PopoverContent>
          </Popover>
        </div>
        <WorkbenchIconAction
          label="New document"
          kind="ghost"
          disabled={operationLabel !== null}
          onClick={() => void handleCreate("")}
        >
          <Plus className="size-icon" />
        </WorkbenchIconAction>
      </div>
      {facetsLoading && tags.length === 0 && statuses.length === 0 && (
        <WorkbenchOperationState
          kind="loading"
          density="inline"
          title="Loading knowledge filters…"
          className="px-2"
        />
      )}
      {facetsError && (
        <WorkbenchOperationState
          kind="error"
          density="compact"
          title="Knowledge filters unavailable"
          detail={facetsError}
          action={<WorkbenchRetryAction onClick={() => void reloadFacets()} />}
        />
      )}
      {operationLabel && (
        <WorkbenchOperationState kind="running" density="compact" title={operationLabel} />
      )}
      {operationError && (
        <WorkbenchOperationState
          kind="error"
          density="compact"
          title="Document operation failed"
          detail={operationError}
          action={
            <div className="flex items-center gap-2">
              {operationRetry && (
                <WorkbenchRetryAction
                  onClick={() =>
                    void guard(
                      operationRetry.runningLabel,
                      operationRetry.successLabel,
                      operationRetry.run,
                    )
                  }
                />
              )}
              <WorkbenchDismissAction
                onClick={() => {
                  setOperationError(null);
                  setOperationRetry(null);
                }}
              />
            </div>
          }
        />
      )}
      {operationSuccess && (
        <WorkbenchOperationState kind="success" density="compact" title={operationSuccess} />
      )}
      {searching ? (
        <div className="space-y-1 px-1">
          {searchLoading ? (
            <WorkbenchOperationState
              kind="loading"
              density="compact"
              title="Searching knowledge…"
              skeletonRows={3}
            />
          ) : searchError ? (
            <WorkbenchOperationState
              kind="error"
              density="compact"
              title="Knowledge search failed"
              detail={searchError}
              action={
                <WorkbenchRetryAction
                  onClick={() => setSearchRequestVersion((version) => version + 1)}
                />
              }
            />
          ) : searchHits.length === 0 ? (
            <WorkbenchOperationState
              kind="empty"
              density="compact"
              title="No matching documents"
              detail="Search covers titles, tags, paths, and note bodies."
            />
          ) : (
            <>
              <WorkbenchOperationState
                kind="success"
                density="inline"
                title={`${searchHits.length} matching document${searchHits.length === 1 ? "" : "s"}`}
                className="sr-only"
              />
              {searchHits.map((hit) => (
                <WorkbenchAction
                  kind="ghost"
                  size="content"
                  type="button"
                  key={hit.path}
                  onClick={() => onSelect({ objectType: "knowledge", objectId: hit.path })}
                  className={cn(
                    "block w-full rounded-control px-2 py-2 text-left hover:bg-muted",
                    activeId === hit.path && "bg-muted",
                  )}
                >
                  <span className="block truncate text-body-lg text-foreground">{hit.title}</span>
                  <span className="block truncate text-micro text-muted-foreground">
                    {hit.path}
                  </span>
                  {hit.snippet && (
                    <span className="block truncate text-micro italic text-muted-foreground">
                      {hit.snippet}
                    </span>
                  )}
                </WorkbenchAction>
              ))}
            </>
          )}
          {searchTruncated && (
            <p className="px-2 text-micro text-muted-foreground">…truncated — refine the query.</p>
          )}
        </div>
      ) : loading && notes.length === 0 ? (
        <WorkbenchOperationState
          kind="loading"
          density="compact"
          title="Loading knowledge documents…"
          skeletonRows={5}
        />
      ) : error && notes.length === 0 ? (
        <WorkbenchOperationState
          kind="error"
          density="compact"
          title="Could not load knowledge documents"
          detail={error}
          action={<WorkbenchRetryAction onClick={() => void reload()} />}
        />
      ) : (
        <>
          {error && (
            <WorkbenchOperationState
              kind="error"
              density="compact"
              title="Could not refresh knowledge documents"
              detail={error}
              action={<WorkbenchRetryAction onClick={() => void reload()} />}
            />
          )}
          {loading ? (
            <WorkbenchOperationState
              kind="running"
              density="compact"
              title="Refreshing knowledge documents…"
            >
              {treeContent}
            </WorkbenchOperationState>
          ) : (
            treeContent
          )}
        </>
      )}
      {promptDialog}
      {confirmDialog}
      <HostPickerDialog
        open={moveTarget !== null}
        onOpenChange={(open) => {
          if (!open) setMoveTarget(null);
        }}
        options={listHostOptions(snapshot, moveTarget?.hostPath ?? "")}
        onPick={(hostPath) => {
          if (!moveTarget) return;
          const path = moveTarget.path;
          setMoveTarget(null);
          void guard("Moving document…", "Document moved.", () => moveDoc(path, hostPath));
        }}
      />
    </div>
  );
};

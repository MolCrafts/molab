import { Plus, Tag, X } from "lucide-react";
import { type JSX, type KeyboardEvent, useEffect, useMemo, useState } from "react";
import { StatusBadge } from "@/app/components/entity";
import { workspaceApi } from "@/app/state/api";
import { knowledgeErrorMessage, useInvalidate, useKnowledgeListQuery } from "@/app/state/queries";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { WorkbenchIconAction, WorkbenchTag } from "@/components/workbench";

/** Common lifecycle labels offered in the status select; `status` is an open
 * string on the backend, so the current value is always included as an option. */
const STATUS_OPTIONS = ["active", "draft", "archived"] as const;

/**
 * Writable document-level tag + status controls for a Note.
 *
 * Reads the note's 05 metadata (`tags` / `status`) from the one shared
 * knowledge-list cache entry — the same `GET /api/knowledge` the doc tree, its
 * facet filter, the command palette and the viewer use, so opening a note costs
 * no extra request — then persists edits via `workspaceApi.updateNoteMeta`, the
 * thin `PATCH /knowledge/doc/meta` route that delegates to `Note.set_tags` /
 * `Note.set_status` (the same verbs the CLI uses, per the Python==UI
 * invariant). A save realigns local state with the server-returned summary and
 * invalidates the knowledge keys; a failed save surfaces an inline error and
 * leaves the prior state intact.
 */
export const DocumentControls = ({ relPath }: { relPath: string }): JSX.Element | null => {
  const listQuery = useKnowledgeListQuery();
  const { afterNoteMutation } = useInvalidate();
  const [tags, setTags] = useState<string[]>([]);
  const [status, setStatus] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tagInput, setTagInput] = useState("");

  const summary = useMemo(
    () => listQuery.data?.notes.find((note) => note.relPath === relPath) ?? null,
    [listQuery.data, relPath],
  );
  const loaded = listQuery.data !== undefined;

  // Seed the editable controls from the server summary whenever it changes
  // (note switch, or a refetch after someone else's edit).
  useEffect(() => {
    setTags(summary?.tags ?? []);
    setStatus(summary?.status ?? null);
    setError(null);
  }, [summary]);

  const statusOptions = useMemo(() => {
    const opts = [...STATUS_OPTIONS] as string[];
    if (status && !opts.includes(status)) opts.push(status);
    return opts;
  }, [status]);

  const persist = async (patch: { tags?: string[]; status?: string }): Promise<void> => {
    setSaving(true);
    setError(null);
    try {
      const updated = await workspaceApi.updateNoteMeta(relPath, patch);
      setTags(updated.tags ?? []);
      setStatus(updated.status ?? null);
      // Tags/status feed the tree's facet filter, so realign the shared list.
      void afterNoteMutation(relPath);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save doc metadata.");
    } finally {
      setSaving(false);
    }
  };

  const addTag = (raw: string): void => {
    const tag = raw.trim();
    setTagInput("");
    if (!tag || tags.includes(tag)) return;
    void persist({ tags: [...tags, tag] });
  };

  const removeTag = (tag: string): void => {
    void persist({ tags: tags.filter((t) => t !== tag) });
  };

  const onTagKeyDown = (event: KeyboardEvent<HTMLInputElement>): void => {
    if (event.key === "Enter") {
      event.preventDefault();
      addTag(tagInput);
    }
  };

  if (!loaded) {
    if (listQuery.error) {
      return (
        <p className="text-label text-destructive">
          {knowledgeErrorMessage(listQuery.error, "Failed to load doc metadata.")}
        </p>
      );
    }
    return <p className="text-micro text-muted-foreground">Loading…</p>;
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <Select
          value={status ?? undefined}
          onValueChange={(next) => {
            if (next !== status) void persist({ status: next });
          }}
          disabled={saving}
        >
          <SelectTrigger className="h-control-compact w-32 text-label" aria-label="Document status">
            <SelectValue placeholder="Set status">
              {status ? <StatusBadge status={status} size="sm" /> : "Set status"}
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            {statusOptions.map((option) => (
              <SelectItem key={option} value={option} className="text-label">
                {option}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <span className="text-border">·</span>
        <Tag className="h-3.5 w-3.5 text-muted-foreground" />
        {tags.length > 0 ? (
          tags.map((tag) => (
            <WorkbenchTag
              key={tag}
              meaning="metadata"
              className="gap-1 px-2 py-0 text-micro font-medium"
            >
              {tag}
              <WorkbenchIconAction
                label={`Remove tag ${tag}`}
                className="size-4 text-muted-foreground hover:text-destructive disabled:opacity-50"
                onClick={() => removeTag(tag)}
                disabled={saving}
              >
                <X className="h-2.5 w-2.5" />
              </WorkbenchIconAction>
            </WorkbenchTag>
          ))
        ) : (
          <span className="text-micro text-muted-foreground">No tags</span>
        )}
      </div>
      <div className="flex items-center gap-2">
        <Input
          value={tagInput}
          onChange={(event) => setTagInput(event.target.value)}
          onKeyDown={onTagKeyDown}
          placeholder="Add tag…"
          aria-label="Add tag"
          className="h-control-compact w-40 text-label"
          disabled={saving}
        />
        <WorkbenchIconAction
          label="Add tag"
          onClick={() => addTag(tagInput)}
          disabled={saving || tagInput.trim().length === 0}
        >
          <Plus className="size-3.5" />
        </WorkbenchIconAction>
      </div>
      {error ? <p className="text-micro text-destructive">{error}</p> : null}
    </div>
  );
};

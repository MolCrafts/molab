import { useQueryClient } from "@tanstack/react-query";
import { Plus, Tag, X } from "lucide-react";
import { type JSX, type KeyboardEvent, useEffect, useMemo, useState } from "react";
import { knowledgeApi } from "@/api";
import { StatusBadge } from "@/app/components/entity";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { WorkbenchIconAction, WorkbenchTag } from "@/components/workbench";
import { knowledgeKeys, useKnowledgeListQuery } from "@/plugins/knowledge/queries";
import { isTexDocument } from "@/plugins/knowledge/texDocument";

/** Common lifecycle labels offered in the status select; `status` is an open
 * string on the backend, so the current value is always included as an option. */
const STATUS_OPTIONS = ["active", "draft", "archived"] as const;

/**
 * Writable document-level tag + status controls for a Note.
 *
 * Loads the note's 05 metadata (`tags` / `status`) through
 * `knowledgeApi.listKnowledge` (the generated client), then persists edits via
 * `knowledgeApi.updateDocMeta` — the thin `PATCH /knowledge/doc/meta` route that
 * delegates to `Note.set_tags` / `Note.set_status` (the same verbs the CLI uses,
 * per the Python==UI invariant). Each save realigns local state with the
 * server-returned summary; a failed save surfaces an inline error and leaves the
 * prior state intact.
 */
export const DocumentControls = ({
  relPath,
  placement = "block",
}: {
  relPath: string;
  /** ``title`` sits after the page heading; ``block`` is the standalone row. */
  placement?: "block" | "title";
}): JSX.Element | null => {
  const queryClient = useQueryClient();
  const listQuery = useKnowledgeListQuery();
  const [tags, setTags] = useState<string[]>([]);
  const [status, setStatus] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tagInput, setTagInput] = useState("");
  const summary = listQuery.data?.notes.find((note) => note.relPath === relPath) ?? null;

  useEffect(() => {
    setError(null);
    setTags(summary?.tags ?? []);
    setStatus(summary?.status ?? null);
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
      const updated = await knowledgeApi.updateDocMeta(relPath, patch);
      setTags(updated.tags ?? []);
      setStatus(updated.status ?? null);
      await queryClient.invalidateQueries({ queryKey: knowledgeKeys.lists() });
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

  if (isTexDocument(relPath)) return null;

  if (listQuery.error) {
    const message =
      listQuery.error instanceof Error ? listQuery.error.message : "Failed to load doc metadata.";
    return <p className="text-label text-destructive">{message}</p>;
  }
  if (listQuery.isPending) {
    return <p className="text-micro text-muted-foreground">Loading…</p>;
  }

  const tagChips = tags.map((tag) => (
    <WorkbenchTag key={tag} meaning="metadata" className="gap-1 px-2 py-0 text-micro font-medium">
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
  ));
  const addTagField = (
    <>
      <Input
        value={tagInput}
        onChange={(event) => setTagInput(event.target.value)}
        onKeyDown={onTagKeyDown}
        placeholder="Add tag…"
        aria-label="Add tag"
        className="h-control-compact w-28 text-label"
        disabled={saving}
      />
      <WorkbenchIconAction
        label="Add tag"
        onClick={() => addTag(tagInput)}
        disabled={saving || tagInput.trim().length === 0}
      >
        <Plus className="size-icon-sm" />
      </WorkbenchIconAction>
    </>
  );

  if (placement === "title") {
    return (
      <div className="flex min-w-0 flex-wrap items-center gap-1">
        {status ? <StatusBadge status={status} size="sm" /> : null}
        {tagChips}
        {addTagField}
        {error ? <span className="text-micro text-destructive">{error}</span> : null}
      </div>
    );
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
        <Tag className="size-icon-sm text-muted-foreground" />
        {tagChips}
        {addTagField}
      </div>
      {error ? <p className="text-micro text-destructive">{error}</p> : null}
    </div>
  );
};

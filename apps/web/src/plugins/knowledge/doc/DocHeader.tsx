/**
 * The head of a knowledge page (L10), as MkDocs Material draws it: tag pills
 * above a light 34px title, then one muted line — the class word in the class
 * accent, then the document's status. Tags are added with + and removed with
 * the ✕ a pill shows on hover.
 */

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, X } from "lucide-react";
import { type JSX, type KeyboardEvent, useState } from "react";
import { knowledgeApi } from "@/api";
import { knowledgeKeys } from "../queries";

const TagPill = ({
  tag,
  onRemove,
}: {
  tag: string;
  onRemove: (() => void) | null;
}): JSX.Element => (
  <span className="group/tag inline-flex h-6 items-center gap-1 rounded-full bg-doc-accent-wash px-3 text-label text-doc-accent">
    #{tag}
    {onRemove ? (
      <button
        type="button"
        aria-label={`Remove tag ${tag}`}
        title={`Remove tag ${tag}`}
        onClick={onRemove}
        className="-mr-1 hidden size-4 items-center justify-center rounded-full group-hover/tag:inline-flex focus-visible:inline-flex"
      >
        <X aria-hidden className="size-3" />
      </button>
    ) : null}
  </span>
);

const TagAdder = ({ onAdd }: { onAdd: (tag: string) => void }): JSX.Element => {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState("");
  const commit = (): void => {
    const tag = value.trim().replace(/^#/, "");
    if (tag) onAdd(tag);
    setValue("");
    setOpen(false);
  };
  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>): void => {
    if (event.key === "Enter") commit();
    if (event.key === "Escape") {
      setValue("");
      setOpen(false);
    }
  };
  if (!open) {
    return (
      <button
        type="button"
        aria-label="Add tag"
        title="Add tag"
        onClick={() => setOpen(true)}
        className="inline-flex size-6 items-center justify-center rounded-full text-muted-foreground hover:bg-doc-accent-wash hover:text-doc-accent"
      >
        <Plus aria-hidden className="size-icon-sm" />
      </button>
    );
  }
  return (
    <input
      // biome-ignore lint/a11y/noAutofocus: opened by the + the user just pressed
      autoFocus
      aria-label="New tag"
      value={value}
      onChange={(event) => setValue(event.target.value)}
      onKeyDown={onKeyDown}
      onBlur={commit}
      className="h-6 w-32 rounded-full border border-input bg-surface px-3 text-label outline-none"
    />
  );
};

export interface DocHeaderProps {
  relPath: string;
  title: string;
  cls: string;
  status: string | null;
  tags: readonly string[];
  writable: boolean;
}

export const DocHeader = ({
  relPath,
  title,
  cls,
  status,
  tags,
  writable,
}: DocHeaderProps): JSX.Element => {
  const queryClient = useQueryClient();
  const setTags = useMutation({
    mutationFn: (next: string[]) => knowledgeApi.updateDocMeta(relPath, { tags: next }),
    onSettled: () => queryClient.invalidateQueries({ queryKey: knowledgeKeys.lists() }),
  });
  const pending = setTags.isPending && setTags.variables ? setTags.variables : tags;
  const remove = (tag: string): void => setTags.mutate(pending.filter((item) => item !== tag));
  const add = (tag: string): void => {
    if (!pending.includes(tag)) setTags.mutate([...pending, tag]);
  };

  return (
    <header className="mb-6 flex flex-col gap-3">
      {pending.length > 0 || writable ? (
        <div className="flex flex-wrap items-center gap-2">
          {pending.map((tag) => (
            <TagPill key={tag} tag={tag} onRemove={writable ? () => remove(tag) : null} />
          ))}
          {writable ? <TagAdder onAdd={add} /> : null}
        </div>
      ) : null}
      <div className="flex flex-col gap-1">
        <h1 className="text-doc-title font-light tracking-tight text-foreground">{title}</h1>
        <p className="flex items-center gap-2 text-body text-muted-foreground">
          <span className="font-semibold text-doc-accent">{cls}</span>
          {status ? (
            <>
              <span aria-hidden>·</span>
              <span>{status}</span>
            </>
          ) : null}
        </p>
      </div>
      {setTags.isError ? (
        <p role="alert" className="text-label text-status-failed">
          {setTags.error instanceof Error ? setTags.error.message : "Couldn't save the tags."}
        </p>
      ) : null}
    </header>
  );
};

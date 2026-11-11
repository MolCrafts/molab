import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useId, useState } from "react";
import { ApiError } from "@/api/generated/core/ApiError";
import { type DocRelationUpdate, type EmbedRole, knowledgeApi } from "@/api/knowledge";
import { knowledgeKeys, knowledgeListQueryOptions } from "./queries";

const roles: { value: EmbedRole; label: string }[] = [
  { value: "derived_from", label: "Derived from" },
  { value: "cites", label: "Cites" },
  { value: "supports", label: "Supports" },
  { value: "contradicts", label: "Contradicts" },
  { value: "supersedes", label: "Supersedes" },
  { value: "records", label: "Records" },
  { value: "references", label: "References" },
];

/** Inline authoring writes the source document; the graph is always derived. */
export function KnowledgeRelationEditor({
  path,
  readOnly = false,
}: {
  path: string;
  readOnly?: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const [target, setTarget] = useState("");
  const [role, setRole] = useState<EmbedRole>("references");
  const [text, setText] = useState("");
  const [notice, setNotice] = useState("");
  const listId = useId();
  const queryClient = useQueryClient();
  const queryKey = [...knowledgeKeys.all, "relations", path];
  const relations = useQuery({
    queryKey,
    queryFn: () => knowledgeApi.getDocRelations(path),
    enabled: expanded,
  });
  const documents = useQuery({ ...knowledgeListQueryOptions(), enabled: expanded });
  const mutation = useMutation({
    mutationFn: (update: DocRelationUpdate) => knowledgeApi.updateDocRelation(path, update),
    onSuccess: async (data, update) => {
      queryClient.setQueryData(queryKey, data);
      if (update.action === "add") {
        setTarget("");
        setText("");
      }
      setNotice("Saved to document.");
      await queryClient.invalidateQueries({ queryKey: knowledgeKeys.all });
    },
    onError: () => setNotice(""),
  });
  const conflict = mutation.error instanceof ApiError && mutation.error.status === 409;
  const apiDetail =
    mutation.error instanceof ApiError && typeof mutation.error.body?.detail === "string"
      ? mutation.error.body.detail
      : "";
  const failure = conflict
    ? "This document changed. Reload its relations before editing again."
    : apiDetail || (mutation.error instanceof Error ? mutation.error.message : "");
  const disabled = readOnly || mutation.isPending || !relations.data || conflict;
  const webTarget = target.trim().startsWith("http://") || target.trim().startsWith("https://");
  const availableRoles = webTarget
    ? roles.filter((option) => ["cites", "derived_from", "references"].includes(option.value))
    : roles;

  return (
    <section className="tw-section tw-relation-editor" aria-label="Edit document relations">
      <button
        className="tw-link"
        type="button"
        aria-expanded={expanded}
        onClick={() => setExpanded(!expanded)}
      >
        {expanded ? "Close relation editor" : "Edit relations"}
      </button>
      {expanded && (
        <>
          <p className="tw-hint">
            Relations are links in this document. Inline text stays when a link is removed.
          </p>
          {readOnly && <p className="tw-hint">This workspace is read-only.</p>}
          {relations.isLoading && <p className="tw-muted">Loading relations…</p>}
          {relations.error && (
            <p role="alert" className="tw-red">
              Could not load relations.
            </p>
          )}
          {relations.data?.relations.map((link) => (
            <div className="tw-relation-row" key={link.id}>
              <div>
                <strong>{link.label || link.target}</strong>
                <p className="tw-path">{link.target}</p>
              </div>
              <div className="tw-row tw-wrap">
                <select
                  className="tw-relation-input"
                  value={link.role}
                  disabled={disabled}
                  aria-label={`Relation type for ${link.label || link.target}`}
                  onChange={(event) =>
                    mutation.mutate({
                      action: "replace",
                      id: link.id,
                      role: event.target.value as EmbedRole,
                      ifMatch: relations.data.digest,
                    })
                  }
                >
                  {roles
                    .filter(
                      (option) =>
                        link.kind !== "external" ||
                        ["cites", "derived_from", "references"].includes(option.value),
                    )
                    .map((option) => (
                      <option value={option.value} key={option.value}>
                        {option.label}
                      </option>
                    ))}
                </select>
                <button
                  type="button"
                  className="tw-link tw-red"
                  disabled={disabled}
                  aria-label={`Remove relation to ${link.label || link.target}`}
                  onClick={() =>
                    mutation.mutate({
                      action: "remove",
                      id: link.id,
                      ifMatch: relations.data.digest,
                    })
                  }
                >
                  Remove
                </button>
              </div>
            </div>
          ))}
          {relations.data?.relations.length === 0 && (
            <p className="tw-muted">No outgoing relations.</p>
          )}
          {!readOnly && (
            <form
              className="tw-relation-fields"
              onSubmit={(event) => {
                event.preventDefault();
                if (!relations.data || !target.trim() || disabled) return;
                mutation.mutate({
                  action: "add",
                  target: target.trim(),
                  role,
                  ...(text.trim() ? { text: text.trim() } : {}),
                  ifMatch: relations.data.digest,
                });
              }}
            >
              <label>
                Target
                <input
                  className="tw-relation-input"
                  list={listId}
                  value={target}
                  disabled={disabled}
                  placeholder="Document, molab: reference or https://…"
                  required
                  onChange={(event) => {
                    setTarget(event.target.value);
                    if (
                      event.target.value.startsWith("http") &&
                      !["cites", "derived_from", "references"].includes(role)
                    ) {
                      setRole("references");
                    }
                  }}
                />
              </label>
              <datalist id={listId}>
                {documents.data?.notes
                  .filter((note) => note.relPath !== path)
                  .map((note) => (
                    <option key={note.relPath} value={note.relPath}>
                      {note.title || note.name}
                    </option>
                  ))}
              </datalist>
              <label>
                Relation
                <select
                  className="tw-relation-input"
                  value={role}
                  disabled={disabled}
                  onChange={(event) => setRole(event.target.value as EmbedRole)}
                >
                  {availableRoles.map((option) => (
                    <option value={option.value} key={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Label <span className="tw-muted">(optional)</span>
                <input
                  className="tw-relation-input"
                  value={text}
                  disabled={disabled}
                  onChange={(event) => setText(event.target.value)}
                />
              </label>
              <button className="tw-button" type="submit" disabled={disabled || !target.trim()}>
                Add relation
              </button>
            </form>
          )}
          {mutation.isPending && (
            <p className="tw-hint" role="status">
              Saving relation…
            </p>
          )}
          {notice && (
            <p className="tw-hint" role="status">
              {notice}
            </p>
          )}
          {failure && (
            <p className="tw-red" role="alert">
              {failure}
            </p>
          )}
          {conflict && (
            <button
              type="button"
              className="tw-button"
              onClick={async () => {
                const result = await relations.refetch();
                if (!result.error) mutation.reset();
              }}
            >
              Reload relations
            </button>
          )}
        </>
      )}
    </section>
  );
}

/** A read-only view of the actual Git file; working-copy comparison comes from difflib. */
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { historyApi } from "@/api/history";
import { knowledgeKeys } from "./queries";

export function KnowledgeHistory({ path }: { path: string }) {
  const [open, setOpen] = useState(false);
  const [commit, setCommit] = useState<string | null>(null);
  const [mode, setMode] = useState<"diff" | "body">("diff");
  const query = useQuery({
    queryKey: [...knowledgeKeys.all, "history", path, commit],
    queryFn: () => historyApi.document(path, commit),
    enabled: open,
    staleTime: 30_000,
  });
  return (
    <section className="tw-section" aria-label="Document history">
      <button
        type="button"
        className="tw-link"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        {open ? "▾" : "▸"} Git history
      </button>
      {open && (
        <div className="tw-history">
          {query.isPending && <p className="tw-muted">Reading document history…</p>}
          {query.error && (
            <p className="tw-red" role="alert">
              {query.error instanceof Error ? query.error.message : "Could not read history"}
            </p>
          )}
          {query.data && (
            <>
              {!query.data.available ? (
                <p className="tw-muted">Git history is unavailable in this workspace.</p>
              ) : query.data.revisions.length === 0 ? (
                <p className="tw-muted">This document has no Git revisions yet.</p>
              ) : (
                <>
                  <p className="tw-hint">
                    Latest {query.data.revisions.length} revisions · compare any version with the
                    current working file, including metadata.
                  </p>
                  <select
                    aria-label="Document revision"
                    value={commit ?? ""}
                    onChange={(event) => setCommit(event.target.value || null)}
                  >
                    <option value="">Choose a revision</option>
                    {query.data.revisions.map((revision) => (
                      <option key={revision.commit} value={revision.commit}>
                        {revision.commit.slice(0, 8)} · {revision.occurred_at.slice(0, 10)} ·{" "}
                        {revision.summary}
                      </option>
                    ))}
                  </select>
                </>
              )}
              {query.data.body !== null && query.data.body !== undefined && (
                <>
                  <div className="tw-row">
                    <button
                      type="button"
                      className="tw-link"
                      aria-pressed={mode === "diff"}
                      onClick={() => setMode("diff")}
                    >
                      Compare with working copy
                    </button>
                    <button
                      type="button"
                      className="tw-link"
                      aria-pressed={mode === "body"}
                      onClick={() => setMode("body")}
                    >
                      Read version
                    </button>
                  </div>
                  {mode === "body" ? (
                    <pre className="tw-doc">{query.data.body}</pre>
                  ) : query.data.diff ? (
                    <pre className="tw-doc tw-history-diff">
                      {query.data.diff.split("\n").map((line, index) => (
                        <span
                          // biome-ignore lint/suspicious/noArrayIndexKey: lines are positions in an immutable Git diff
                          key={`${index}:${line}`}
                          className={
                            line.startsWith("+") ? "tw-green" : line.startsWith("-") ? "tw-red" : ""
                          }
                        >
                          {line}
                          {"\n"}
                        </span>
                      ))}
                    </pre>
                  ) : (
                    <p className="tw-muted">No changes from this version.</p>
                  )}
                </>
              )}
            </>
          )}
        </div>
      )}
    </section>
  );
}

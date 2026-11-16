/**
 * A document's git versions in the research panel. Each opens the document
 * page at that version, where it is read and compared (`DocVersions`); there
 * is one version UI, not a second raw view here.
 */
import { useState } from "react";
import { useNavigationState } from "@/app/state/useNavigationState";
import type { RendererSnapshot } from "@/app/types";
import { versionAgent, versionEvent, versionToOpen } from "./knowledgeVersions";
import { useKnowledgeVersionsQuery } from "./queries";

const shortDate = (iso: string): string =>
  new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });

export function KnowledgeHistory({ path, snapshot }: { path: string; snapshot: RendererSnapshot }) {
  const nav = useNavigationState(snapshot);
  const [open, setOpen] = useState(false);
  const query = useKnowledgeVersionsQuery(path, open);
  const history = query.data;
  const openVersion = (version: number | null): void =>
    nav.setSelection({
      objectType: "knowledge",
      objectId: path,
      ...(version === null ? {} : { version }),
    });
  return (
    <section className="tw-section" aria-label="Document versions">
      <button
        type="button"
        className="tw-link"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        {open ? "▾" : "▸"} Versions
        {history?.available && history.versions.length > 0 ? ` · ${history.versions.length}` : ""}
      </button>
      {open && (
        <div className="tw-history">
          {query.isPending && <p className="tw-muted">Reading document versions…</p>}
          {query.error && (
            <p className="tw-muted">
              {query.error instanceof Error ? query.error.message : "Versions are unavailable."}
            </p>
          )}
          {history &&
            (!history.available ? (
              <p className="tw-muted">Versions need a local workspace with git.</p>
            ) : (
              <>
                {history.uncommitted && (
                  <div className="tw-kv">
                    <span className="tw-muted">Uncommitted changes</span>
                    <button type="button" className="tw-link" onClick={() => openVersion(null)}>
                      Working copy ›
                    </button>
                  </div>
                )}
                {history.versions.length === 0 && (
                  <p className="tw-muted">This document has no committed version yet.</p>
                )}
                {history.versions.map((version) => {
                  const agent = versionAgent(version);
                  return (
                    <div className="tw-kv" key={version.commit} title={version.summary}>
                      <span>
                        {shortDate(version.occurred_at)} · {versionEvent(version)}
                        {agent ? ` · ${agent}` : ""}
                      </span>
                      <button
                        type="button"
                        className="tw-link"
                        onClick={() => openVersion(versionToOpen(history, version.number))}
                      >
                        v{version.number} ›
                      </button>
                    </div>
                  );
                })}
              </>
            ))}
        </div>
      )}
    </section>
  );
}

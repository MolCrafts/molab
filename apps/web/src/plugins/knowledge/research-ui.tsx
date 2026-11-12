/** Research map UI primitives and floating panels. */
import { type ButtonHTMLAttributes, type ReactNode, useMemo, useState } from "react";
import type { EntityCard } from "@/api/generated/models/EntityCard";
import type { KnowledgeGraphResponse } from "@/api/generated/models/KnowledgeGraphResponse";
import { usePreview } from "@/app/preview/PreviewContext";
import type { RendererSnapshot } from "@/app/types";
import { buildMolabRefIndex } from "@/lib/entity-linkify";
import { resolveDocRef } from "./doc/RefChip";
import { KnowledgeEvidence } from "./KnowledgeEvidence";
import { KnowledgeHistory } from "./KnowledgeHistory";
import { KnowledgeRelationEditor } from "./KnowledgeRelationEditor";
import { knowledgeChangeImpact } from "./knowledge-audit";
import type { knowledgeLineage } from "./knowledge-map";
import { useKnowledgeNoteQuery } from "./queries";
import workflowIcon from "./research-assets/workflow.svg";
import type { MapNode, ResearchMap } from "./research-map";
import { useHostExpansion, useRefExpansion } from "./useKnowledgeEntities";

const reasoningLabels: Record<string, Record<string, string>> = {
  Hypothesis: {
    open: "Being tested",
    supported: "Supported",
    refuted: "Refuted",
    unsettled: "Unsettled",
  },
};
const reasoningTones: Record<string, Record<string, string>> = {
  Hypothesis: { open: "blue", supported: "green", refuted: "red", unsettled: "muted" },
};
export const reasoningLabel = (node: MapNode) =>
  reasoningLabels[node.cls]?.[node.state ?? ""] ?? node.state;
export const reasoningTone = (node: MapNode) =>
  reasoningTones[node.cls]?.[node.state ?? ""] ?? "muted";
export const Button = ({
  children,
  tone,
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { tone?: string }) => (
  <button
    type="button"
    className={`tw-button ${tone ? `tw-button-${tone}` : ""} ${className}`}
    {...props}
  >
    {children}
  </button>
);
export const Tag = ({ tone = "muted", children }: { tone?: string; children: ReactNode }) => (
  <span className={`tw-tag tw-${tone}`}>{children}</span>
);
export const Dot = ({ tone = "muted", shape = "dot" }: { tone?: string; shape?: string }) => (
  <i className={`tw-${shape} tw-bg-${tone}`} aria-hidden="true" />
);
export const Card = ({
  className = "",
  label,
  children,
}: {
  className?: string;
  label: string;
  children: ReactNode;
}) => (
  <section className={`tw-card ${className}`} aria-label={label}>
    {children}
  </section>
);
export const Empty = ({ title, children }: { title: string; children: ReactNode }) => (
  <div className="tw-empty">
    <img className="tw-icon" src={workflowIcon} alt="" draggable="false" />
    <h2>{title}</h2>
    <p>{children}</p>
  </div>
);
const Head = ({
  tag,
  tone,
  title,
  onClose,
}: {
  tag: string;
  tone: string;
  title: string;
  onClose: () => void;
}) => (
  <>
    <div className="tw-row">
      <Tag tone={tone}>{tag}</Tag>
      <span className="tw-grow" />
      <button type="button" className="tw-close" aria-label="Close details" onClick={onClose}>
        ✕
      </button>
    </div>
    <h2 className="tw-serif">{title}</h2>
  </>
);
const Section = ({ title, children }: { title: string; children: ReactNode }) => (
  <div className="tw-section">
    <h3 className="tw-eyebrow">{title}</h3>
    {children}
  </div>
);
const Link = ({ children, onClick }: { children: ReactNode; onClick: () => void }) => (
  <button type="button" className="tw-link" onClick={onClick}>
    {children}
  </button>
);

const roleLabels: Record<string, string> = {
  derived_from: "Derived from",
  supersedes: "Supersedes",
  supports: "Supports",
  contradicts: "Contradicts",
  cites: "Cites",
  records: "Records",
  references: "Refers to",
};
const backLabels: Record<string, string> = {
  derived_from: "Source of",
  supersedes: "Superseded by",
  supports: "Supported by",
  contradicts: "Contradicted by",
  cites: "Cited by",
  records: "Recorded by",
  references: "Referred to by",
};

/** The arrows at one document: what it refers to and what refers to it, each with the role the link declares. */
function Links({
  node,
  map,
  onOpen,
  onOpenOutside,
  snapshot,
  cards,
}: {
  node: MapNode;
  map: ResearchMap;
  onOpen: (id: string) => void;
  onOpenOutside: (id: string) => void;
  snapshot: RendererSnapshot;
  cards: readonly EntityCard[];
}) {
  const preview = usePreview();
  const [allSources, setAllSources] = useState(false);
  const [evidence, setEvidence] = useState<EntityCard | null>(null);
  const projectId =
    snapshot.projects.find((project) =>
      map.nodes.some((item) => item.id.startsWith(`${project.path}/`)),
    )?.id ?? "";
  const refIndex = useMemo(() => buildMolabRefIndex(snapshot), [snapshot]);
  const title = (id: string) => map.nodes.find((entry) => entry.id === id)?.title ?? id;
  const refersTo = map.edges.filter((edge) => edge.from === node.id);
  const referredBy = map.edges.filter((edge) => edge.to === node.id);
  return (
    <>
      {refersTo.length > 0 && (
        <Section title={`Refers to · ${refersTo.length}`}>
          {refersTo.map((edge) => (
            <div className="tw-kv" key={`${edge.to}:${edge.role}`}>
              <span>{roleLabels[edge.role] ?? edge.role}</span>
              <Link onClick={() => onOpen(edge.to)}>{title(edge.to)} ›</Link>
            </div>
          ))}
        </Section>
      )}
      {referredBy.length > 0 && (
        <Section title={`Referred to by · ${referredBy.length}`}>
          {referredBy.map((edge) => (
            <div className="tw-kv" key={`${edge.from}:${edge.role}`}>
              <span>{backLabels[edge.role] ?? edge.role}</span>
              <Link onClick={() => onOpen(edge.from)}>{title(edge.from)} ›</Link>
            </div>
          ))}
        </Section>
      )}
      {node.refs.length > 0 && (
        <Section title={`Workspace and outside · ${node.refs.length}`}>
          {(allSources ? node.refs : node.refs.slice(0, 8)).map((ref) => {
            const card = cards.find((card) => card.ref === ref.target);
            const hit = ref.kind === "ref" ? resolveDocRef(ref.target, refIndex, snapshot) : null;
            return (
              <div className="tw-kv" key={`${ref.target}:${ref.role}`}>
                <span>{roleLabels[ref.role] ?? ref.role}</span>
                {ref.kind === "document" ? (
                  <Link onClick={() => onOpenOutside(ref.target)}>{ref.target} ↗</Link>
                ) : ref.kind === "external" && /^https?:\/\//.test(ref.target) ? (
                  <a className="tw-link" href={ref.target} target="_blank" rel="noreferrer">
                    {ref.target} ↗
                  </a>
                ) : card && ["asset", "run"].includes(card.kind) && !card.missing ? (
                  <Link onClick={() => setEvidence(card)}>{card.title} ›</Link>
                ) : hit?.target ? (
                  <Link
                    onClick={() => {
                      const target = hit.target;
                      if (target) preview.open(target);
                    }}
                  >
                    {hit.resolved.label} ↗
                  </Link>
                ) : (
                  <span className={`tw-path ${ref.kind === "missing" ? "tw-amber" : ""}`}>
                    {ref.target}
                    {ref.kind === "missing" ? " · Missing document" : ""}
                  </span>
                )}
              </div>
            );
          })}
          {node.refs.length > 8 && (
            <button
              type="button"
              className="tw-link"
              aria-expanded={allSources}
              onClick={() => setAllSources((value) => !value)}
            >
              {allSources ? "Show fewer sources" : `Show all ${node.refs.length} sources`}
            </button>
          )}
        </Section>
      )}
      {refersTo.length + referredBy.length + node.refs.length === 0 && (
        <p className="tw-muted">
          This document refers to nothing, and nothing on the map refers to it.
        </p>
      )}
      {evidence && (
        <KnowledgeEvidence
          key={evidence.ref ?? evidence.id}
          card={evidence}
          projectId={
            snapshot.assets.find((asset) => asset.id === evidence.id)?.projectId ?? projectId
          }
          snapshot={snapshot}
          onClose={() => setEvidence(null)}
        />
      )}
    </>
  );
}

/** A preview of one knowledge document: what its fields say, the references it makes and receives, and its text. */
export function DocumentPanel({
  node,
  map,
  graph,
  snapshot,
  lineage,
  onOpenOutside,
  onOpen,
  onOpenPage,
  onFocus,
  onHide,
  canHide,
  onClose,
}: {
  node: MapNode;
  map: ResearchMap;
  graph: KnowledgeGraphResponse;
  snapshot: RendererSnapshot;
  lineage: ReturnType<typeof knowledgeLineage>;
  onOpenOutside: (id: string) => void;
  onOpen: (id: string) => void;
  onOpenPage: () => void;
  onFocus: () => void;
  onHide: () => void;
  canHide: boolean;
  onClose: () => void;
}) {
  const query = useKnowledgeNoteQuery(node.id);
  const body = query.data?.body ?? null;
  const error = query.error instanceof Error ? query.error.message : "";
  useHostExpansion([graph.nodes.find((doc) => doc.relPath === node.id)?.hostPath ?? ""], snapshot);
  useRefExpansion(
    `${body ?? ""}\n${(query.data?.cards ?? []).map((card) => card.ref ?? "").join("\n")}`,
    snapshot,
  );
  const impact = useMemo(() => knowledgeChangeImpact(graph, node.id), [graph, node.id]);
  return (
    <Card className="tw-panel tw-panel-wide" label={node.cls}>
      <Head
        tag={node.cls}
        tone={node.state ? reasoningTone(node) : "ink"}
        title={node.title}
        onClose={onClose}
      />
      <p className="tw-path">{node.id}</p>
      <div className="tw-row tw-wrap">
        <Button onClick={onOpenPage}>Open page ↗</Button>
        <Button onClick={onFocus}>Focus here</Button>
        <Button
          onClick={onHide}
          disabled={!canHide}
          title={canHide ? "Hide from this view" : "The focus anchor stays visible"}
        >
          Hide node
        </Button>
      </div>
      {node.state && <p className={`tw-${reasoningTone(node)}`}>{reasoningLabel(node)}</p>}
      {[
        { title: "Origins", entries: lineage.ancestors },
        { title: "Used by", entries: lineage.descendants },
      ].map(
        ({ title, entries }) =>
          entries.length > 0 && (
            <Section key={title} title={`${title} · ${entries.length}`}>
              {entries.map((entry) => (
                <div className="tw-kv" key={entry.id}>
                  <span
                    title={`Via ${graph.nodes.find((doc) => doc.relPath === entry.via)?.title || graph.nodes.find((doc) => doc.relPath === entry.via)?.name || entry.via}`}
                  >
                    {entry.depth} {entry.depth === 1 ? "step" : "steps"}
                  </span>
                  <Link
                    onClick={() =>
                      map.nodes.some((doc) => doc.id === entry.id)
                        ? onOpen(entry.id)
                        : onOpenOutside(entry.id)
                    }
                  >
                    {graph.nodes.find((doc) => doc.relPath === entry.id)?.title ||
                      graph.nodes.find((doc) => doc.relPath === entry.id)?.name ||
                      entry.id}{" "}
                    ›
                  </Link>
                </div>
              ))}
            </Section>
          ),
      )}
      <Links
        node={node}
        map={map}
        snapshot={snapshot}
        cards={query.data?.cards ?? []}
        onOpen={onOpen}
        onOpenOutside={onOpenOutside}
      />
      <details className="tw-section">
        <summary className="tw-link">Change impact · {impact.length}</summary>
        <p className="tw-hint">
          Review these dependants and claims if this document changes. This does not mark
          conclusions as invalid.
        </p>
        {impact.map((entry) => (
          <div className="tw-kv" key={entry.id}>
            <span>
              {entry.reasons.join(" / ")} · {entry.depth} {entry.depth === 1 ? "step" : "steps"}
            </span>
            <Link
              onClick={() =>
                map.nodes.some((item) => item.id === entry.id)
                  ? onOpen(entry.id)
                  : onOpenOutside(entry.id)
              }
            >
              {entry.title} ›
            </Link>
          </div>
        ))}
        {impact.length === 0 && (
          <p className="tw-muted">No downstream dependants in the current knowledge graph.</p>
        )}
      </details>
      {!node.id.endsWith(".tex") && <KnowledgeRelationEditor key={node.id} path={node.id} />}
      <KnowledgeHistory key={`history:${node.id}`} path={node.id} />
      {error ? (
        <p className="tw-red" role="alert">
          {error}
        </p>
      ) : body === null ? (
        <p className="tw-muted">Loading the document…</p>
      ) : (
        <pre className="tw-doc">{body}</pre>
      )}
    </Card>
  );
}

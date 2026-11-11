import type { KnowledgeGraphResponse } from "@/api/generated/models/KnowledgeGraphResponse";
import type { auditKnowledge } from "./knowledge-audit";
import { Button, Card, Tag } from "./research-ui";

/** Original Tack floating inspector; each review opens the existing document. */
export function KnowledgeAudit({
  result,
  graph,
  onSelect,
  onClose,
  loading = false,
  errors = [],
  onRetry,
}: {
  result: ReturnType<typeof auditKnowledge>;
  graph: KnowledgeGraphResponse;
  onSelect: (path: string) => void;
  onClose: () => void;
  loading?: boolean;
  errors?: readonly { path: string; error: string }[];
  onRetry?: () => void;
}) {
  const labels = new Map(graph.nodes.map((node) => [node.relPath, node.title || node.name]));
  const tones = { error: "red", review: "amber", info: "muted" };
  const severityLabels = { error: "Broken reference", review: "Review", info: "Not yet checked" };
  return (
    <Card className="tw-panel tw-panel-wide" label="Evidence audit">
      <div className="tw-row">
        <Tag tone="ink">Evidence audit</Tag>
        <span className="tw-grow" />
        <button
          type="button"
          className="tw-close"
          aria-label="Close evidence audit"
          onClick={onClose}
        >
          ✕
        </button>
      </div>
      <h2 className="tw-serif">Check the evidence</h2>
      <p className="tw-muted">
        Review declared sources, counter-evidence and replaced conclusions. Verdicts stay as
        recorded.
      </p>
      <div className="tw-row tw-wrap">
        {(["error", "review", "info"] as const).map((severity) => (
          <Tag key={severity} tone={tones[severity]}>
            {result.issues.filter((issue) => issue.severity === severity).length}{" "}
            {severityLabels[severity].toLowerCase()}
          </Tag>
        ))}
      </div>
      {loading && (
        <p className="tw-muted" role="status">
          Checking source records…
        </p>
      )}
      {errors.length > 0 && (
        <section className="tw-section" aria-label="Sources not checked">
          <h3 className="tw-eyebrow">Sources not checked · {errors.length}</h3>
          {errors.map(({ path, error }) => (
            <div key={path}>
              <button type="button" className="tw-link" onClick={() => onSelect(path)}>
                {labels.get(path) ?? path} ›
              </button>
              <p className="tw-red" role="alert">
                {error}
              </p>
            </div>
          ))}
          {onRetry && <Button onClick={onRetry}>Retry source checks</Button>}
        </section>
      )}
      {!loading &&
        errors.length === 0 &&
        result.uncheckedHypotheses.length === 0 &&
        result.issues.length === 0 && <p>No issues found in the checked relations.</p>}
      {result.issues.map((issue) => (
        <section className="tw-section" key={issue.id} aria-label={issue.title}>
          <Tag tone={tones[issue.severity]}>{severityLabels[issue.severity]}</Tag>
          <h3>{issue.title}</h3>
          <button type="button" className="tw-link" onClick={() => onSelect(issue.document)}>
            {labels.get(issue.document) ?? issue.document} ›
          </button>
          <p>{issue.detail}</p>
          {issue.target && <p className="tw-path">{issue.target}</p>}
          {issue.related.map((path) => (
            <div className="tw-kv" key={path}>
              <button type="button" className="tw-link" onClick={() => onSelect(path)}>
                {labels.get(path) ?? path} ›
              </button>
            </div>
          ))}
          <Button onClick={() => onSelect(issue.document)}>Inspect document</Button>
        </section>
      ))}
      {result.uncheckedHypotheses.length > 0 && (
        <section className="tw-section" aria-label="Hypotheses not yet checked">
          <h3 className="tw-eyebrow">
            Verdicts not yet checked · {result.uncheckedHypotheses.length}
          </h3>
          <p className="tw-muted">
            Load the hypothesis records to compare their recorded verdicts with evidence.
          </p>
          {result.uncheckedHypotheses.map((path) => (
            <div className="tw-kv" key={path}>
              <button type="button" className="tw-link" onClick={() => onSelect(path)}>
                {labels.get(path) ?? path} ›
              </button>
            </div>
          ))}
        </section>
      )}
    </Card>
  );
}

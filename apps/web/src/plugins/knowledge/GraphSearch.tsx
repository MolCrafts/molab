import { useEffect, useId, useMemo, useRef, useState } from "react";
import { searchResearchNodes } from "./graph-search";
import type { HiddenReason } from "./graph-view";
import type { MapNode } from "./research-map";
import { reasoningLabel, stageLabels } from "./research-ui";

/** A map-local navigator: the full graph stays visible while results locate its documents. */
export const GraphSearch = ({
  nodes,
  onSelect,
  hidden,
}: {
  nodes: readonly MapNode[];
  hidden: ReadonlyMap<string, readonly HiddenReason[]>;
  onSelect: (id: string) => void;
}) => {
  const id = useId();
  const input = useRef<HTMLInputElement>(null);
  const options = useRef(new Map<string, HTMLButtonElement>());
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const [index, setIndex] = useState(0);
  const results = useMemo(() => searchResearchNodes(nodes, query), [nodes, query]);
  const currentIndex = Math.min(index, Math.max(0, results.length - 1));
  const current = results[currentIndex];
  useEffect(() => {
    if (open && current) options.current.get(current.id)?.scrollIntoView({ block: "nearest" });
  }, [open, current]);
  const choose = (node: MapNode) => {
    onSelect(node.id);
    setOpen(false);
  };
  return (
    <search
      aria-label="Search project knowledge"
      className="tw-map-search"
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false);
      }}
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          event.stopPropagation();
          setOpen(false);
        } else if (event.target === input.current && ["ArrowDown", "ArrowUp"].includes(event.key)) {
          event.preventDefault();
          setOpen(true);
          const direction = event.key === "ArrowDown" ? 1 : -1;
          setIndex((value) => {
            if (!results.length) return 0;
            if (!open) return direction > 0 ? 0 : results.length - 1;
            return (value + direction + results.length) % results.length;
          });
        } else if (event.target === input.current && event.key === "Enter" && open && current) {
          event.preventDefault();
          choose(current);
        }
      }}
    >
      <div className="tw-pill tw-map-search-controls">
        <input
          ref={input}
          role="combobox"
          aria-label="Search graph"
          aria-autocomplete="list"
          aria-expanded={open}
          aria-controls={`${id}-results`}
          aria-activedescendant={open && current ? `${id}-result-${currentIndex}` : undefined}
          placeholder="Find a document…"
          value={query}
          onFocus={() => setOpen(true)}
          onChange={(event) => {
            setQuery(event.target.value);
            setIndex(0);
            setOpen(true);
          }}
        />
        {query && (
          <button
            type="button"
            aria-label="Clear graph search"
            onClick={() => {
              setQuery("");
              setIndex(0);
              input.current?.focus();
            }}
          >
            ×
          </button>
        )}
      </div>
      {open && (
        <div className="tw-card tw-map-search-results">
          <div className="tw-hint" role="status">
            {results.length} of {nodes.length} documents
          </div>
          <div id={`${id}-results`} role="listbox" aria-label="Matching knowledge documents">
            {results.map((node, resultIndex) => (
              <button
                key={node.id}
                id={`${id}-result-${resultIndex}`}
                ref={(element) => {
                  if (element) options.current.set(node.id, element);
                  else options.current.delete(node.id);
                }}
                type="button"
                role="option"
                aria-selected={node === current}
                aria-label={hidden.has(node.id) ? `Show and locate ${node.title}` : node.title}
                className="tw-map-search-result"
                onClick={() => choose(node)}
                onMouseMove={() => setIndex(resultIndex)}
              >
                <span className="tw-row">
                  <strong className="tw-grow">{node.title}</strong>
                  <span className="tw-eyebrow">{node.cls}</span>
                </span>
                {hidden.has(node.id) && (
                  <span className="tw-view-hidden-reason">
                    Hidden by{" "}
                    {hidden
                      .get(node.id)
                      ?.map(
                        (reason) =>
                          ({
                            type: "type",
                            state: "state",
                            manual: "manual hide",
                            scope: "focus range",
                          })[reason],
                      )
                      .join(", ")}{" "}
                    · Show & locate
                  </span>
                )}
                <span className="tw-hint">
                  {reasoningLabel(node) ?? stageLabels[node.status ?? ""] ?? node.host ?? node.id}
                </span>
              </button>
            ))}
          </div>
          {!results.length && (
            <p className="tw-muted">No matching documents. Try another title or path.</p>
          )}
        </div>
      )}
    </search>
  );
};

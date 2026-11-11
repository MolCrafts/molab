import { Popover, PopoverContent, PopoverTrigger } from "@molcrafts/ui";
import { ArrowLeft, ChevronDown, ChevronRight } from "lucide-react";
import { useState } from "react";
import {
  DEFAULT_GRAPH_VIEW,
  type GraphViewState,
  type projectGraphView,
  RELATION_GROUPS,
  RELATION_ROLES,
} from "./graph-view";
import type { ResearchMap } from "./research-map";
import { reasoningLabel, stageLabels } from "./research-ui";

/** One compact popover, two levels. Each page edits only its own dimension. */
export function GraphViewMenu({
  map,
  view,
  projection,
  selected,
  onChange,
}: {
  map: ResearchMap;
  view: GraphViewState;
  projection: ReturnType<typeof projectGraphView>;
  selected: string;
  onChange: (next: GraphViewState) => void;
}) {
  const [open, setOpen] = useState(false);
  const [page, setPage] = useState<"root" | "nodes" | "relations" | "scope">("root");
  const classes = [...new Set(map.nodes.map((node) => node.cls))].sort();
  const selectedNode = map.nodes.find((node) => node.id === selected);
  const focus = view.focus;
  const anchor = map.nodes.find((node) => node.id === focus?.anchor);
  const stateful = classes.flatMap((cls) => {
    const nodes = map.nodes.filter((node) => node.cls === cls && (node.state || node.status));
    return nodes.length
      ? [{ cls, states: [...new Set(nodes.map((node) => node.state ?? node.status ?? ""))] }]
      : [];
  });
  const hiddenByNode = [...projection.hidden.values()].filter((reasons) =>
    reasons.some((reason) => reason !== "scope"),
  ).length;
  const manual = map.nodes.filter((node) => view.hiddenNodes.includes(node.id));
  const roleSet = view.roles ?? RELATION_ROLES;
  const preset =
    view.roles === null
      ? "all"
      : (["lineage", "evidence", "citations"].find((_name, index) => {
          const roles = RELATION_GROUPS[index].roles.map((role) => role.value);
          return roles.length === roleSet.length && roles.every((role) => roleSet.includes(role));
        }) ?? "custom");
  const changed =
    view.hiddenClasses.length > 0 ||
    Object.values(view.hiddenStates).some((states) => states.length > 0) ||
    view.hiddenNodes.length > 0 ||
    view.roles !== null ||
    view.focus !== null;
  const toggleRoles = (roles: readonly string[], checked: boolean) => {
    const next = new Set(view.roles ?? RELATION_ROLES);
    for (const role of roles) {
      if (checked) next.add(role);
      else next.delete(role);
    }
    onChange({ ...view, roles: RELATION_ROLES.every((role) => next.has(role)) ? null : [...next] });
  };
  const label = { root: "View", nodes: "Nodes", relations: "Relations", scope: "Scope" }[page];
  return (
    <Popover
      open={open}
      onOpenChange={(value) => {
        setOpen(value);
        if (value) setPage("root");
      }}
    >
      <PopoverTrigger asChild>
        <button
          type="button"
          className="tw-map-menu-trigger"
          aria-label={changed ? "Map view · modified" : "Map view"}
        >
          View {changed && <i className="tw-view-modified" aria-hidden="true" />}
          <ChevronDown size={12} aria-hidden="true" />
        </button>
      </PopoverTrigger>
      <PopoverContent
        align="end"
        sideOffset={8}
        className="tw-map-menu tw-view-options"
        aria-label="Graph view"
        data-graph-controls="true"
        onEscapeKeyDown={(event) => {
          if (page !== "root") {
            event.preventDefault();
            setPage("root");
          }
        }}
      >
        {page === "root" ? (
          <>
            <nav aria-label="View dimensions">
              {(
                [
                  ["nodes", "Nodes", hiddenByNode ? `${hiddenByNode} hidden` : "All visible"],
                  [
                    "relations",
                    "Relations",
                    {
                      all: "All",
                      lineage: "Lineage",
                      evidence: "Evidence",
                      citations: "Citations",
                      custom: "Custom",
                    }[preset],
                  ],
                  [
                    "scope",
                    "Scope",
                    anchor
                      ? `Focused · ${view.focus?.depth === "all" ? "all hops" : `${view.focus?.depth} hop${view.focus?.depth === 1 ? "" : "s"}`}`
                      : "Project graph",
                  ],
                ] as const
              ).map(([key, title, summary]) => (
                <button
                  key={key}
                  type="button"
                  className="tw-view-dimension"
                  onClick={() => setPage(key)}
                >
                  <strong>{title}</strong>
                  <span>{summary}</span>
                  <ChevronRight size={14} aria-hidden="true" />
                </button>
              ))}
            </nav>
            <div className="tw-view-footer">
              <button
                type="button"
                className="tw-link"
                disabled={!changed}
                onClick={() => onChange(DEFAULT_GRAPH_VIEW)}
              >
                Restore default view
              </button>
            </div>
          </>
        ) : (
          <>
            <div className="tw-view-page-head">
              <button type="button" aria-label="Back to View" onClick={() => setPage("root")}>
                <ArrowLeft size={16} aria-hidden="true" />
              </button>
              <strong>{label}</strong>
            </div>
            <div className="tw-view-page">
              {page === "nodes" && (
                <>
                  <fieldset>
                    <legend>Document types</legend>
                    <button
                      type="button"
                      className="tw-link"
                      onClick={() => onChange({ ...view, hiddenClasses: [] })}
                    >
                      Show all types
                    </button>
                    {classes.map((cls) => (
                      <label className="tw-view-check" key={cls}>
                        <input
                          type="checkbox"
                          checked={!view.hiddenClasses.includes(cls)}
                          onChange={(event) =>
                            onChange({
                              ...view,
                              hiddenClasses: event.target.checked
                                ? view.hiddenClasses.filter((value) => value !== cls)
                                : [...view.hiddenClasses, cls],
                            })
                          }
                        />
                        <span>{cls}</span>
                        <small>{map.nodes.filter((node) => node.cls === cls).length}</small>
                      </label>
                    ))}
                  </fieldset>
                  {stateful.length > 0 && (
                    <details>
                      <summary>Filter by state</summary>
                      {stateful.map(({ cls, states }) => (
                        <fieldset key={cls}>
                          <legend>{cls}</legend>
                          {states.map((state) => {
                            const node = map.nodes.find(
                              (node) => node.cls === cls && (node.state ?? node.status) === state,
                            );
                            return (
                              <label key={state} className="tw-view-check">
                                <input
                                  type="checkbox"
                                  checked={!view.hiddenStates[cls]?.includes(state)}
                                  onChange={(event) =>
                                    onChange({
                                      ...view,
                                      hiddenStates: {
                                        ...view.hiddenStates,
                                        [cls]: event.target.checked
                                          ? (view.hiddenStates[cls] ?? []).filter(
                                              (value) => value !== state,
                                            )
                                          : [...(view.hiddenStates[cls] ?? []), state],
                                      },
                                    })
                                  }
                                />
                                <span>
                                  {node
                                    ? (reasoningLabel(node) ?? stageLabels[state] ?? state)
                                    : state}
                                </span>
                              </label>
                            );
                          })}
                        </fieldset>
                      ))}
                    </details>
                  )}
                  <details>
                    <summary>Hidden documents · {manual.length}</summary>
                    {manual.length ? (
                      <>
                        <button
                          type="button"
                          className="tw-link"
                          onClick={() => onChange({ ...view, hiddenNodes: [] })}
                        >
                          Restore all hidden documents
                        </button>
                        {manual.map((node) => (
                          <div className="tw-view-hidden-row" key={node.id}>
                            <span title={node.id}>{node.title}</span>
                            <button
                              type="button"
                              className="tw-link"
                              aria-label={`Restore ${node.title}`}
                              onClick={() =>
                                onChange({
                                  ...view,
                                  hiddenNodes: view.hiddenNodes.filter((id) => id !== node.id),
                                })
                              }
                            >
                              Restore
                            </button>
                          </div>
                        ))}
                      </>
                    ) : (
                      <p>No individually hidden documents. Right-click a node to hide it.</p>
                    )}
                  </details>
                  {anchor && (
                    <p className="tw-view-hint">
                      The focus anchor stays visible, including when its type or state is hidden.
                    </p>
                  )}
                </>
              )}
              {page === "relations" && (
                <>
                  <label className="tw-view-field">
                    Show relations
                    <select
                      aria-label="Relation preset"
                      value={preset}
                      onChange={(event) => {
                        const value = event.target.value;
                        if (value !== "custom")
                          onChange({
                            ...view,
                            roles:
                              value === "all"
                                ? null
                                : RELATION_GROUPS[
                                    ["lineage", "evidence", "citations"].indexOf(value)
                                  ].roles.map((role) => role.value),
                          });
                      }}
                    >
                      <option value="all">All relations</option>
                      <option value="lineage">Lineage only</option>
                      <option value="evidence">Evidence only</option>
                      <option value="citations">Citations & records only</option>
                      <option value="custom" disabled>
                        Custom
                      </option>
                    </select>
                  </label>
                  {RELATION_GROUPS.map((group) => {
                    const checked = group.roles.filter((role) =>
                      roleSet.includes(role.value),
                    ).length;
                    return (
                      <fieldset key={group.label}>
                        <legend>
                          <label className="tw-view-check">
                            <input
                              type="checkbox"
                              aria-label={`All ${group.label} relations`}
                              checked={checked === group.roles.length}
                              ref={(element) => {
                                if (element)
                                  element.indeterminate =
                                    checked > 0 && checked < group.roles.length;
                              }}
                              onChange={(event) =>
                                toggleRoles(
                                  group.roles.map((role) => role.value),
                                  event.target.checked,
                                )
                              }
                            />
                            <strong>{group.label}</strong>
                          </label>
                        </legend>
                        {group.roles.map((role) => (
                          <label key={role.value} className="tw-view-check">
                            <input
                              type="checkbox"
                              checked={roleSet.includes(role.value)}
                              onChange={(event) => toggleRoles([role.value], event.target.checked)}
                            />
                            <span>{role.label}</span>
                          </label>
                        ))}
                      </fieldset>
                    );
                  })}
                  <p className="tw-view-hint">
                    Only lines change. Documents without visible lines remain on the map.
                  </p>
                </>
              )}
              {page === "scope" && (
                <>
                  <fieldset>
                    <legend>Visible area</legend>
                    <label className="tw-view-check">
                      <input
                        type="radio"
                        name="graph-scope"
                        checked={!anchor}
                        onChange={() => onChange({ ...view, focus: null })}
                      />
                      <span>Project graph</span>
                    </label>
                    <label className="tw-view-check">
                      <input
                        type="radio"
                        name="graph-scope"
                        checked={Boolean(anchor)}
                        disabled={!anchor && !selectedNode}
                        onChange={() => {
                          if (selectedNode)
                            onChange({
                              ...view,
                              focus: { anchor: selectedNode.id, direction: "both", depth: 1 },
                            });
                        }}
                      />
                      <span>Focus on a document</span>
                    </label>
                  </fieldset>
                  {anchor && focus ? (
                    <>
                      <div className="tw-view-anchor">
                        <span>Anchor</span>
                        <strong>{anchor.title}</strong>
                      </div>
                      {selectedNode && selectedNode.id !== anchor.id && (
                        <button
                          type="button"
                          className="tw-link"
                          onClick={() =>
                            onChange({
                              ...view,
                              focus: { ...focus, anchor: selectedNode.id },
                            })
                          }
                        >
                          Use selected document as anchor
                        </button>
                      )}
                      <label className="tw-view-field">
                        Direction
                        <select
                          aria-label="Focus direction"
                          value={view.focus?.direction}
                          onChange={(event) =>
                            onChange({
                              ...view,
                              focus: {
                                ...focus,
                                direction: event.target.value as NonNullable<
                                  GraphViewState["focus"]
                                >["direction"],
                              },
                            })
                          }
                        >
                          <option value="both">Both directions</option>
                          <option value="incoming">Incoming arrows</option>
                          <option value="outgoing">Outgoing arrows</option>
                        </select>
                      </label>
                      <label className="tw-view-field">
                        Depth
                        <select
                          aria-label="Focus depth"
                          value={view.focus?.depth}
                          onChange={(event) =>
                            onChange({
                              ...view,
                              focus: {
                                ...focus,
                                depth:
                                  event.target.value === "all"
                                    ? "all"
                                    : (Number(event.target.value) as 1 | 2),
                              },
                            })
                          }
                        >
                          <option value="1">1 hop</option>
                          <option value="2">2 hops</option>
                          <option value="all">All hops</option>
                        </select>
                      </label>
                      <p className="tw-view-hint">
                        Follows the enabled relations. Previewing another document keeps this anchor
                        fixed.
                      </p>
                    </>
                  ) : (
                    <p className="tw-view-hint">
                      Select a document, then focus here. You can also right-click a node and choose
                      “Focus here”.
                    </p>
                  )}
                </>
              )}
            </div>
          </>
        )}
      </PopoverContent>
    </Popover>
  );
}

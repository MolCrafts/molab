/** Tack's research map, hosted in a Molab project editor tab without its conversation. */
import {
  EditorRenderer,
  FreeLayoutEditorProvider,
  type FreeLayoutPluginContext,
  type FreeLayoutProps,
  useListenEvents,
  usePlaygroundTools,
  type WorkflowNodeProps,
  WorkflowNodeRenderer,
} from "@flowgram.ai/free-layout-editor";
import "@flowgram.ai/free-layout-editor/index.css";
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuTrigger,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@molcrafts/ui";
import { useQueries, useQuery } from "@tanstack/react-query";
import { Ellipsis } from "lucide-react";
import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
} from "react";
import type { KnowledgeGraphResponse } from "@/api/generated/models/KnowledgeGraphResponse";
import { useNavigationState } from "@/app/state/useNavigationState";
import type { RendererProps, RendererSnapshot } from "@/app/types";
import { buildMolabRefIndex } from "@/lib/entity-linkify";
import { GraphSearch } from "./GraphSearch";
import { GraphViewMenu } from "./GraphViewMenu";
import { DEFAULT_GRAPH_VIEW, projectGraphView, revealGraphNode } from "./graph-view";
import { KnowledgeAudit } from "./KnowledgeAudit";
import { auditKnowledge, type KnowledgeAuditContext } from "./knowledge-audit";
import {
  knowledgeLineage,
  projectKnowledgeMap,
  projectResearchMap,
  toResearchGraph,
} from "./knowledge-map";
import { knowledgeClassOf } from "./knowledgeClass";
import { MAP_SHAPE_SIZE } from "./map-layout";
import { knowledgeGraphQueryOptions, knowledgeNoteQueryOptions } from "./queries";
import { type MapNode, type ResearchMap, STATEFUL } from "./research-map";
import {
  Button,
  DocumentPanel,
  Dot,
  Empty,
  NowCard,
  reasoningLabel,
  reasoningTone,
  stageLabels,
  stageTones,
  Tag,
} from "./research-ui";
import "./research-fonts.css";
import "./knowledge-relations.css";

const CanvasContext = createContext({
  selected: "",
  select: (_id: string) => {},
  open: (_id: string) => {},
  visible: (_id: string): boolean => true,
  hide: (_id: string) => {},
  focus: (_id: string) => {},
  anchor: "",
});
const PORTS = [
  { type: "output" as const, location: "left" as const },
  { type: "input" as const, location: "right" as const },
];
const registries = Object.entries(MAP_SHAPE_SIZE).map(([type, size]) => ({
  type,
  meta: { size, defaultPorts: PORTS },
}));
const pillTones: Record<string, string> = {
  Finding: "green",
  Observation: "blue",
  Literature: "muted",
};
const LINE_COLORS = {
  default: "var(--tw-faint)",
  selected: "var(--tw-blue)",
  hovered: "var(--tw-blue)",
  drawing: "var(--tw-blue)",
  flowing: "var(--tw-blue)",
  error: "var(--tw-red)",
  hidden: "transparent",
};

const Body = ({ shape, data }: { shape: string; data: MapNode }) => {
  if (shape === "question")
    return (
      <>
        <span className="tw-eyebrow tw-blue">{data.cls}</span>
        <strong className="tw-serif">{data.title}</strong>
        <small>{data.excerpt}</small>
      </>
    );
  if (shape === "card" && data.state)
    return (
      <>
        <div className="tw-row">
          <Tag tone={reasoningTone(data)}>{data.cls}</Tag>
        </div>
        <strong>{data.title}</strong>
        <small className={`tw-${reasoningTone(data)}`}>{reasoningLabel(data)}</small>
      </>
    );
  if (shape === "card")
    return (
      <>
        <div className="tw-row">
          <Tag tone={stageTones[data.status ?? ""] ?? "muted"}>{data.cls}</Tag>
        </div>
        <strong>{data.title}</strong>
        <small>
          {data.status && (
            <span className={`tw-${stageTones[data.status]}`}>
              {stageLabels[data.status]}
              {data.note && " · "}
            </span>
          )}
          {data.note}
        </small>
      </>
    );
  return (
    <div className="tw-row">
      <Dot tone={pillTones[data.cls] ?? "muted"} shape="diamond" />
      <span>{data.title}</span>
    </div>
  );
};

const RelationNode = ({ node }: WorkflowNodeProps) => {
  const { selected, select, open, visible, hide, focus, anchor } = useContext(CanvasContext);
  useListenEvents(node.onExtInfoChange);
  const data = node.getExtInfo() as MapNode;
  const shape = String(node.flowNodeType);
  return (
    <ContextMenu>
      <WorkflowNodeRenderer
        node={node}
        className={`tw-map-node tw-map-${shape} ${data.status ? `is-${data.status}` : ""} ${data.state ? `is-${data.cls.toLowerCase()}-${data.state}` : ""} ${selected === node.id ? "is-selected" : ""} ${visible(node.id) ? "" : "is-hidden"}`}
        portClassName="tw-map-port"
      >
        <ContextMenuTrigger asChild>
          <button
            type="button"
            tabIndex={visible(node.id) ? 0 : -1}
            style={{ textAlign: "left" }}
            aria-label={`${data.cls}: ${data.title}`}
            aria-pressed={selected === node.id}
            className="tw-map-content"
            title="Click to preview · double-click to open the page"
            onClick={(event) => {
              event.stopPropagation();
              select(node.id);
            }}
            onDoubleClick={(event) => {
              event.stopPropagation();
              open(node.id);
            }}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                select(node.id);
              }
            }}
          >
            <Body shape={shape} data={data} />
          </button>
        </ContextMenuTrigger>
      </WorkflowNodeRenderer>
      <ContextMenuContent className="tw-map-menu" data-graph-controls="true">
        <ContextMenuItem onSelect={() => focus(node.id)}>Focus here</ContextMenuItem>
        <ContextMenuItem disabled={anchor === node.id} onSelect={() => hide(node.id)}>
          Hide node
        </ContextMenuItem>
      </ContextMenuContent>
    </ContextMenu>
  );
};

const ZoomPill = ({ children }: { children: ReactNode }) => {
  const tools = usePlaygroundTools();
  return (
    <div className="tw-pill tw-zoom">
      <button type="button" aria-label="Zoom out" onClick={() => tools.zoomout()}>
        −
      </button>
      <span>{Math.round(tools.zoom * 100)}%</span>
      <button type="button" aria-label="Zoom in" onClick={() => tools.zoomin()}>
        +
      </button>
      <button type="button" onClick={() => tools.fitView()}>
        Fit
      </button>
      {children}
    </div>
  );
};

const MapView = ({
  map,
  graph,
  auditGraph,
  auditContext,
  snapshot,
  focus,
  onOpenPage,
}: {
  map: ResearchMap;
  graph: KnowledgeGraphResponse;
  auditGraph: KnowledgeGraphResponse;
  auditContext: KnowledgeAuditContext;
  snapshot: RendererSnapshot;
  focus?: string;
  onOpenPage: (id: string) => void;
}) => {
  const instance = useId();
  const scope = `[data-research-map=${JSON.stringify(instance)}]`;
  const [selection, setSelection] = useState({ id: focus ?? "", locate: Boolean(focus) });
  const [view, setView] = useState(DEFAULT_GRAPH_VIEW);
  const projection = useMemo(() => projectGraphView(map, view), [map, view]);
  const selected = selection.id;
  const [auditOpen, setAuditOpen] = useState(false);
  const [canvasRevision, setCanvasRevision] = useState(0);
  const select = useCallback((id: string) => {
    setAuditOpen(false);
    setSelection({ id, locate: false });
  }, []);
  const onCanvasReady = useCallback(() => setCanvasRevision((value) => value + 1), []);
  useEffect(() => {
    if (focus) setSelection({ id: focus, locate: true });
  }, [focus]);
  const locate = (id: string) => {
    const node = map.nodes.find((node) => node.id === id);
    if (!node) return;
    setView((current) => revealGraphNode(map, current, node));
    setAuditOpen(false);
    setSelection({ id, locate: true });
  };
  const hide = (id: string) => {
    if (view.focus?.anchor === id) return;
    setView((current) => ({ ...current, hiddenNodes: [...new Set([...current.hiddenNodes, id])] }));
    if (selected === id) select("");
  };
  const focusHere = (id: string) => {
    setView((current) => ({
      ...current,
      focus: {
        anchor: id,
        direction: current.focus?.direction ?? "both",
        depth: current.focus?.depth ?? 1,
      },
    }));
    select(id);
  };
  const auditNodes = useMemo(() => {
    const entitySources = new Set(
      auditGraph.edges.filter((edge) => edge.kind === "ref").map((edge) => edge.source),
    );
    return auditGraph.nodes.filter((node) => {
      const cls = knowledgeClassOf(node);
      return (
        ["Finding", "Roadmap", "Todo", "Milestone"].includes(cls) ||
        cls in STATEFUL ||
        entitySources.has(node.relPath)
      );
    });
  }, [auditGraph]);
  // Reuse cached planning records, and resolve Finding/entity source cards only on audit demand.
  const auditDetails = useQueries({
    queries: auditNodes.map((node) => ({
      ...knowledgeNoteQueryOptions(node.relPath),
      enabled: auditOpen,
    })),
  });
  const refIndex = useMemo(() => buildMolabRefIndex(snapshot), [snapshot]);
  const audit = auditOpen
    ? auditKnowledge(auditGraph, {
        records: {
          ...auditContext.records,
          ...Object.fromEntries(
            auditNodes.flatMap((node, index) =>
              auditDetails[index]?.data?.record
                ? [[node.relPath, auditDetails[index].data.record]]
                : [],
            ),
          ),
        },
        cardsByPath: {
          ...auditContext.cardsByPath,
          ...Object.fromEntries(
            auditNodes.flatMap((node, index) =>
              auditDetails[index]?.data
                ? [[node.relPath, auditDetails[index].data.cards ?? []]]
                : [],
            ),
          ),
        },
        refIndex,
      })
    : { issues: [], uncheckedHypotheses: [] };
  const auditErrors = auditNodes.flatMap((node, index) =>
    auditDetails[index]?.error
      ? [{ path: node.relPath, error: String(auditDetails[index].error) }]
      : [],
  );
  useEffect(() => {
    const clear = (event: KeyboardEvent) => {
      if (
        event.key === "Escape" &&
        !event.defaultPrevented &&
        !(event.target instanceof Element && event.target.closest("[data-graph-controls]"))
      )
        select("");
    };
    window.addEventListener("keydown", clear);
    return () => window.removeEventListener("keydown", clear);
  }, [select]);
  const editor = useRef<FreeLayoutPluginContext | null>(null);
  const built = useMemo(() => toResearchGraph(map), [map]);
  const shape = JSON.stringify([
    built.graph.nodes.map((node) => [
      node.id,
      node.type,
      node.meta.position,
      node.data.status,
      node.data.state,
    ]),
    built.graph.edges,
    [...built.roles],
  ]);
  useEffect(() => {
    const document = editor.current?.document;
    if (!document || document.disposed) return;
    for (const node of built.graph.nodes) document.getNode(node.id)?.updateExtInfo(node.data);
  }, [built]);
  const active = built.links.has(selected) ? selected : "";
  useEffect(() => {
    const ctx = editor.current;
    if (
      !selection.id ||
      !selection.locate ||
      !projection.visible.has(selection.id) ||
      !ctx ||
      ctx.document.disposed ||
      !canvasRevision
    )
      return;
    const target = ctx.document.getNode(selection.id);
    if (!target) return;
    const viewport = ctx.playground.config.getClientBounds();
    // Leave the document preview its existing space: right on desktop, bottom on narrow screens.
    ctx.playground.config.scrollToView({
      entities: [target],
      zoom: 1,
      scrollToCenter: true,
      scrollDelta: viewport.width > 900 ? { x: 242, y: 0 } : { x: 0, y: viewport.height / 4 },
    });
    setSelection((current) => (current === selection ? { ...current, locate: false } : current));
  }, [selection, canvasRevision, projection.visible]);
  const lineage = useMemo(() => knowledgeLineage(graph, active), [graph, active]);
  const node = map.nodes.find((entry) => entry.id === active);
  // The canvas keeps the complete layout and viewport. Visibility only changes
  // nodes and original edges; the engine never manufactures paths across hidden nodes.
  const arrows = [
    `${scope} .tw-map-line{display:none}${scope} .tw-map-line svg path{stroke:var(--tw-faint)!important;stroke-dasharray:3 5!important}`,
    ...projection.edges.map(
      (edge) =>
        `${scope} .tw-edge-a${built.index.get(edge.from)}.tw-edge-b${built.index.get(edge.to)}{display:block;opacity:1}`,
    ),
    ...(
      [
        ["derived_from", "ink", "none"],
        ["supersedes", "amber", "6 5"],
        ["supports", "green", "none"],
        ["contradicts", "red", "none"],
      ] as const
    )
      .filter(([role]) => view.roles === null || view.roles.includes(role))
      .map(
        ([role, color, dash]) =>
          `${scope} .tw-role-${role} svg path{stroke:var(--tw-${color})!important;stroke-dasharray:${dash}!important}`,
      ),
  ].join("");
  return (
    <CanvasContext.Provider
      value={{
        selected: active,
        select,
        open: onOpenPage,
        visible: (id) => projection.visible.has(id),
        hide,
        focus: focusHere,
        anchor: view.focus?.anchor ?? "",
      }}
    >
      <div className="tw-view" data-research-map={instance}>
        <style>{arrows}</style>
        <GraphCanvas key={shape} built={built} editor={editor} onReady={onCanvasReady}>
          <ZoomPill>
            <span className="tw-rule" aria-hidden="true" />
            <GraphViewMenu
              map={map}
              view={view}
              projection={projection}
              selected={active}
              onChange={setView}
            />
            <DropdownMenu modal={false}>
              <DropdownMenuTrigger asChild>
                <button type="button" className="tw-map-menu-trigger" aria-label="Project actions">
                  <Ellipsis size={16} aria-hidden="true" />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent
                align="end"
                sideOffset={8}
                className="tw-map-menu"
                data-graph-controls="true"
              >
                <DropdownMenuItem onSelect={() => setAuditOpen(true)}>
                  Check evidence
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </ZoomPill>
        </GraphCanvas>
        <GraphSearch nodes={map.nodes} hidden={projection.hidden} onSelect={locate} />
        {projection.visible.size === 0 && (
          <div className="tw-card tw-now" role="status">
            <h2>No visible documents</h2>
            <p>Restore the view or locate a hidden document using search.</p>
            <Button onClick={() => setView(DEFAULT_GRAPH_VIEW)}>Restore default view</Button>
          </div>
        )}
        {view.focus && (
          <div className="tw-focus-notice">
            <span>
              Focused on{" "}
              {map.nodes.find((item) => item.id === view.focus?.anchor)?.title ?? "document"}
            </span>
            <button
              type="button"
              aria-label="Exit focus"
              onClick={() => setView((current) => ({ ...current, focus: null }))}
            >
              Show project graph
            </button>
          </div>
        )}
        {auditOpen && (
          <KnowledgeAudit
            result={audit}
            graph={auditGraph}
            loading={auditDetails.some((detail) => detail.isFetching)}
            errors={auditErrors}
            onRetry={() => {
              for (const detail of auditDetails) if (detail.isError) void detail.refetch();
            }}
            onSelect={locate}
            onClose={() => setAuditOpen(false)}
          />
        )}
        {!auditOpen && !node && !view.focus && projection.visible.size > 0 && (
          <NowCard map={map} onSelect={select} />
        )}
        {!auditOpen && node && (
          <DocumentPanel
            key={node.id}
            node={node}
            map={map}
            graph={graph}
            snapshot={snapshot}
            lineage={lineage}
            onOpenOutside={onOpenPage}
            onOpen={select}
            onOpenPage={() => onOpenPage(node.id)}
            onFocus={() => focusHere(node.id)}
            onHide={() => hide(node.id)}
            canHide={view.focus?.anchor !== node.id}
            onClose={() => select("")}
          />
        )}
      </div>
    </CanvasContext.Provider>
  );
};

const GraphCanvas = ({
  built,
  editor,
  onReady,
  children,
}: {
  built: ReturnType<typeof toResearchGraph>;
  editor: { current: FreeLayoutPluginContext | null };
  onReady: () => void;
  children: ReactNode;
}) => {
  const [props] = useState<FreeLayoutProps>(() => ({
    initialData: structuredClone(built.graph),
    nodeRegistries: registries,
    readonly: true,
    background: false,
    nodeEngine: { enable: false },
    variableEngine: { enable: false },
    materials: { renderDefaultNode: RelationNode },
    lineColor: LINE_COLORS,
    isHideArrowLine: () => false,
    setLineClassName: (_ctx, line) =>
      `tw-map-line ${built.roles.get(JSON.stringify([line.from?.id, line.to?.id])) ?? "tw-role-references"}`,
    onInit: (ctx) => {
      editor.current = ctx;
    },
    onAllLayersRendered: (ctx) => {
      editor.current = ctx;
      if (ctx.document.disposed) return;
      ctx.document.getAllEdges().forEach((line) => {
        line.updateUIState({ shrink: 0, strokeWidth: 1.75 });
      });
      ctx.tools.fitView(false).then(() => {
        if (editor.current === ctx && !ctx.document.disposed) onReady();
      });
    },
    onDispose: (ctx) => {
      if (editor.current === ctx) editor.current = null;
    },
  }));
  return (
    <FreeLayoutEditorProvider {...props}>
      <EditorRenderer className="tw-editor" />
      {children}
    </FreeLayoutEditorProvider>
  );
};

export const KnowledgeRelations = ({ selection: target, snapshot }: RendererProps) => {
  const graph = useQuery(knowledgeGraphQueryOptions());
  const nav = useNavigationState(snapshot);
  const project = snapshot.projects.find(
    (project) => target.objectType === "project" && project.id === target.objectId,
  );
  const scoped = useMemo(
    () => projectKnowledgeMap(graph.data ?? { nodes: [], edges: [] }, project?.path ?? ""),
    [graph.data, project?.path],
  );
  const heads = useMemo(
    () =>
      scoped.nodes.filter(
        (node) => ["Roadmap", "Todo", "Milestone"].includes(node.cls) || node.cls in STATEFUL,
      ),
    [scoped],
  );
  const details = useQueries({ queries: heads.map((node) => knowledgeNoteQueryOptions(node.id)) });
  const records = Object.fromEntries(
    heads.flatMap((node, index) =>
      details[index]?.data?.record ? [[node.id, details[index].data?.record]] : [],
    ),
  );
  const cardsByPath = Object.fromEntries(
    heads.flatMap((node, index) =>
      details[index]?.data ? [[node.id, details[index].data.cards ?? []]] : [],
    ),
  );
  const auditGraph = useMemo(() => {
    const ids = new Set(scoped.nodes.map((node) => node.id));
    return {
      nodes: scoped.nodes,
      edges: (graph.data?.edges ?? []).filter(
        (edge) => ids.has(edge.source) && (edge.kind !== "document" || ids.has(edge.target)),
      ),
    };
  }, [scoped, graph.data]);
  const unreadable = heads.flatMap((node, index) =>
    details[index]?.error ? [{ path: node.id, error: String(details[index].error) }] : [],
  );
  const map = projectResearchMap(
    graph.data ?? { nodes: [], edges: [] },
    project?.path ?? "",
    records,
    unreadable,
  );
  const pending = graph.isPending || details.some((detail) => detail.isPending);
  return (
    <section className="tw-workspace" aria-label="Knowledge relations">
      <div className="tw-stage">
        <div className="tw-view">
          {pending ? (
            <Empty title="Loading the research map">
              Reading the knowledge documents and the links between them from Molab.
            </Empty>
          ) : graph.isError ? (
            <Empty title="The research map could not be read">
              {graph.error.message}
              <Button onClick={() => void graph.refetch()}>Retry</Button>
            </Empty>
          ) : map.nodes.length === 0 ? (
            <Empty title="No research map yet">
              This project has no Plan, Roadmap, Finding or other research document.
            </Empty>
          ) : (
            <MapView
              key={project?.id}
              map={map}
              snapshot={snapshot}
              graph={graph.data ?? { nodes: [], edges: [] }}
              auditGraph={auditGraph}
              auditContext={{ records, cardsByPath }}
              focus={target.objectType === "project" ? target.pluginFocus : undefined}
              onOpenPage={(id) => nav.setSelection({ objectType: "knowledge", objectId: id })}
            />
          )}
        </div>
      </div>
    </section>
  );
};

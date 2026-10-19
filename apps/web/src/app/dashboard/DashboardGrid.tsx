import {
  Checkbox,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@molcrafts/ui";
import { Grip, Plus, RotateCcw, Scaling, SlidersHorizontal, X } from "lucide-react";
import {
  type JSX,
  type ReactNode,
  type PointerEvent as ReactPointerEvent,
  useId,
  useRef,
  useState,
} from "react";
import {
  type ActivityOptions,
  addWidget,
  DASHBOARD_COLUMNS,
  DASHBOARD_GAP_PX,
  DASHBOARD_ROW_PX,
  type DashboardWidget,
  defaultWidgets,
  moveWidget,
  readingOrder,
  removeWidget,
  resizeWidget,
  STATUS_CHOICES,
  WIDGET_CATALOG,
  widgetDescription,
  widgetId,
  widgetTitle,
} from "@/app/dashboard/layout";
import { STATUS_GROUPS, type StatusGroupId } from "@/app/runs/statusGroups";
import { useConfirm } from "@/components/ConfirmDialog";
import { WorkbenchAction, WorkbenchIconAction } from "@/components/workbench";
import { cn } from "@/lib/utils";

interface DashboardGridProps {
  widgets: DashboardWidget[];
  arranging: boolean;
  wide: boolean;
  onWidgets: (widgets: DashboardWidget[]) => void;
  renderWidget: (widget: DashboardWidget) => ReactNode;
}

interface Gesture {
  id: string;
  mode: "move" | "resize";
  pointerId: number;
  startClientX: number;
  startClientY: number;
  origin: DashboardWidget;
}

const clamp = (value: number, min: number, max: number): number =>
  Math.min(max, Math.max(min, value));

const replaceWidget = (widgets: DashboardWidget[], next: DashboardWidget): DashboardWidget[] =>
  widgets.map((widget) => (widget.id === next.id && widget.kind === next.kind ? next : widget));

const SCROLLING_KINDS = new Set<DashboardWidget["kind"]>([
  "schedule",
  "needs-attention",
  "backends",
]);

const InstrumentFrame = ({
  widget,
  wide,
  interactive,
  action,
  onMove,
  children,
}: {
  widget: DashboardWidget;
  wide: boolean;
  interactive: boolean;
  action: ReactNode;
  onMove?: (event: ReactPointerEvent<HTMLElement>) => void;
  children: ReactNode;
}): JSX.Element => {
  const headingId = useId();
  const title = widgetTitle(widget.kind);
  const description = widgetDescription(widget.kind);
  return (
    <section
      aria-labelledby={headingId}
      className={cn(
        "flex min-h-0 min-w-0 flex-col border-t border-border",
        wide ? "h-full" : "py-6",
        interactive && "rounded-panel border-t-0 ring-1 ring-inset ring-border",
      )}
    >
      <header
        className={cn(
          "flex shrink-0 items-baseline gap-3 pt-2 pb-2",
          interactive && "cursor-grab touch-none px-3 pt-3 active:cursor-grabbing",
        )}
        onPointerDown={onMove}
      >
        <h2
          id={headingId}
          title={`${title} · ${description}`}
          className="shrink-0 text-label font-medium text-foreground"
        >
          {title}
        </h2>
        <span className="flex-1" />
        {action != null ? (
          <div
            className="flex shrink-0 items-center gap-1 self-center"
            onPointerDown={(event) => event.stopPropagation()}
          >
            {action}
          </div>
        ) : null}
      </header>
      <div
        className={cn(
          "min-h-0",
          wide && "flex-1",
          SCROLLING_KINDS.has(widget.kind) ? "overflow-auto" : "overflow-hidden",
          interactive && "px-3 pb-8",
        )}
      >
        {children}
      </div>
    </section>
  );
};

const Choice = ({
  selected,
  children,
  onClick,
}: {
  selected: boolean;
  children: ReactNode;
  onClick: () => void;
}): JSX.Element => (
  <WorkbenchAction kind={selected ? "primary" : "ghost"} size="compact" onClick={onClick}>
    {children}
  </WorkbenchAction>
);

const WidgetOptions = ({
  widget,
  onChange,
}: {
  widget: DashboardWidget;
  onChange: (widget: DashboardWidget) => void;
}): JSX.Element => {
  if (widget.kind === "execution-status" || widget.kind === "needs-attention") {
    const allowed: readonly StatusGroupId[] =
      widget.kind === "execution-status" ? STATUS_CHOICES : ["failed", "cancelled"];
    const selected: readonly StatusGroupId[] = widget.options.statuses;
    return (
      <fieldset className="space-y-2">
        <legend className="text-label text-muted-foreground">Show</legend>
        {allowed.map((status) => {
          const spec = STATUS_GROUPS.find((group) => group.id === status);
          const checked = selected.includes(status);
          const fieldId = `${widget.id}-${status}`;
          return (
            <label key={status} htmlFor={fieldId} className="flex items-center gap-2 text-label">
              <Checkbox
                id={fieldId}
                checked={checked}
                onCheckedChange={() => {
                  const next = checked
                    ? selected.filter((item) => item !== status)
                    : [...selected, status];
                  if (next.length === 0) return;
                  const ordered = allowed.filter((item) => next.includes(item));
                  if (widget.kind === "execution-status") {
                    onChange({
                      ...widget,
                      options: { statuses: [...ordered] },
                    });
                  } else {
                    onChange({
                      ...widget,
                      options: {
                        ...widget.options,
                        statuses: ordered.filter(
                          (item): item is "failed" | "cancelled" =>
                            item === "failed" || item === "cancelled",
                        ),
                      },
                    });
                  }
                }}
              />
              {spec?.label ?? status}
            </label>
          );
        })}
        {widget.kind === "needs-attention" ? (
          <LimitChoices
            value={widget.options.limit}
            choices={[3, 6, 12]}
            onChange={(limit) => onChange({ ...widget, options: { ...widget.options, limit } })}
          />
        ) : null}
      </fieldset>
    );
  }

  if (widget.kind === "activity") {
    return (
      <div className="space-y-3">
        <div className="flex flex-wrap gap-1">
          <Choice
            selected={widget.options.window === "24h"}
            onClick={() => onChange({ ...widget, options: { ...widget.options, window: "24h" } })}
          >
            24 hours
          </Choice>
          <Choice
            selected={widget.options.window === "7d"}
            onClick={() => onChange({ ...widget, options: { ...widget.options, window: "7d" } })}
          >
            7 days
          </Choice>
        </div>
        <div className="flex flex-wrap gap-1">
          {(
            [
              ["both", "Starts and finishes"],
              ["starts", "Starts"],
              ["finishes", "Finishes"],
            ] as const
          ).map(([events, label]) => (
            <Choice
              key={events}
              selected={widget.options.events === events}
              onClick={() =>
                onChange({
                  ...widget,
                  options: { ...widget.options, events } satisfies ActivityOptions,
                })
              }
            >
              {label}
            </Choice>
          ))}
        </div>
      </div>
    );
  }

  if (widget.kind === "backends") {
    return (
      <LimitChoices
        value={widget.options.limit}
        choices={[3, 6, 12]}
        noun="backends"
        onChange={(limit) => onChange({ ...widget, options: { limit } })}
      />
    );
  }

  if (widget.kind === "run-duration") {
    return (
      <div className="flex flex-wrap gap-1">
        <Choice
          selected={widget.options.scope === "finished"}
          onClick={() => onChange({ ...widget, options: { scope: "finished" } })}
        >
          Finished
        </Choice>
        <Choice
          selected={widget.options.scope === "succeeded"}
          onClick={() => onChange({ ...widget, options: { scope: "succeeded" } })}
        >
          Succeeded
        </Choice>
      </div>
    );
  }

  return (
    <LimitChoices
      value={widget.options.limit}
      choices={[4, 8, 16]}
      noun="runs"
      onChange={(limit) => onChange({ ...widget, options: { limit } })}
    />
  );
};

const LimitChoices = <T extends number>({
  value,
  choices,
  noun = "rows",
  onChange,
}: {
  value: T;
  choices: readonly T[];
  noun?: string;
  onChange: (value: T) => void;
}): JSX.Element => (
  <div className="flex flex-wrap gap-1">
    {choices.map((choice) => (
      <Choice key={choice} selected={value === choice} onClick={() => onChange(choice)}>
        {choice} {noun}
      </Choice>
    ))}
  </div>
);

export const DashboardToolbar = ({
  arranging,
  wide,
  widgets,
  onArranging,
  onWidgets,
}: {
  arranging: boolean;
  wide: boolean;
  widgets: DashboardWidget[];
  onArranging: (arranging: boolean) => void;
  onWidgets: (widgets: DashboardWidget[]) => void;
}): JSX.Element => {
  const { confirm, dialog } = useConfirm();
  const missing = WIDGET_CATALOG.filter(
    (item) => !widgets.some((widget) => widget.kind === item.kind),
  );

  const resetLayout = (): void => {
    void confirm({
      title: "Reset layout",
      description: "The custom chart layout is replaced by the default six charts.",
      confirmLabel: "Reset layout",
      cancelLabel: "Keep layout",
      destructive: true,
    }).then((accepted) => {
      if (accepted) onWidgets(defaultWidgets());
    });
  };

  return (
    <>
      {dialog}
      {wide ? (
        <div className="flex shrink-0 items-center gap-1">
          <WorkbenchAction
            aria-pressed={arranging}
            className={arranging ? "bg-interactive" : undefined}
            kind="ghost"
            size="compact"
            icon={<Grip className="size-3.5" />}
            onClick={() => onArranging(!arranging)}
          >
            {arranging ? "Done" : "Arrange"}
          </WorkbenchAction>
          {arranging ? (
            <>
              {missing.length > 0 ? (
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <WorkbenchAction
                      kind="secondary"
                      size="compact"
                      icon={<Plus className="size-3.5" />}
                    >
                      Add chart
                    </WorkbenchAction>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    {missing.map((item) => (
                      <DropdownMenuItem
                        key={item.kind}
                        onSelect={() => onWidgets(addWidget(widgets, item.kind, widgetId()))}
                      >
                        {item.title}
                      </DropdownMenuItem>
                    ))}
                  </DropdownMenuContent>
                </DropdownMenu>
              ) : null}
              <WorkbenchAction
                kind="ghost"
                size="compact"
                icon={<RotateCcw className="size-3.5" />}
                onClick={resetLayout}
              >
                Reset layout
              </WorkbenchAction>
            </>
          ) : null}
        </div>
      ) : null}
    </>
  );
};

export const DashboardGrid = ({
  widgets,
  arranging,
  wide,
  onWidgets,
  renderWidget,
}: DashboardGridProps): JSX.Element => {
  const gridRef = useRef<HTMLDivElement>(null);
  const widgetsRef = useRef(widgets);
  widgetsRef.current = widgets;
  const onWidgetsRef = useRef(onWidgets);
  onWidgetsRef.current = onWidgets;
  const [draft, setDraft] = useState<DashboardWidget[] | null>(null);
  const draftRef = useRef<DashboardWidget[] | null>(null);
  const shown = readingOrder(draft ?? widgets);
  const interactive = arranging && wide;

  const begin = (
    widget: DashboardWidget,
    mode: Gesture["mode"],
    event: ReactPointerEvent<HTMLElement>,
  ): void => {
    if (!interactive || event.button !== 0) return;
    const gesture: Gesture = {
      id: widget.id,
      mode,
      pointerId: event.pointerId,
      startClientX: event.clientX,
      startClientY: event.clientY,
      origin: widget,
    };
    const show = (next: DashboardWidget[] | null): void => {
      draftRef.current = next;
      setDraft(next);
    };
    const move = (pointer: PointerEvent): void => {
      if (pointer.pointerId !== gesture.pointerId) return;
      const width = gridRef.current?.clientWidth ?? DASHBOARD_COLUMNS;
      const column = width / DASHBOARD_COLUMNS;
      const dx = Math.round((pointer.clientX - gesture.startClientX) / column);
      const dy = Math.round((pointer.clientY - gesture.startClientY) / DASHBOARD_ROW_PX);
      const origin = gesture.origin;
      const spec = WIDGET_CATALOG.find((item) => item.kind === origin.kind);
      show(
        widgetsRef.current.map((item) => {
          if (item.id !== gesture.id) return item;
          if (gesture.mode === "move") {
            return {
              ...item,
              x: clamp(origin.x + dx, 0, DASHBOARD_COLUMNS - item.w),
              y: Math.max(0, origin.y + dy),
            };
          }
          return {
            ...item,
            w: clamp(origin.w + dx, spec?.minW ?? 1, DASHBOARD_COLUMNS),
            h: clamp(origin.h + dy, spec?.minH ?? 1, 16),
          };
        }),
      );
    };
    const up = (pointer: PointerEvent): void => {
      if (pointer.pointerId !== gesture.pointerId) return;
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      const item = (draftRef.current ?? widgetsRef.current).find(
        (entry) => entry.id === gesture.id,
      );
      show(null);
      if (!item) return;
      const source = widgetsRef.current;
      onWidgetsRef.current(
        gesture.mode === "move"
          ? moveWidget(source, item.id, item.x, item.y)
          : resizeWidget(source, item.id, item.w, item.h),
      );
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };

  return (
    <div
      ref={gridRef}
      className={cn("min-w-0", wide ? "grid" : "flex flex-col")}
      style={
        wide
          ? {
              gridTemplateColumns: `repeat(${DASHBOARD_COLUMNS}, minmax(0, 1fr))`,
              gridAutoRows: `${DASHBOARD_ROW_PX}px`,
              columnGap: DASHBOARD_GAP_PX,
              rowGap: DASHBOARD_GAP_PX,
            }
          : undefined
      }
    >
      {shown.map((widget) => (
        <div
          key={widget.id}
          className={cn(
            "relative min-h-0 min-w-0",
            !wide && "border-b border-border last:border-b-0",
          )}
          style={
            wide
              ? {
                  gridColumn: `${widget.x + 1} / span ${widget.w}`,
                  gridRow: `${widget.y + 1} / span ${widget.h}`,
                }
              : undefined
          }
        >
          <InstrumentFrame
            widget={widget}
            wide={wide}
            interactive={interactive}
            onMove={interactive ? (event) => begin(widget, "move", event) : undefined}
            action={
              interactive ? (
                <>
                  <Popover>
                    <PopoverTrigger asChild>
                      <WorkbenchIconAction label={`Edit ${widgetTitle(widget.kind)}`}>
                        <SlidersHorizontal className="size-3.5" />
                      </WorkbenchIconAction>
                    </PopoverTrigger>
                    <PopoverContent align="end" className="w-64">
                      <WidgetOptions
                        widget={widget}
                        onChange={(next) => onWidgets(replaceWidget(widgets, next))}
                      />
                    </PopoverContent>
                  </Popover>
                  <WorkbenchIconAction
                    label={`Remove ${widgetTitle(widget.kind)}`}
                    onClick={() => onWidgets(removeWidget(widgets, widget.id))}
                  >
                    <X className="size-3.5" />
                  </WorkbenchIconAction>
                </>
              ) : null
            }
          >
            {renderWidget(widget)}
          </InstrumentFrame>
          {interactive ? (
            <WorkbenchIconAction
              label={`Resize ${widgetTitle(widget.kind)}`}
              className="absolute right-1 bottom-1 cursor-nwse-resize"
              onPointerDown={(event) => {
                event.stopPropagation();
                begin(widget, "resize", event);
              }}
            >
              <Scaling className="size-3.5" aria-hidden />
            </WorkbenchIconAction>
          ) : null}
        </div>
      ))}
    </div>
  );
};

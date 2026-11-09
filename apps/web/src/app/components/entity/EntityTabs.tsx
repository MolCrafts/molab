import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@molcrafts/ui";
import { ChevronsRight } from "lucide-react";
import {
  Activity,
  type ComponentProps,
  createContext,
  type ReactNode,
  startTransition,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import { cn } from "@/lib/utils";

export interface EntityTabItem {
  value: string;
  label: ReactNode;
  disabled?: boolean;
  /** A rule before this tab: the entity's own views end, contributed views begin. */
  dividerBefore?: boolean;
}

const TabState = createContext<{
  active: string | undefined;
  visited: ReadonlySet<string>;
  select: (next: string) => void;
} | null>(null);

export const EntityTabs = ({
  className,
  value,
  defaultValue,
  onValueChange,
  ...props
}: ComponentProps<typeof Tabs>): JSX.Element => {
  const [localValue, setLocalValue] = useState(defaultValue);
  const active = value ?? localValue;
  const [visited, setVisited] = useState<ReadonlySet<string>>(
    () => new Set(active ? [active] : []),
  );
  const select = (next: string): void => {
    startTransition(() => {
      setVisited((previous) => new Set([...previous, ...(active ? [active] : []), next]));
      setLocalValue(next);
      onValueChange?.(next);
    });
  };
  return (
    <TabState.Provider value={{ active, visited, select }}>
      <Tabs
        className={cn("flex flex-1 flex-col gap-0 overflow-hidden", className)}
        value={active}
        onValueChange={select}
        {...props}
      />
    </TabState.Provider>
  );
};

interface EntityTabBarProps {
  tabs: EntityTabItem[];
  /** Right end of the row (the run's attempt, L14); hidden on phones. */
  trailing?: ReactNode;
  className?: string;
  listClassName?: string;
  triggerClassName?: string;
}

/**
 * View tabs (L00): one 32px row aligned to the 24px content gutter, VS Code
 * underline on the active view. When the views do not fit, the row still
 * scrolls and `» n` lists the ones out of sight.
 */
export const EntityTabBar = ({
  tabs,
  trailing,
  className,
  listClassName,
  triggerClassName,
}: EntityTabBarProps): JSX.Element => {
  const strip = useRef<HTMLDivElement>(null);
  const list = useRef<HTMLDivElement>(null);
  const state = useContext(TabState);
  const active = state?.active;
  const [clipped, setClipped] = useState<readonly string[]>([]);

  const measure = useCallback(() => {
    const element = strip.current;
    if (!element) return;
    const box = element.getBoundingClientRect();
    const hidden = [...element.querySelectorAll<HTMLElement>('[role="tab"]')]
      .filter((trigger) => {
        const rect = trigger.getBoundingClientRect();
        return rect.right > box.right + 1 || rect.left < box.left - 1;
      })
      .map((trigger) => trigger.dataset.value ?? "");
    setClipped((current) =>
      current.length === hidden.length && current.every((value, i) => value === hidden[i])
        ? current
        : hidden,
    );
  }, []);

  // A strip narrower than its tabs scrolls; keep the selected one in view.
  useEffect(() => {
    if (!active) return;
    const trigger = strip.current?.querySelector<HTMLElement>('[role="tab"][data-state="active"]');
    trigger?.scrollIntoView?.({ block: "nearest", inline: "nearest" });
    measure();
  }, [active, measure]);

  useEffect(() => {
    const element = strip.current;
    if (!element || typeof ResizeObserver === "undefined") return;
    // The scroller keeps its size while labels grow (counts arrive): watch the list too.
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    if (list.current) observer.observe(list.current);
    element.addEventListener("scroll", measure, { passive: true });
    return () => {
      observer.disconnect();
      element.removeEventListener("scroll", measure);
    };
  }, [measure]);

  const hiddenTabs = tabs.filter((tab) => clipped.includes(tab.value));

  return (
    <div
      className={cn(
        "flex h-8 w-full min-w-0 shrink-0 items-stretch border-b border-border bg-background pr-2",
        // Phones: the views become a bottom bar of icons (retrofit R2: icon OR text).
        "max-sm:order-last max-sm:h-toolbar max-sm:border-t max-sm:border-b-0 max-sm:pr-1",
        className,
      )}
    >
      <div
        ref={strip}
        className="flex min-w-0 flex-1 items-stretch overflow-x-auto px-4 max-sm:px-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
      >
        <TabsList
          ref={list}
          variant="line"
          className={cn(
            "flex h-full w-max min-w-0 shrink-0 justify-start gap-0 rounded-none border-0 bg-transparent p-0",
            "group-data-[orientation=horizontal]/tabs:h-full",
            listClassName,
          )}
        >
          {tabs.map((tab) => [
            tab.dividerBefore ? (
              <span
                key={`${tab.value}:divider`}
                aria-hidden
                className="mx-2 w-px flex-none self-center bg-border"
                style={{ height: 16 }}
              />
            ) : null,
            <TabsTrigger
              key={tab.value}
              value={tab.value}
              data-value={tab.value}
              disabled={tab.disabled}
              className={cn(
                "h-full min-w-0 flex-none self-stretch rounded-none border-0 bg-transparent px-2 shadow-none",
                "text-body text-muted-foreground hover:text-foreground",
                "focus-visible:border-transparent focus-visible:ring-0 focus-visible:ring-offset-0",
                "focus-visible:bg-interactive",
                "data-[state=active]:border-transparent data-[state=active]:bg-background data-[state=active]:text-foreground data-[state=active]:shadow-none",
                "group-data-[orientation=horizontal]/tabs:after:inset-x-0 group-data-[orientation=horizontal]/tabs:after:bottom-0 group-data-[orientation=horizontal]/tabs:after:h-0.5",
                "after:bg-accent data-[state=active]:after:opacity-100",
                "max-sm:min-w-12 max-sm:px-2 max-sm:data-[state=active]:text-accent max-sm:after:hidden",
                triggerClassName,
              )}
            >
              <span
                title={typeof tab.label === "string" ? tab.label : undefined}
                className="flex items-center gap-1 truncate max-sm:justify-center"
              >
                {tab.label}
              </span>
            </TabsTrigger>,
          ])}
        </TabsList>
      </div>
      {hiddenTabs.length > 0 && state ? (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              aria-label={`${hiddenTabs.length} more views`}
              className="flex flex-none items-center gap-hairline self-center rounded-action px-1 text-label text-muted-foreground hover:bg-interactive hover:text-foreground"
            >
              <ChevronsRight className="size-icon-sm" aria-hidden />
              <span className="tabular-nums">{hiddenTabs.length}</span>
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            {hiddenTabs.map((tab) => (
              <DropdownMenuItem
                key={tab.value}
                disabled={tab.disabled}
                onSelect={() => state.select(tab.value)}
              >
                {tab.label}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      ) : null}
      {trailing ? (
        <div className="flex flex-none items-center pl-2 max-sm:hidden">{trailing}</div>
      ) : null}
    </div>
  );
};

export const EntityTabContent = ({
  className,
  children,
  value,
  ...props
}: ComponentProps<typeof TabsContent>): JSX.Element | null => {
  const state = useContext(TabState);
  const active = !state || state.active === value;
  if (state && !active && !state.visited.has(value)) return null;
  return (
    <TabsContent
      className={cn(
        "m-0 flex flex-1 flex-col overflow-hidden bg-canvas p-0 data-[state=inactive]:hidden",
        className,
      )}
      value={value}
      forceMount={state ? true : undefined}
      {...props}
    >
      <Activity mode={active ? "visible" : "hidden"}>{children}</Activity>
    </TabsContent>
  );
};

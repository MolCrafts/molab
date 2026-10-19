import { Tabs, TabsContent, TabsList, TabsTrigger } from "@molcrafts/ui";
import {
  Activity,
  type ComponentProps,
  createContext,
  type ReactNode,
  startTransition,
  useContext,
  useState,
} from "react";
import { cn } from "@/lib/utils";

export interface EntityTabItem {
  value: string;
  label: ReactNode;
  disabled?: boolean;
}

const TabState = createContext<{ active: string | undefined; visited: ReadonlySet<string> } | null>(
  null,
);

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
  return (
    <TabState.Provider value={{ active, visited }}>
      <Tabs
        className={cn("flex flex-1 flex-col gap-0 overflow-hidden", className)}
        value={active}
        onValueChange={(next) => {
          startTransition(() => {
            setVisited((previous) => new Set([...previous, ...(active ? [active] : []), next]));
            setLocalValue(next);
            onValueChange?.(next);
          });
        }}
        {...props}
      />
    </TabState.Provider>
  );
};

interface EntityTabBarProps {
  tabs: EntityTabItem[];
  className?: string;
  listClassName?: string;
  triggerClassName?: string;
}

/**
 * Entity tab strip — MolVis PanelTabStrip topology, text labels (no icons).
 * Tabs share the content canvas; an underline identifies the selected view.
 */
export const EntityTabBar = ({
  tabs,
  className,
  listClassName,
  triggerClassName,
}: EntityTabBarProps): JSX.Element => {
  return (
    <div
      className={cn(
        "flex h-8 w-full min-w-0 shrink-0 items-stretch overflow-x-auto border-b border-border/60 bg-background",
        className,
      )}
    >
      <TabsList
        variant="line"
        className={cn(
          "flex h-full w-max min-w-0 gap-0 rounded-none border-0 bg-transparent p-0",
          "group-data-[orientation=horizontal]/tabs:h-full",
          listClassName,
        )}
      >
        {tabs.map((tab) => (
          <TabsTrigger
            key={tab.value}
            value={tab.value}
            disabled={tab.disabled}
            className={cn(
              "h-full min-w-0 flex-none self-stretch rounded-none border-0 bg-transparent px-3 shadow-none",
              "text-label font-medium text-muted-foreground hover:text-foreground",
              "focus-visible:border-transparent focus-visible:ring-0 focus-visible:ring-offset-0",
              "focus-visible:bg-interactive/60",
              "data-[state=active]:border-transparent data-[state=active]:bg-background data-[state=active]:text-foreground data-[state=active]:shadow-none",
              "group-data-[orientation=horizontal]/tabs:after:inset-x-3 group-data-[orientation=horizontal]/tabs:after:bottom-0 group-data-[orientation=horizontal]/tabs:after:h-0.5",
              "after:bg-accent data-[state=active]:after:opacity-100",
              triggerClassName,
            )}
          >
            <span className="truncate">{tab.label}</span>
          </TabsTrigger>
        ))}
      </TabsList>
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

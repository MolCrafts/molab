import type { JSX } from "react";

import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";

export const RUNS_TABS = ["jobs", "timeline"] as const;
export type RunsTab = (typeof RUNS_TABS)[number];

const TAB_DEFS: Array<{ id: RunsTab; label: string }> = [
  { id: "jobs", label: "Jobs" },
  { id: "timeline", label: "Timeline" },
];

export const parseRunsTab = (raw: string | null | undefined): RunsTab => {
  if (raw && (RUNS_TABS as readonly string[]).includes(raw)) {
    return raw as RunsTab;
  }
  return "jobs";
};

interface RunsTabBarProps {
  value: RunsTab;
  onChange: (next: RunsTab) => void;
  className?: string;
}

export const RunsTabBar = ({ value, onChange, className }: RunsTabBarProps): JSX.Element => (
  <Tabs value={value} onValueChange={(next) => onChange(next as RunsTab)} className={className}>
    <TabsList
      variant="line"
      className="h-10 w-full justify-start gap-4 rounded-none bg-transparent p-0 sm:gap-6 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
    >
      {TAB_DEFS.map(({ id, label }) => (
        <TabsTrigger
          key={id}
          value={id}
          className={cn(
            "h-10 flex-none rounded-none border-0 border-b border-transparent px-0 py-0",
            "text-body-lg font-medium text-muted-foreground shadow-none after:hidden",
            "data-[state=active]:border-foreground data-[state=active]:bg-transparent data-[state=active]:text-foreground data-[state=active]:shadow-none",
          )}
        >
          {label}
        </TabsTrigger>
      ))}
    </TabsList>
  </Tabs>
);

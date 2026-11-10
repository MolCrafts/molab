import type { ComponentType, JSX, ReactNode } from "react";
import { EditorActions } from "@/app/shell/editorActions";
import { PageHeader } from "@/components/layout/PageHeader";
import { cn } from "@/lib/utils";
import { EntityTabBar, EntityTabContent, EntityTabs } from "./EntityTabs";

interface EntityHeaderProps {
  icon: ComponentType<{ className?: string }>;
  title: string;
  /** Hover tooltip on the title, e.g. the untruncated source text. */
  titleTooltip?: string;
  /** Sits immediately after the title (tags, a badge). */
  afterTitle?: ReactNode;
  /** Primary / secondary controls — prefer one primary icon + a More menu. */
  actions?: ReactNode;
}

export const EntityHeader = ({
  icon: Icon,
  title,
  titleTooltip,
  afterTitle,
  actions,
}: EntityHeaderProps): JSX.Element => {
  return (
    <PageHeader
      icon={Icon}
      title={title}
      titleTooltip={titleTooltip}
      afterTitle={afterTitle}
      actions={actions}
    />
  );
};

interface KeyValueItem {
  label: string;
  value: ReactNode;
}

interface KeyValueGridProps {
  items: KeyValueItem[];
}

export const KeyValueGrid = ({ items }: KeyValueGridProps): JSX.Element => {
  return (
    <dl className="grid gap-x-6 gap-y-3 md:grid-cols-2">
      {items.map((item) => (
        <div key={item.label} className="flex min-w-0 flex-col">
          <dt className="text-label text-muted-foreground">{item.label}</dt>
          <dd className="mt-1 min-w-0 truncate text-body-lg text-foreground">{item.value}</dd>
        </div>
      ))}
    </dl>
  );
};

export interface PropertyEntry {
  label: string;
  value: ReactNode;
}

/**
 * One object's fields as a definition list: a label column, values as code. A
 * two-column `<Table>` with a header row is chrome around what is really this.
 */
export const PropertyList = ({
  entries,
  monoLabels = false,
  className,
}: {
  entries: readonly PropertyEntry[];
  /** Parameter keys read as code; field names read as words. */
  monoLabels?: boolean;
  className?: string;
}): JSX.Element => (
  <dl
    className={cn("grid gap-x-6 gap-y-2 sm:grid-cols-[minmax(0,10rem)_minmax(0,1fr)]", className)}
  >
    {entries.map((entry) => (
      <div key={entry.label} className="contents">
        <dt
          className={cn(
            "min-w-0 truncate text-label text-muted-foreground",
            monoLabels && "font-mono",
          )}
        >
          {entry.label}
        </dt>
        <dd
          className="min-w-0 break-all font-mono text-label text-foreground"
          title={typeof entry.value === "string" ? entry.value : undefined}
        >
          {entry.value}
        </dd>
      </div>
    ))}
  </dl>
);

// ── EntityPage ──────────────────────────────────────────────────────────────
//
// One template every entity viewer renders into. Owns the outer flex column,
// the header chrome (via :class:`EntityHeader`), and the tab bar + tab content
// pattern. Viewers only supply the data: header props, tab list, optional
// post-tab body. This is what keeps Workflow / Run / Asset / Project
// pages looking identical regardless of which tab is active.

export interface EntityPageTab {
  value: string;
  label: ReactNode;
  /** Tab body. Rendered inside an ``EntityTabContent`` so it owns scrolling. */
  content: ReactNode;
  /** Disable the tab trigger; used for plugin-discovered tabs that haven't loaded. */
  disabled?: boolean;
  /** A rule before this tab (the entity's own views end, plugin views begin). */
  dividerBefore?: boolean;
}

interface EntityPageProps {
  /** Right end of the view row (the run's attempt, L14). */
  tabsTrailing?: ReactNode;
  // Header — forwarded verbatim to :class:`EntityHeader`.
  icon: ComponentType<{ className?: string }>;
  title: string;
  titleTooltip?: string;
  afterTitle?: ReactNode;
  actions?: ReactNode;
  /** Facts under the title. One home for counts that used to be a subtitle sentence. */
  meta?: ReactNode;

  // Tabs — controlled (pass ``activeTab`` + ``onActiveTabChange``) or
  // uncontrolled (pass ``defaultTab``). Omit ``tabs`` entirely for a
  // header-only page (``children`` then renders directly under the header).
  tabs?: EntityPageTab[];
  activeTab?: string;
  defaultTab?: string;
  onActiveTabChange?: (value: string) => void;

  /** Body rendered when ``tabs`` is omitted. */
  children?: ReactNode;
}

export const EntityPage = ({
  icon,
  title,
  titleTooltip,
  afterTitle,
  actions,
  meta,
  tabs,
  activeTab,
  defaultTab,
  onActiveTabChange,
  tabsTrailing,
  children,
}: EntityPageProps): JSX.Element => {
  // One heading for the page. Actions stay on the editor tab row.
  return (
    <section
      aria-label={titleTooltip ?? title}
      className="flex h-full min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-background"
    >
      <EditorActions>{actions}</EditorActions>
      <EntityHeader icon={icon} title={title} titleTooltip={titleTooltip} afterTitle={afterTitle} />
      {meta ? (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 px-6 py-1 font-mono text-micro tabular-nums text-muted-foreground">
          {meta}
        </div>
      ) : null}

      {tabs && tabs.length > 0 ? (
        <EntityTabs
          value={activeTab}
          defaultValue={defaultTab ?? tabs[0]?.value}
          onValueChange={onActiveTabChange}
        >
          <EntityTabBar
            trailing={tabsTrailing}
            tabs={tabs.map(({ value, label, disabled, dividerBefore }) => ({
              value,
              label,
              disabled,
              dividerBefore,
            }))}
          />
          {tabs.map((tab) => (
            <EntityTabContent key={tab.value} value={tab.value}>
              {tab.content}
            </EntityTabContent>
          ))}
        </EntityTabs>
      ) : (
        children && <div className="flex min-h-0 flex-1 flex-col overflow-hidden">{children}</div>
      )}
    </section>
  );
};

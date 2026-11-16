/**
 * Two hops of lineage (L08 v3): inputs → the producing run → this asset →
 * the runs that use it. An import puts its source where the run would be.
 * A click on a node opens its details beside the page. Phones stack the
 * chain vertically.
 */

import type { LucideIcon } from "lucide-react";
import { FileInput, FlaskConical, Link2 } from "lucide-react";
import type { JSX, ReactNode } from "react";
import { StatusIcon } from "@/app/components/entity";
import { cn } from "@/lib/utils";

export interface LineageNodeSpec {
  key: string;
  label: string;
  sub?: string;
  /** A run's latest status (a status glyph), or an icon. */
  status?: string | null;
  icon?: ReactNode;
  mono?: boolean;
  /** Its details are open. */
  selected?: boolean;
  onClick?: () => void;
}

interface AssetLineageProps {
  inputs: LineageNodeSpec[];
  /** The producing run, or the import source. */
  origin: LineageNodeSpec | null;
  originTitle: string;
  self: LineageNodeSpec;
  usedBy: LineageNodeSpec[];
}

/** Row pitch and the narrowest column, in px — they place the connectors. */
const ROW = 40;
const MIN_HEIGHT = 48;

const LineageNode = ({
  node,
  strong = false,
}: {
  node: LineageNodeSpec;
  strong?: boolean;
}): JSX.Element => {
  const body = (
    <>
      {node.status !== undefined ? <StatusIcon status={node.status} /> : node.icon}
      <span className="flex min-w-0 flex-col items-start">
        <span
          className={cn(
            "max-w-full truncate",
            node.mono ? "font-mono text-label" : "text-body",
            strong && "font-semibold",
          )}
        >
          {node.label}
        </span>
        {node.sub ? (
          <span className="max-w-full truncate text-micro text-muted-foreground">{node.sub}</span>
        ) : null}
      </span>
    </>
  );
  const frame = cn(
    "flex h-8 w-full min-w-0 items-center gap-2 rounded-md border bg-background px-3 text-left",
    node.sub && "h-10",
    strong ? "border-accent ring-1 ring-accent" : "border-border",
    node.selected && "bg-accent-muted",
  );
  return node.onClick ? (
    <button
      type="button"
      onClick={node.onClick}
      aria-pressed={node.selected ?? false}
      title={node.sub ? `${node.label} · ${node.sub}` : node.label}
      className={cn(
        frame,
        "hover:bg-interactive focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring",
      )}
    >
      {body}
    </button>
  ) : (
    <div className={frame}>{body}</div>
  );
};

const EmptyNode = ({ icon: Icon, label }: { icon: LucideIcon; label: string }): JSX.Element => (
  <div className="flex h-8 w-full min-w-0 items-center gap-2 rounded-md border border-dashed border-border px-3 text-label text-muted-foreground">
    <Icon aria-hidden className="size-icon-sm flex-none" />
    <span className="truncate">{label}</span>
  </div>
);

/** Centres of `count` rows stacked in the middle of `height`. */
const rowCentres = (count: number, height: number): number[] => {
  const rows = Math.max(count, 1);
  const top = (height - rows * ROW) / 2;
  return Array.from({ length: rows }, (_, index) => top + index * ROW + ROW / 2);
};

/** Curves from each `from` y to each `to` y across one gap. */
const Connectors = ({
  from,
  to,
  height,
}: {
  from: number[];
  to: number[];
  height: number;
}): JSX.Element => {
  const width = 64;
  const paths = from.flatMap((y0) =>
    to.map((y1) => `M0,${y0} C${width / 2},${y0} ${width / 2},${y1} ${width - 5},${y1}`),
  );
  const heads = to.map((y) => `M${width - 7},${y - 4} L${width - 1},${y} L${width - 7},${y + 4}`);
  return (
    <svg
      aria-hidden
      width={width}
      height={height}
      className="flex-none text-muted-foreground/40"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
    >
      {[...paths, ...heads].map((d) => (
        <path key={d} d={d} />
      ))}
    </svg>
  );
};

const Column = ({ height, children }: { height: number; children: ReactNode }): JSX.Element => (
  <div className="flex min-w-0 flex-1 flex-col justify-center" style={{ height }}>
    {children}
  </div>
);

const Rows = ({ children }: { children: ReactNode }): JSX.Element => (
  <div className="flex flex-col">{children}</div>
);

const Row = ({ children }: { children: ReactNode }): JSX.Element => (
  <div className="flex h-10 items-center">{children}</div>
);

export const CountBadge = ({ count }: { count: number }): JSX.Element => (
  <span className="min-w-4 rounded-full bg-muted px-1 text-center text-micro tabular-nums text-muted-foreground">
    {count}
  </span>
);

const Label = ({ children, count }: { children: ReactNode; count?: number }): JSX.Element => (
  <div className="flex min-w-0 flex-1 items-center gap-2 text-label text-muted-foreground">
    {children}
    {count ? <CountBadge count={count} /> : null}
  </div>
);

export const AssetLineage = ({
  inputs,
  origin,
  originTitle,
  self,
  usedBy,
}: AssetLineageProps): JSX.Element => {
  const height = Math.max(MIN_HEIGHT, Math.max(inputs.length, usedBy.length, 1) * ROW);
  const middle = [height / 2];
  const inputYs = rowCentres(inputs.length, height);
  const usedYs = rowCentres(usedBy.length, height);
  const gap = <div className="w-16 flex-none" />;
  const emptyInputs = <EmptyNode icon={FileInput} label="No input assets" />;
  const emptyUsers = <EmptyNode icon={FlaskConical} label="No run uses it yet" />;
  const originNode = origin ? (
    <LineageNode node={origin} />
  ) : (
    <EmptyNode icon={Link2} label="Origin not recorded" />
  );

  return (
    <section aria-label="Lineage">
      {/* Desktop: four columns joined by curves. */}
      <div className="max-md:hidden">
        <div className="flex items-center pb-1">
          <Label count={inputs.length}>Inputs</Label>
          {gap}
          <Label>{originTitle}</Label>
          {gap}
          <Label>This asset</Label>
          {gap}
          <Label count={usedBy.length}>Used by</Label>
        </div>
        <div className="flex items-start">
          <Column height={height}>
            <Rows>
              {inputs.length ? (
                inputs.map((node) => (
                  <Row key={node.key}>
                    <LineageNode node={node} />
                  </Row>
                ))
              ) : (
                <Row>{emptyInputs}</Row>
              )}
            </Rows>
          </Column>
          <Connectors from={inputYs} to={middle} height={height} />
          <Column height={height}>{originNode}</Column>
          <Connectors from={middle} to={middle} height={height} />
          <Column height={height}>
            <LineageNode node={self} strong />
          </Column>
          <Connectors from={middle} to={usedYs} height={height} />
          <Column height={height}>
            <Rows>
              {usedBy.length ? (
                usedBy.map((node) => (
                  <Row key={node.key}>
                    <LineageNode node={node} />
                  </Row>
                ))
              ) : (
                <Row>{emptyUsers}</Row>
              )}
            </Rows>
          </Column>
        </div>
      </div>
      {/* Phone: one vertical chain. */}
      <ol className="flex flex-col gap-1 md:hidden">
        <PhoneStep title="Inputs" count={inputs.length}>
          {inputs.length
            ? inputs.map((node) => <LineageNode key={node.key} node={node} />)
            : emptyInputs}
        </PhoneStep>
        <PhoneStep title={originTitle}>{originNode}</PhoneStep>
        <PhoneStep>
          <LineageNode node={self} strong />
        </PhoneStep>
        <PhoneStep title="Used by" count={usedBy.length} last>
          {usedBy.length
            ? usedBy.map((node) => <LineageNode key={node.key} node={node} />)
            : emptyUsers}
        </PhoneStep>
      </ol>
    </section>
  );
};

const PhoneStep = ({
  title,
  count,
  last = false,
  children,
}: {
  title?: string;
  count?: number;
  last?: boolean;
  children: ReactNode;
}): JSX.Element => (
  <li className="flex flex-col gap-1">
    {title ? <Label count={count}>{title}</Label> : null}
    <div className="flex flex-col gap-1">{children}</div>
    {last ? null : <span aria-hidden className="ml-4 h-3 border-l border-border" />}
  </li>
);

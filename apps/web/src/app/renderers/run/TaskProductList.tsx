import type { JSX } from "react";
import { RunStatusBadge } from "@/components/workbench";
import { cn } from "@/lib/utils";
import type { TaskProduct } from "./taskProducts";

/** Status and per-task scalars for one attempt. The run result lives on Overview. */
export const TaskProductList = ({
  products,
  activePath,
  onOpen,
}: {
  products: readonly TaskProduct[];
  activePath: string | null;
  onOpen: (path: string) => void;
}): JSX.Element | null => {
  if (products.length === 0) return null;
  return (
    <section aria-label="Tasks in this attempt" className="shrink-0 space-y-4">
      <h3 className="border-b border-border/70 pb-2 text-label font-medium text-foreground">
        Tasks
      </h3>
      <ul className="space-y-3">
        {products.map((product) => (
          <li key={product.taskId} className="min-w-0 space-y-1">
            <div className="flex min-w-0 flex-wrap items-center gap-2">
              <span className="font-mono text-label text-foreground">{product.taskId}</span>
              <RunStatusBadge status={product.status} size="sm" />
            </div>
            {product.scalars.length > 0 ? (
              <dl className="flex flex-wrap gap-x-4 gap-y-1">
                {product.scalars.map((scalar) => (
                  <div key={scalar.key} className="flex min-w-0 gap-1">
                    <dt className="text-label text-muted-foreground">{scalar.key}</dt>
                    <dd className="font-mono text-label text-foreground">{scalar.value}</dd>
                  </div>
                ))}
              </dl>
            ) : null}
            {product.structures.length > 0 ? (
              <div className="flex flex-wrap gap-1">
                {product.structures.map((structure) => {
                  const active = structure.path === activePath;
                  return (
                    <button
                      key={structure.key}
                      type="button"
                      onClick={() => onOpen(structure.path)}
                      className={cn(
                        "rounded-control border px-2 py-1 font-mono text-micro",
                        active
                          ? "border-accent bg-accent-muted text-accent-muted-foreground"
                          : "border-border text-muted-foreground hover:text-foreground",
                      )}
                    >
                      {structure.label}
                    </button>
                  );
                })}
              </div>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
};

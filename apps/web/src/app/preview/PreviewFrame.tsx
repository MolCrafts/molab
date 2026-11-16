/**
 * The Preview's chrome (L12, Figma `L12-*`): what it is · ↗ open · ⋯ · ✕, one
 * context line, the body (Level 2 verdict, Level 3 evidence, one figure or a
 * short key list), the state's primary action + Logs, and the key hints. Every
 * kind renders into this one frame; nothing else draws Preview chrome.
 */

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  Kbd,
} from "@molcrafts/ui";
import { ArrowUpRight, Copy, Ellipsis, SquareArrowOutUpRight, X } from "lucide-react";
import type { ComponentType, JSX, ReactNode } from "react";
import { toast } from "@/components/ui/toast";
import { WorkbenchIconAction } from "@/components/workbench";
import { cn } from "@/lib/utils";

export interface PreviewCopy {
  label: string;
  value: string;
}

export interface PreviewFrameProps {
  /** Status glyph for a stateful thing, else the kind's icon. */
  lead: ReactNode;
  title: string;
  /** Run identities and file names read as code. */
  mono?: boolean;
  context?: string;
  /** Read aloud when the Preview changes target: title + verdict. */
  announcement?: string;
  /** The state's primary action, then Logs. */
  actions?: ReactNode;
  /** Extra ⋯ items for this kind (Add to selection …), above the copies. */
  menuItems?: ReactNode;
  copies?: readonly PreviewCopy[];
  onOpen: () => void;
  onOpenInBackground?: () => void;
  onClose: () => void;
  children?: ReactNode;
}

const copyValue = (copy: PreviewCopy): void => {
  void navigator.clipboard
    .writeText(copy.value)
    .then(() => toast.success(`${copy.label} copied`))
    .catch(() => toast.error(`Could not copy ${copy.label.toLowerCase()}`));
};

export const KindIcon = ({
  icon: Icon,
}: {
  icon: ComponentType<{ className?: string }>;
}): JSX.Element => <Icon className="size-icon flex-none text-muted-foreground" aria-hidden />;

export const PreviewFrame = ({
  lead,
  title,
  mono = false,
  context,
  announcement,
  actions,
  menuItems,
  copies = [],
  onOpen,
  onOpenInBackground,
  onClose,
  children,
}: PreviewFrameProps): JSX.Element => (
  <div className="flex h-full min-h-0 flex-col">
    <header className="flex h-10 flex-none items-center gap-2 pr-2 pl-4">
      <span className="flex flex-none items-center">{lead}</span>
      <h2
        className={cn(
          "min-w-0 flex-1 truncate font-medium text-foreground",
          mono ? "font-mono text-label" : "text-body",
        )}
        title={title}
      >
        {title}
      </h2>
      <WorkbenchIconAction size="shell" label="Open" shortcut="↵" onClick={onOpen}>
        <ArrowUpRight aria-hidden />
      </WorkbenchIconAction>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <WorkbenchIconAction size="shell" label="More actions">
            <Ellipsis aria-hidden />
          </WorkbenchIconAction>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-60">
          {onOpenInBackground ? (
            <DropdownMenuItem onSelect={onOpenInBackground}>
              <SquareArrowOutUpRight className="size-icon" aria-hidden />
              Open in background
            </DropdownMenuItem>
          ) : null}
          {menuItems}
          {copies.length > 0 ? <DropdownMenuSeparator /> : null}
          {copies.map((copy) => (
            <DropdownMenuItem key={copy.label} onSelect={() => copyValue(copy)}>
              <Copy className="size-icon" aria-hidden />
              Copy {copy.label.toLowerCase()}
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>
      <WorkbenchIconAction size="shell" label="Close Preview" shortcut="Esc" onClick={onClose}>
        <X aria-hidden />
      </WorkbenchIconAction>
    </header>
    {context ? (
      <p className="flex min-w-0 flex-none gap-2 border-b border-border px-4 pb-2 text-label text-muted-foreground">
        {/* Under the title, past the glyph column. */}
        <span className="w-4 flex-none" aria-hidden />
        <span className="min-w-0 truncate">{context}</span>
      </p>
    ) : (
      <div className="flex-none border-b border-border" />
    )}
    <div className="sr-only" aria-live="polite">
      {announcement ?? title}
    </div>
    <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
      {children}
      {actions ? <div className="flex flex-wrap items-center gap-2 pl-6">{actions}</div> : null}
    </div>
    {/* Keys only (retrofit R11: icon OR text); each key's word is its tooltip. */}
    <footer className="flex h-7 flex-none items-center gap-2 border-t border-border px-4 text-label text-muted-foreground">
      {(
        [
          ["↵", "Open"],
          ["Esc", "Close"],
          ["↑↓", "Move"],
        ] as const
      ).map(([key, word]) => (
        <span key={key} role="img" aria-label={`${word}: ${key}`} title={word}>
          <Kbd>{key}</Kbd>
        </span>
      ))}
    </footer>
  </div>
);

/** One row of a Preview key list: 92px key column, value as code by default. */
export const PreviewKV = ({
  label,
  children,
  mono = true,
}: {
  label: string;
  children: ReactNode;
  mono?: boolean;
}): JSX.Element => (
  <div className="flex h-shell-action min-w-0 items-center gap-2 text-body">
    <span className="w-shell-kv-label flex-none text-muted-foreground">{label}</span>
    <span className={cn("min-w-0 truncate", mono && "font-mono text-label")}>{children}</span>
  </div>
);

/** Level 3 sub-heading inside the body, aligned to the text column. */
export const PreviewSubhead = ({ children }: { children: ReactNode }): JSX.Element => (
  <p className="pl-6 text-label text-muted-foreground">{children}</p>
);

/** A link inside a Preview re-targets the Preview (upstream task, produced-by run…). */
export const PreviewLink = ({
  children,
  onClick,
  mono = true,
}: {
  children: ReactNode;
  onClick: () => void;
  mono?: boolean;
}): JSX.Element => (
  <button
    type="button"
    className={cn(
      "min-w-0 truncate text-left text-link hover:underline focus-visible:underline focus-visible:outline-none",
      mono && "font-mono text-label",
    )}
    onClick={onClick}
  >
    {children}
  </button>
);

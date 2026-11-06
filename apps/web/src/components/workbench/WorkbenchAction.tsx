/**
 * Product action vocabulary — feature chrome should use these, not raw
 * `Button variant=…`. Visual mapping stays inside this module.
 */

import { Button } from "@molcrafts/ui";
import { Slot, Slottable } from "@radix-ui/react-slot";
import { RefreshCw, X } from "lucide-react";
import type { ButtonHTMLAttributes, JSX, ReactNode } from "react";
import { DeniedHint } from "@/app/auth/DeniedHint";
import { cn } from "@/lib/utils";

export type WorkbenchActionKind = "primary" | "secondary" | "ghost" | "danger" | "link";

const KIND_TO_VARIANT: Record<
  WorkbenchActionKind,
  "default" | "outline" | "ghost" | "destructive" | "link"
> = {
  primary: "ghost",
  secondary: "ghost",
  ghost: "ghost",
  danger: "ghost",
  link: "link",
};

export interface WorkbenchActionProps
  extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children"> {
  kind?: WorkbenchActionKind;
  /** compact 28 · default 32 · comfortable 36 · content preserves caller layout */
  size?: "compact" | "default" | "comfortable" | "content";
  icon?: ReactNode;
  children?: ReactNode;
  asChild?: boolean;
  /**
   * When set, the control is disabled and hover shows this explanation
   * (permission denial, etc.). Prefer over only setting `disabled`.
   */
  deniedReason?: string | null;
}

const SIZE_MAP = {
  compact: "sm" as const,
  default: "default" as const,
  comfortable: "lg" as const,
  content: "content" as const,
};

export const WorkbenchAction = ({
  kind = "secondary",
  size = "default",
  icon,
  children,
  className,
  asChild,
  type = "button",
  deniedReason,
  disabled,
  title,
  ...rest
}: WorkbenchActionProps): JSX.Element => {
  const blocked = Boolean(deniedReason);
  const iconOnly = Boolean(icon) && !asChild && size !== "content";
  const button = (
    <Button
      type={asChild ? undefined : type}
      variant={KIND_TO_VARIANT[kind]}
      size={iconOnly ? "icon" : SIZE_MAP[size]}
      className={cn(
        "border-0 shadow-none",
        iconOnly && "size-control-compact shrink-0",
        kind === "primary" && !iconOnly && "bg-interactive",
        kind === "danger" && "text-destructive hover:text-destructive",
        className,
      )}
      asChild={asChild}
      disabled={disabled || blocked}
      title={
        blocked
          ? undefined
          : (title ?? (iconOnly && typeof children === "string" ? children : undefined))
      }
      {...rest}
    >
      {icon}
      {asChild ? (
        <Slottable>{children}</Slottable>
      ) : iconOnly ? (
        <span className="sr-only">{children}</span>
      ) : (
        children
      )}
    </Button>
  );
  return <DeniedHint reason={deniedReason}>{button}</DeniedHint>;
};

export interface WorkbenchIconActionProps
  extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children"> {
  label: string;
  /** All action controls stay borderless; intent is carried by the icon and tooltip. */
  kind?: Exclude<WorkbenchActionKind, "link" | "secondary">;
  size?: "compact" | "default";
  children: ReactNode;
  asChild?: boolean;
  /** Permission / policy denial — disables control and explains on hover. */
  deniedReason?: string | null;
}

export const WorkbenchIconAction = ({
  label,
  kind = "ghost",
  size = "compact",
  children,
  className,
  asChild,
  type = "button",
  deniedReason,
  disabled,
  title,
  ...rest
}: WorkbenchIconActionProps): JSX.Element => {
  const blocked = Boolean(deniedReason);
  const button = (
    <Button
      type={asChild ? undefined : type}
      variant={KIND_TO_VARIANT[kind]}
      size="icon"
      aria-label={label}
      title={blocked ? undefined : (title ?? label)}
      className={cn(
        size === "compact" ? "size-control-compact" : "size-control",
        "shrink-0 border-0 shadow-none",
        kind === "danger" && "text-destructive hover:text-destructive",
        className,
      )}
      asChild={asChild}
      disabled={disabled || blocked}
      {...rest}
    >
      {children}
    </Button>
  );
  return <DeniedHint reason={deniedReason}>{button}</DeniedHint>;
};

export type WorkbenchRetryActionProps = Omit<
  WorkbenchIconActionProps,
  "children" | "kind" | "label"
> & {
  label?: string;
};

/** Consistent borderless retry affordance for compact error and empty states. */
export const WorkbenchRetryAction = ({
  label = "Retry",
  ...rest
}: WorkbenchRetryActionProps): JSX.Element => (
  <WorkbenchIconAction label={label} kind="ghost" {...rest}>
    <RefreshCw aria-hidden />
  </WorkbenchIconAction>
);

export type WorkbenchDismissActionProps = Omit<
  WorkbenchIconActionProps,
  "children" | "kind" | "label"
> & {
  label?: string;
};

/** Consistent borderless dismiss affordance for inline notices. */
export const WorkbenchDismissAction = ({
  label = "Dismiss",
  ...rest
}: WorkbenchDismissActionProps): JSX.Element => (
  <WorkbenchIconAction label={label} kind="ghost" {...rest}>
    <X aria-hidden />
  </WorkbenchIconAction>
);

/** Tooltip-friendly icon control without importing Button variants in features. */
export const WorkbenchToggleAction = ({
  pressed,
  label,
  children,
  className,
  ...rest
}: {
  pressed: boolean;
  label: string;
  children: ReactNode;
} & Omit<ButtonHTMLAttributes<HTMLButtonElement>, "children" | "aria-pressed">): JSX.Element => (
  <Button
    type="button"
    variant="ghost"
    size="icon"
    aria-label={label}
    aria-pressed={pressed}
    title={label}
    className={cn("size-control-compact", pressed && "bg-interactive text-foreground", className)}
    {...rest}
  >
    {children}
  </Button>
);

// re-export Slot for rare asChild composition without pulling radix in features
export { Slot };

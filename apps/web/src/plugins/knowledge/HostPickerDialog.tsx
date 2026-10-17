import type { JSX } from "react";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { HostOption } from "./knowledgeDocTree";

const GROUPS = [
  ["workspace", "Workspace"],
  ["project", "Projects"],
  ["experiment", "Experiments"],
  ["run", "Runs"],
] as const;

/** Pick a document host from server-reported paths. */
export const HostPickerDialog = ({
  open,
  onOpenChange,
  options,
  onPick,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  options: HostOption[];
  onPick: (hostPath: string) => void;
}): JSX.Element => (
  <Dialog open={open} onOpenChange={onOpenChange}>
    <DialogContent className="gap-0 overflow-hidden p-0">
      <DialogHeader className="px-4 pt-4">
        <DialogTitle>Move document</DialogTitle>
        <DialogDescription>Choose the host that should own this document.</DialogDescription>
      </DialogHeader>
      <Command>
        <CommandInput placeholder="Filter hosts…" />
        <CommandList>
          <CommandEmpty>No matching host.</CommandEmpty>
          {GROUPS.map(([kind, heading]) => {
            const items = options.filter((option) => option.kind === kind);
            if (items.length === 0) return null;
            return (
              <CommandGroup key={kind} heading={heading}>
                {items.map((option) => (
                  <CommandItem
                    key={`${kind}:${option.hostPath}`}
                    value={`${heading} ${option.label} ${option.hostPath || "root"}`}
                    disabled={option.disabled}
                    onSelect={() => {
                      if (option.disabled) return;
                      onPick(option.hostPath);
                      onOpenChange(false);
                    }}
                  >
                    <span className="truncate">{option.label}</span>
                    {option.hostPath ? (
                      <span className="ml-auto truncate font-mono text-micro text-muted-foreground">
                        {option.hostPath}
                      </span>
                    ) : null}
                  </CommandItem>
                ))}
              </CommandGroup>
            );
          })}
        </CommandList>
      </Command>
    </DialogContent>
  </Dialog>
);

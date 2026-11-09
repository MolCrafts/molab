/**
 * An experiment with no workflow (Figma L06-6, decision 6): what binds one, as
 * Python to copy. No empty canvas, and no “open a workflow file” with nothing
 * to click.
 */

import type { JSX } from "react";
import { StatusIcon } from "@/app/components/entity";
import { DialogButton } from "@/components/dialog/AppDialog";
import { toast } from "@/components/ui/toast";

const py = (text: string): string => JSON.stringify(text);

export const bindSnippet = (projectName: string, experimentName: string): string =>
  [
    "import molab",
    "",
    `exp = molab.Workspace(".").get_folder(${py(projectName)}).get_folder(${py(experimentName)})`,
    "exp.define(wf)  # binds wf to this experiment",
  ].join("\n");

export const UnboundWorkflow = ({
  projectName,
  experimentName,
}: {
  projectName: string;
  experimentName: string;
}): JSX.Element => {
  const snippet = bindSnippet(projectName, experimentName);
  return (
    <div className="h-full min-h-0 overflow-auto bg-background">
      <div className="space-y-4 px-6 py-6">
        <div className="flex items-center gap-2">
          <StatusIcon status="pending" className="size-icon shrink-0" />
          <h2 className="text-title">
            <span className="font-semibold text-muted-foreground">No workflow bound yet</span>
          </h2>
        </div>
        <div className="space-y-2 pl-6">
          <p className="text-label text-muted-foreground">
            Bind one from Python, then it shows here:
          </p>
          <div className="flex max-w-[48rem] items-start gap-2">
            <pre className="min-w-0 flex-1 overflow-x-auto rounded-control border border-border bg-muted px-3 py-2 font-mono text-label text-foreground">
              {snippet}
            </pre>
            <DialogButton
              kind="secondary"
              onClick={() => {
                void navigator.clipboard.writeText(snippet);
                toast("Copied");
              }}
            >
              Copy
            </DialogButton>
          </div>
        </div>
      </div>
    </div>
  );
};

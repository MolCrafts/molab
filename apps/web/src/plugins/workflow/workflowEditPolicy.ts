/** Whether a workflow graph may be edited, from the experiment's kind alone. */

export type WorkflowEditPolicy = { mode: "edit" } | { mode: "convert"; kind: string };

/** Document and unbound experiments are editable. A code experiment must convert first. */
export const workflowEditPolicy = (kind: string | null | undefined): WorkflowEditPolicy => {
  if (kind === "document" || kind == null) return { mode: "edit" };
  return { mode: "convert", kind };
};

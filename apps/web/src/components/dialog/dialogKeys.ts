/** ⌘↵ / Ctrl-↵ submits any dialog (L13); a plain ↵ is the field's own. */
export const isSubmitShortcut = (
  event: Pick<KeyboardEvent, "key" | "metaKey" | "ctrlKey" | "isComposing">,
): boolean => event.key === "Enter" && (event.metaKey || event.ctrlKey) && !event.isComposing;

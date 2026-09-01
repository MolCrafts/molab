import type { PendingApprovalItem } from "@/api/generated/models/PendingApprovalItem";

export const humanApprovalTitle = (intent: string, formTitle?: string | null): string => {
  const cleaned = (formTitle ?? "").trim();
  if (cleaned && !/original request|revise the previous plan/i.test(cleaned)) {
    return cleaned.length > 80 ? `${cleaned.slice(0, 77)}…` : cleaned;
  }
  const knownTitles: Record<string, string> = {
    approve_experiment_plan: "Approve experiment plan",
    approve_experiment_spec: "Approve experiment spec",
    approve_execution: "Approve execution",
    approve_plan: "Approve plan",
  };
  if (knownTitles[intent]) return knownTitles[intent];
  return intent
    .replace(/^approve_/, "Approve ")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
};

const formDocumentTitle = (item: PendingApprovalItem): string | null => {
  const document = item.formDocument;
  if (!document || typeof document !== "object") return null;
  const title = document.title;
  return typeof title === "string" ? title : null;
};

export const pendingApprovalTitle = (item: PendingApprovalItem): string =>
  humanApprovalTitle(item.intent, formDocumentTitle(item));

export const pendingApprovalPath = (item: PendingApprovalItem): string =>
  `/agent-tasks/${encodeURIComponent(item.taskId)}`;

/** One icon per knowledge class (L10): the tree, tables, tabs and pages all use it. */

import {
  Activity,
  BookOpen,
  Bot,
  CircleAlert,
  CircleCheck,
  FileText,
  Flag,
  ListChecks,
  type LucideIcon,
  SquareCheck,
  Workflow,
} from "lucide-react";
import type { KnowledgeClass } from "./knowledgeClass";

export const KNOWLEDGE_CLASS_ICON: Record<KnowledgeClass, LucideIcon> = {
  Note: FileText,
  Literature: BookOpen,
  Report: CircleAlert,
  Finding: CircleCheck,
  Observation: Activity,
  Plan: ListChecks,
  Roadmap: Workflow,
  Todo: SquareCheck,
  Milestone: Flag,
  Delegation: Bot,
};

export const knowledgeClassIcon = (cls: KnowledgeClass): LucideIcon => KNOWLEDGE_CLASS_ICON[cls];

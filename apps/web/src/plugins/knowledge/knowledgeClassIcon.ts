/** One icon per knowledge class (L10): the tree, tables, tabs and pages all use it. */

import {
  Activity,
  BookOpen,
  CircleAlert,
  CircleCheck,
  FileText,
  Lightbulb,
  ListChecks,
  type LucideIcon,
} from "lucide-react";
import type { KnowledgeClass } from "./knowledgeClass";

export const KNOWLEDGE_CLASS_ICON: Record<KnowledgeClass, LucideIcon> = {
  Note: FileText,
  Literature: BookOpen,
  Report: CircleAlert,
  Finding: CircleCheck,
  Observation: Activity,
  Hypothesis: Lightbulb,
  Plan: ListChecks,
};

/** The class's icon; a file with no knowledge class (a TeX manuscript) is a plain file. */
export const knowledgeClassIcon = (cls: KnowledgeClass | null): LucideIcon =>
  cls === null ? FileText : KNOWLEDGE_CLASS_ICON[cls];

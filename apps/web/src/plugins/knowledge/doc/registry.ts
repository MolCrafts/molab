/**
 * The `<molab-…>` components a knowledge page knows (L10), in "/" menu order:
 * planning, then data, then text. One entry per element name.
 */

import { approvalSpec } from "./components/Approval";
import { citationSpec } from "./components/Citation";
import { figureSpec } from "./components/Figure";
import { linksSpec } from "./components/Links";
import { logSpec } from "./components/Log";
import { metricChartSpec } from "./components/MetricChart";
import { milestoneSpec } from "./components/Milestone";
import { paramsSpec } from "./components/Params";
import { runRefSpec } from "./components/RunRef";
import { runTableSpec } from "./components/RunTable";
import { stageTrackSpec } from "./components/StageTrack";
import { todoListSpec } from "./components/TodoList";
import type { DocComponentSpec } from "./context";

export const DOC_COMPONENTS: readonly DocComponentSpec[] = [
  todoListSpec,
  stageTrackSpec,
  milestoneSpec,
  approvalSpec,
  runRefSpec,
  runTableSpec,
  metricChartSpec,
  paramsSpec,
  figureSpec,
  citationSpec,
  logSpec,
  linksSpec,
];

const BY_NAME = new Map<string, DocComponentSpec>(DOC_COMPONENTS.map((spec) => [spec.name, spec]));

export const componentSpec = (name: string): DocComponentSpec | undefined => BY_NAME.get(name);

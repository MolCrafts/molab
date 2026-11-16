/**
 * The `<molab-…>` components a knowledge page knows (L10), in "/" menu order:
 * data, then text. One entry per element name.
 */

import { citationSpec } from "./components/Citation";
import { figureSpec } from "./components/Figure";
import { linksSpec } from "./components/Links";
import { logSpec } from "./components/Log";
import { metricChartSpec } from "./components/MetricChart";
import { paramsSpec } from "./components/Params";
import { runRefSpec } from "./components/RunRef";
import { runTableSpec } from "./components/RunTable";
import type { DocComponentSpec } from "./context";

export const DOC_COMPONENTS: readonly DocComponentSpec[] = [
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

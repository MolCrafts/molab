export {
  getActivePluginId,
  getContributionGeneration,
  listEntityTabContributions,
  listExecutionColumnContributions,
  listExecutionDetailContributions,
  listFilePreviewContributions,
  listFileTypeContributions,
  listMetricReaderContributions,
  registerEntityTabContribution,
  registerExecutionColumnContribution,
  registerExecutionDetailContribution,
  registerFilePreviewContribution,
  registerFileTypeContribution,
  registerMetricReaderContribution,
  registerRendererContribution,
  resolveMetricReaderForPath,
  resolveMetricReaderForText,
  resolveRendererContribution,
  runWithPluginContext,
  unregisterEntityTabContribution,
  unregisterExecutionColumnContribution,
  unregisterExecutionDetailContribution,
  unregisterFilePreviewContribution,
  unregisterFileTypeContribution,
  unregisterMetricReaderContribution,
  unregisterRendererContribution,
  useContributionGeneration,
} from "@/lib/contribution-runtime";

import { resetContributionRuntimeForTests as resetHostContributions } from "@/lib/contribution-runtime";
import { resetWorkbenchContributionsForTests } from "@/plugins/contributions/workbench";

export const resetContributionRuntimeForTests = (): void => {
  resetHostContributions();
  resetWorkbenchContributionsForTests();
};

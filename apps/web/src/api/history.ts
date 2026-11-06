import type { HistoryFact } from "@/api/generated/models/HistoryFact";
import type { HistorySyncResponse } from "@/api/generated/models/HistorySyncResponse";
import { HistoryService } from "@/api/generated/services/HistoryService";

export type { HistoryFact };

export const historyApi = {
  list: (limit = 50): Promise<HistoryFact[]> =>
    HistoryService.readHistory(undefined, undefined, limit),
  sync: (): Promise<HistorySyncResponse> => HistoryService.syncHistory(),
  push: (remote: string): Promise<HistorySyncResponse> => HistoryService.pushHistory({ remote }),
};

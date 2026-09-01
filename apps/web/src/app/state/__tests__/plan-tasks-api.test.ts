import { afterEach, describe, expect, it, rs } from "@rstest/core";
import { planTasksApi } from "@/api";
import { PlanTasksService } from "@/api/generated/services/PlanTasksService";

const CREATE = "createPlanTask" as const;
const GET = "getPlanTask" as const;

const RESPONSE = {
  taskId: "plan-1",
  runId: "run-1",
  projectId: "proj",
  experimentId: "exp",
  status: "running",
  createdAt: "2026-06-22T00:00:00Z",
  model: "stub-model",
  draftPreview: "screen ratios",
  workflowPersisted: false,
};

describe("planTasksApi", () => {
  afterEach(() => {
    rs.restoreAllMocks();
  });

  it("createPlanTask posts the draft through the generated PlanTasksService", async () => {
    const spy = rs.spyOn(PlanTasksService, CREATE).mockResolvedValue(RESPONSE as never);
    const fetchSpy = rs.spyOn(globalThis, "fetch");

    const result = await planTasksApi.createPlanTask("proj", "exp", { draft: "screen ratios" });

    expect(spy).toHaveBeenCalledWith("proj", "exp", { draft: "screen ratios" });
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(result.taskId).toBe("plan-1");
    expect(result.status).toBe("running");
  });

  it("getPlanTask fetches a task's status through the generated PlanTasksService", async () => {
    const done = { ...RESPONSE, status: "completed", workflowPersisted: true };
    const spy = rs.spyOn(PlanTasksService, GET).mockResolvedValue(done as never);

    const result = await planTasksApi.getPlanTask("proj", "exp", "plan-1");

    expect(spy).toHaveBeenCalledWith("proj", "exp", "plan-1");
    expect(result.status).toBe("completed");
    expect(result.workflowPersisted).toBe(true);
  });
});

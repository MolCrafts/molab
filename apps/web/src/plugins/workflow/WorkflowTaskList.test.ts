import { describe, expect, it } from "@rstest/core";
import { taskOrder } from "./WorkflowTaskList";

const task = (id: string) => ({ id, type: `t.${id}` });

describe("taskOrder", () => {
  it("lists tasks after the tasks they run after", () => {
    const order = taskOrder({
      task_configs: [task("publish"), task("train"), task("prepare"), task("evaluate")],
      links: [
        { from: "prepare", to: "train" },
        { from: "prepare", to: "evaluate" },
        { from: "train", to: "publish" },
        { from: "evaluate", to: "publish" },
      ],
    });
    expect(order.map((item) => item.id)).toEqual(["prepare", "train", "evaluate", "publish"]);
    expect(order.at(-1)?.after).toEqual(["train", "evaluate"]);
  });

  it("keeps the tasks of a loop instead of dropping them", () => {
    const order = taskOrder({
      task_configs: [task("a"), task("b")],
      links: [
        { from: "a", to: "b" },
        { from: "b", to: "a" },
      ],
    });
    expect(order.map((item) => item.id)).toEqual(["a", "b"]);
  });
});

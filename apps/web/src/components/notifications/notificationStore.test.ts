import { describe, expect, it } from "@rstest/core";
import {
  addNotification,
  MAX_NOTIFICATIONS,
  type Notification,
  routeOf,
} from "./notificationStore";

const n = (id: string, kind: Notification["kind"] = "error"): Notification => ({
  id,
  kind,
  message: id,
});

describe("routeOf", () => {
  it("floats errors and results that carry a follow-up action", () => {
    expect(routeOf("error", false)).toBe("notification");
    expect(routeOf("success", true)).toBe("notification");
  });

  it("keeps plain confirmations and progress in the status bar", () => {
    expect(routeOf("success", false)).toBe("status");
    expect(routeOf("default", false)).toBe("status");
  });
});

describe("addNotification", () => {
  it("adds at the bottom and keeps at most three, dropping the oldest", () => {
    let list: Notification[] = [];
    for (const id of ["a", "b", "c", "d"]) list = addNotification(list, n(id));
    expect(list.map((item) => item.id)).toEqual(["b", "c", "d"]);
    expect(list).toHaveLength(MAX_NOTIFICATIONS);
  });

  it("replaces an identical message instead of stacking it", () => {
    const list = addNotification(addNotification([], n("a")), { ...n("a2"), message: "a" });
    expect(list).toHaveLength(1);
    expect(list[0]?.id).toBe("a2");
  });
});

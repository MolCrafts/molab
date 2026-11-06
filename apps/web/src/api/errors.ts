import { ApiError } from "@/api/generated/core/ApiError";

const softMessage = (text: string): boolean => {
  const trimmed = text.trim().toLowerCase();
  if (trimmed === "needs_auth" || trimmed === "unreachable" || trimmed === "service unavailable") {
    return true;
  }
  return /^request failed:\s*503\b/.test(trimmed);
};

const softBody = (body: unknown): boolean => {
  if (!body || typeof body !== "object") return false;
  const record = body as {
    detail?: unknown;
    error?: { message?: unknown; details?: { reason?: unknown } };
  };
  return [record.detail, record.error?.message, record.error?.details?.reason].some(
    (value) => typeof value === "string" && softMessage(value),
  );
};

/**
 * A remote host that is still asking for a code, or that has not been reached
 * yet. The connect dialog and the status strip already say so.
 */
export const isSoftRemoteWait = (err: unknown): boolean => {
  if (err == null || err === "") return false;
  if (typeof err === "string") return softMessage(err);
  if (err instanceof ApiError) {
    return err.status === 503 || softMessage(err.message) || softBody(err.body);
  }
  if (err instanceof Error) return softMessage(err.message);
  return false;
};

/** Draw a failure only after the fetch has settled and the host is not waiting on a code. */
export const shouldShowFailure = (
  err: unknown,
  options: { fetching?: boolean; needsAuth?: boolean } = {},
): boolean => {
  if (err == null || err === "") return false;
  if (options.fetching || options.needsAuth) return false;
  return !isSoftRemoteWait(err);
};

export const activeNeedsAuth = (
  workspaces: readonly { active?: boolean; needsAuth?: boolean }[] | undefined,
): boolean => {
  if (!workspaces || workspaces.length === 0) return false;
  const active = workspaces.find((workspace) => workspace.active) ?? workspaces[0];
  return Boolean(active?.needsAuth);
};

/** FastAPI `{ detail }` body, or the generated client's status text. */
export const apiErrorMessage = (err: unknown, fallback: string): string => {
  if (err instanceof ApiError) {
    const detail = (err.body as { detail?: unknown } | null)?.detail;
    if (typeof detail === "string" && detail) return detail;
    if (typeof err.body === "string" && err.body.length > 0 && err.body.length < 500) {
      return err.body.trim();
    }
    return err.statusText || fallback;
  }
  if (err instanceof Error && err.message) return err.message;
  return fallback;
};

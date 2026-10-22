import { ApiError } from "@/api/generated/core/ApiError";

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

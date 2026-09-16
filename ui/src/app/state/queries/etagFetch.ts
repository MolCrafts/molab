/**
 * Conditional JSON fetch for the endpoints that bypass the generated client.
 *
 * The generated `openapi-typescript-codegen` client throws on any non-2xx
 * (`core/request.ts`), so it cannot see a 304 — for those calls the browser's
 * own HTTP cache does the revalidation when the server sends
 * `ETag` + `Cache-Control: private, no-cache`. The raw-`fetch` wrappers in
 * `app/state/api.ts` (served workspaces, per-workspace projects, project
 * assets, catalog-by-path, agent sessions, the runs index, the fs listing) go
 * through this helper instead, which:
 *
 *  - remembers the last `ETag` per URL,
 *  - sends `If-None-Match` only when an ETag **and** the previous data exist,
 *  - answers a 304 with the previous data (same reference → no re-render),
 *  - retries once without the header when the cached data was evicted,
 *  - throws {@link HttpStatusError} on any other non-2xx.
 *
 * It also covers dev:mock mode, where the MSW service worker bypasses the
 * browser cache.
 */

export class HttpStatusError extends Error {
  readonly status: number;
  readonly url: string;
  readonly body: unknown;

  constructor(url: string, status: number, statusText: string, body: unknown) {
    super(`${status} ${statusText || "request failed"} — ${url}`);
    this.name = "HttpStatusError";
    this.status = status;
    this.url = url;
    this.body = body;
  }
}

export interface ConditionalFetchOptions<T> {
  signal?: AbortSignal;
  /** The data currently cached for this URL (TanStack `getQueryData`). */
  previous?: () => T | undefined;
  /** Extra `fetch` options (method/headers/body); `headers` are merged. */
  init?: RequestInit;
}

const etags = new Map<string, string>();

/** The ETag remembered for `url`, if any (test/debug aid). */
export const getStoredEtag = (url: string): string | undefined => etags.get(url);

/** Forget every remembered ETag (workspace switch, tests). */
export const resetEtagCache = (): void => {
  etags.clear();
};

const readBody = async (response: Response): Promise<unknown> => {
  const text = await response.text().catch(() => "");
  if (!text) return undefined;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return text;
  }
};

export async function fetchJsonConditional<T>(
  url: string,
  options: ConditionalFetchOptions<T> = {},
): Promise<T> {
  const { signal, previous, init } = options;
  const headers = new Headers(init?.headers);
  if (!headers.has("Accept")) headers.set("Accept", "application/json");

  const previousData = previous?.();
  const etag = etags.get(url);
  if (etag !== undefined && previousData !== undefined) headers.set("If-None-Match", etag);

  let response = await fetch(url, { ...init, headers, signal });

  if (response.status === 304) {
    const cached = previous?.();
    if (cached !== undefined) return cached;
    // The cache was evicted between the header decision and the answer (or a
    // browser-level 304 leaked through): ask once more, unconditionally.
    etags.delete(url);
    headers.delete("If-None-Match");
    response = await fetch(url, { ...init, headers, signal });
  }

  if (!response.ok) {
    throw new HttpStatusError(url, response.status, response.statusText, await readBody(response));
  }

  const tag = response.headers.get("ETag");
  if (tag) etags.set(url, tag);
  else etags.delete(url);

  return (await response.json()) as T;
}

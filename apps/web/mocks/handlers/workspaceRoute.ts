import { matchRequestUrl } from "msw";

/** The single served example has the same flat and explicit-workspace API. */
export const workspaceRoute =
  (path: string) =>
  ({ request }: { request: Request }) => {
    const url = new URL(request.url);
    url.pathname = url.pathname.replace(/^\/api\/workspaces\/feature-showcase(?=\/)/, "/api");
    const match = matchRequestUrl(url, path);
    return { matches: match.matches, params: match.params ?? {} };
  };

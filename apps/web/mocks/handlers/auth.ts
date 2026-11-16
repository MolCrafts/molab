import { HttpResponse, http } from "msw";

/**
 * Mock auth is off by default so offline ``npm run dev:web`` boots without a
 * login wall. Set ``localStorage["molab.mock.auth"] = "on"`` to review the
 * login page (L15): the mock then requires a session, accepts admin / admin,
 * and keeps the session in sessionStorage. Real auth is exercised against
 * ``molab serve --auth``.
 */
const AUTH_SWITCH = "molab.mock.auth";
const SESSION_KEY = "molab.mock.session";

const ADMIN = {
  username: "admin",
  role: "admin",
  workspaces: ["*"],
  disabled: false,
};

const read = (store: () => Storage, key: string): string | null => {
  try {
    return store().getItem(key);
  } catch {
    return null;
  }
};

const authOn = (): boolean => read(() => window.localStorage, AUTH_SWITCH) === "on";
const signedIn = (): boolean => read(() => window.sessionStorage, SESSION_KEY) === "admin";

export const authHandlers = [
  http.get("/api/auth/status", () =>
    HttpResponse.json(
      authOn()
        ? { enabled: true, authenticated: signedIn(), user: signedIn() ? ADMIN : null }
        : { enabled: false, authenticated: false, user: null },
    ),
  ),
  http.post("/api/auth/login", async ({ request }) => {
    const body = (await request.json()) as { username?: string; password?: string };
    if (body.username !== "admin" || body.password !== "admin")
      return HttpResponse.json({ detail: "Wrong username or password." }, { status: 401 });
    window.sessionStorage.setItem(SESSION_KEY, "admin");
    return HttpResponse.json(ADMIN);
  }),
  http.post("/api/auth/logout", () => {
    window.sessionStorage.removeItem(SESSION_KEY);
    return HttpResponse.json({ ok: true });
  }),
  http.get("/api/auth/users", () => HttpResponse.json({ users: authOn() ? [ADMIN] : [] })),
];

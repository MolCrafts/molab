import { QueryClientProvider } from "@tanstack/react-query";
import ReactDOM from "react-dom/client";
import { createBrowserRouter, RouterProvider } from "react-router-dom";
import { RouteErrorBoundary } from "@/app/layout/RouteErrorBoundary";
import { installRemoteAuthFetch } from "@/app/layout/remoteAuthPrompt";
import { onWorkspaceSwitching } from "@/app/state/workspaceSwitchEvents";
import { ToastProvider } from "@/components/ui/toast";
import { createAppQueryClient } from "@/lib/query-client";
import { applyTextScale } from "@/lib/ui-scale";
import { applyUiTheme } from "@/lib/ui-theme";
import { bootPlugins } from "@/plugins/runtime";
import App from "./App";
import "./styles/tailwind.css";

// Before the first API call: a 503 needs_auth opens the verification-code dialog.
installRemoteAuthFetch();

const queryClient = createAppQueryClient();
onWorkspaceSwitching(() => {
  // Cancel first: late responses from the previous connection cannot repopulate caches.
  void queryClient.cancelQueries();
  queryClient.clear();
});

// Before the first paint: every token is rem, so this sizes the whole UI.
applyTextScale();
applyUiTheme();

// A data router (vs. the plain <BrowserRouter>) is required so in-app navigation
// can be intercepted with `useBlocker` — e.g. to confirm before discarding
// unsaved workflow-graph edits. App reads `location` directly, so a single
// splat route renders the whole SPA.
//
// `errorElement` replaces React Router's bare "Unexpected Application Error!"
// overlay with a styled screen covering 404s and unreachable-backend
// (`Failed to fetch`) failures that escape the in-app ErrorBoundary.
const router = createBrowserRouter([
  { path: "*", element: <App />, errorElement: <RouteErrorBoundary /> },
]);

const rootElement = document.getElementById("root");

if (!rootElement) {
  throw new Error("Root element #root not found");
}

async function enableMocking() {
  if (!__USE_MOCK__) {
    return;
  }

  const { start } = await import("../mocks/browser");

  // `start()` returns a Promise that resolves
  // once the Service Worker is up and ready to intercept requests.
  return start();
}

enableMocking().then(async () => {
  // Service worker (in dev:mock mode) is now in control of the page —
  // safe to fire plugin discovery without racing MSW activation.
  await bootPlugins();

  const root = ReactDOM.createRoot(rootElement);
  // No <React.StrictMode>: its dev-only double-mount re-initializes
  // @flowgram.ai/free-layout-editor's inversify container, which then throws
  // "Ambiguous match found for serviceIdentifier: FlowRendererRegistry" on
  // every workflow-graph surface. Production builds never double-mount, so
  // this changes dev behavior only. Re-enable if flowgram becomes
  // StrictMode-safe upstream.
  root.render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <RouterProvider router={router} />
      </ToastProvider>
    </QueryClientProvider>,
  );
});

/**
 * Sign in (L15): the molab mark, "Sign in to <host>", two fields, one
 * full-width button that says what it does, the server's message under the
 * password when it fails, and the real command that resets a password.
 */

import { Button, Input, Label } from "@molcrafts/ui";
import { Eye, EyeOff, LoaderCircle } from "lucide-react";
import { type FormEvent, type JSX, useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "@/app/auth/AuthContext";
import { ProductMark } from "@/app/shell/ProductMark";
import { cn } from "@/lib/utils";

/** Default username matches CLI ``molab auth login`` bootstrap. */
const DEFAULT_USERNAME = "admin";
const PAGE_TITLE = "Sign in · molab";

export function LoginPage(): JSX.Element {
  const { login, enabled, authenticated, loading } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const next = params.get("next") || "/";

  const [username, setUsername] = useState(DEFAULT_USERNAME);
  const [password, setPassword] = useState("");
  const [shown, setShown] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const passwordRef = useRef<HTMLInputElement | null>(null);

  // The tab says where you are; the shell's title comes back on the way out.
  useEffect(() => {
    const previous = document.title;
    document.title = PAGE_TITLE;
    return () => {
      document.title = previous;
    };
  }, []);

  // Auth off or already in — on to where the user was going.
  useEffect(() => {
    if (loading) return;
    if (!enabled || authenticated) {
      navigate(next, { replace: true });
    }
  }, [loading, enabled, authenticated, navigate, next]);

  const onSubmit = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(username.trim(), password);
      navigate(next, { replace: true });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Could not sign in");
      // The password is what is usually wrong: select it for retyping.
      requestAnimationFrame(() => passwordRef.current?.select());
    } finally {
      setSubmitting(false);
    }
  };

  const host = typeof window === "undefined" ? "" : window.location.host;

  return (
    <main className="flex min-h-screen items-center justify-center bg-surface-subtle px-4">
      <div className="flex w-full max-w-sm flex-col gap-6">
        <header className="flex flex-col items-start gap-4">
          <span className="flex items-center gap-2 text-title font-semibold text-foreground">
            <ProductMark className="size-6 text-accent" />
            molab
          </span>
          <div className="flex flex-col gap-1">
            <h1 className="text-title font-semibold text-foreground">Sign in</h1>
            {host ? (
              <p className="text-body text-muted-foreground">
                to <span className="font-mono text-foreground">{host}</span>
              </p>
            ) : null}
          </div>
        </header>

        <form className="flex flex-col gap-4" onSubmit={(event) => void onSubmit(event)} noValidate>
          <div className="flex flex-col gap-2">
            <Label htmlFor="username">Username</Label>
            <Input
              id="username"
              name="username"
              autoComplete="username"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              required
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="password">Password</Label>
            <div className="relative">
              <Input
                ref={passwordRef}
                id="password"
                name="password"
                type={shown ? "text" : "password"}
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                aria-invalid={error ? true : undefined}
                aria-describedby={error ? "login-error" : undefined}
                className={cn("pr-8", error && "border-destructive focus-visible:ring-destructive")}
                required
              />
              <button
                type="button"
                onClick={() => setShown((value) => !value)}
                aria-label={shown ? "Hide password" : "Show password"}
                title={shown ? "Hide password" : "Show password"}
                className="absolute inset-y-0 right-0 flex w-8 items-center justify-center text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              >
                {shown ? (
                  <EyeOff aria-hidden className="size-icon-sm" />
                ) : (
                  <Eye aria-hidden className="size-icon-sm" />
                )}
              </button>
            </div>
            {error ? (
              <p id="login-error" role="alert" className="text-label text-destructive">
                {error}
              </p>
            ) : null}
          </div>
          <Button type="submit" className="w-full" disabled={submitting} aria-busy={submitting}>
            {submitting ? (
              <LoaderCircle aria-hidden className="size-icon-sm mol-motion-progress-spin" />
            ) : null}
            {submitting ? "Signing in…" : "Sign in"}
          </Button>
        </form>

        <p className="text-label leading-relaxed text-muted-foreground">
          Forgot the password? An admin resets it with{" "}
          <code className="font-mono text-foreground">molab auth users passwd &lt;name&gt;</code>.
        </p>
      </div>
    </main>
  );
}

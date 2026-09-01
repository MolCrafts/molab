import { LogOut } from "lucide-react";
import { useAuth } from "@/app/auth/AuthContext";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

/** Header control: only renders when auth is enabled and a user is signed in. */
export function UserMenu(): JSX.Element | null {
  const { enabled, authenticated, user, logout } = useAuth();

  if (!enabled || !authenticated || !user) {
    return null;
  }

  const initials =
    user.username
      .split(/[\s._-]+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0]?.toUpperCase())
      .join("") || "U";

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="icon-sm"
          className="rounded-full bg-background font-mono text-micro"
          aria-label="Account menu"
          title={user.username}
        >
          <span aria-hidden>{initials}</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-48">
        <DropdownMenuLabel className="font-normal">
          <div className="flex flex-col gap-0.5">
            <span className="text-body font-medium">{user.username}</span>
            <span className="text-micro text-muted-foreground">{user.role}</span>
          </div>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          onSelect={() => {
            void logout();
          }}
        >
          <LogOut className="h-4 w-4" />
          Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

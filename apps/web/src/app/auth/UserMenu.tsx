import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@molcrafts/ui";
import { CircleUser, LogOut } from "lucide-react";
import { useAuth } from "@/app/auth/AuthContext";
import { ActivityBarButton } from "@/components/layout/ExplorerShell";

/**
 * Accounts (L00): the activity bar's foot, as in VS Code. Only renders when
 * auth is enabled and a user is signed in.
 */
export function UserMenu(): JSX.Element | null {
  const { enabled, authenticated, user, logout } = useAuth();

  if (!enabled || !authenticated || !user) {
    return null;
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <ActivityBarButton label={`Account — ${user.username}`} icon={CircleUser} />
      </DropdownMenuTrigger>
      <DropdownMenuContent side="right" align="end" className="w-48">
        <DropdownMenuLabel className="font-normal">
          <div className="flex flex-col gap-hairline">
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
          <LogOut className="size-icon" />
          Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

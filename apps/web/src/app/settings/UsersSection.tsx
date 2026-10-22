import { WorkbenchIconAction } from "@/components/workbench";
/**
 * Settings → Users — admin-only filesystem user management.
 * Data via TanStack Query (list + mutations); chrome via shared SettingsSection.
 */

import {
  Badge,
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Input,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@molcrafts/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Plus, Trash2, X } from "lucide-react";
import { useState } from "react";
import { useAuth } from "@/app/auth/AuthContext";
import * as authApi from "@/app/auth/api";
import { DeniedHint } from "@/app/auth/DeniedHint";
import { authKeys } from "@/app/auth/keys";
import type { AuthRole, AuthUser } from "@/app/auth/types";
import { usePermissions } from "@/app/auth/usePermissions";
import { SettingsSection } from "@/components/settings";

const ROLES: AuthRole[] = ["admin", "operator", "viewer"];

export function UsersSection({ sectionId = "users" }: { sectionId?: string }): JSX.Element {
  const { user: me } = useAuth();
  const { usersDeniedReason, canManageUsers } = usePermissions();
  const queryClient = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [formUser, setFormUser] = useState("");
  const [formPassword, setFormPassword] = useState("");
  const [formRole, setFormRole] = useState<AuthRole>("operator");
  const [formWorkspaces, setFormWorkspaces] = useState("*");
  const [formError, setFormError] = useState<string | null>(null);

  const usersQuery = useQuery({
    queryKey: authKeys.users(),
    queryFn: authApi.fetchUsers,
    enabled: me?.role === "admin",
  });

  const invalidate = async (): Promise<void> => {
    await queryClient.invalidateQueries({ queryKey: authKeys.users() });
  };

  const createMutation = useMutation({
    mutationFn: authApi.createUser,
    onSuccess: async () => {
      await invalidate();
      setCreateOpen(false);
      setFormUser("");
      setFormPassword("");
      setFormRole("operator");
      setFormWorkspaces("*");
      setFormError(null);
    },
    onError: (err: Error) => setFormError(err.message),
  });

  const deleteMutation = useMutation({
    mutationFn: authApi.deleteUser,
    onSuccess: invalidate,
  });

  const patchMutation = useMutation({
    mutationFn: ({
      username,
      patch,
    }: {
      username: string;
      patch: { role?: AuthRole; disabled?: boolean; workspaces?: string[] };
    }) => authApi.patchUser(username, patch),
    onSuccess: invalidate,
  });

  const users = usersQuery.data ?? [];

  if (!canManageUsers) {
    return (
      <SettingsSection
        id={sectionId}
        title="Users"
        description="Admin only — manage filesystem accounts for this serve process."
      >
        <p className="text-body text-muted-foreground" title={usersDeniedReason ?? undefined}>
          {usersDeniedReason ?? "You need the admin role to manage users."}
        </p>
      </SettingsSection>
    );
  }

  return (
    <SettingsSection
      id={sectionId}
      title="Users"
      description="Filesystem accounts under ~/.molab/auth/ (CLI: molab auth users …)."
      trailing={
        <DeniedHint reason={usersDeniedReason}>
          <WorkbenchIconAction
            label="Add user"
            onClick={() => setCreateOpen(true)}
            disabled={Boolean(usersDeniedReason)}
          >
            <Plus aria-hidden />
          </WorkbenchIconAction>
        </DeniedHint>
      }
    >
      {usersQuery.isLoading ? (
        <p className="text-body text-muted-foreground">Loading users…</p>
      ) : usersQuery.isError ? (
        <p className="text-body text-destructive" role="alert">
          {usersQuery.error instanceof Error ? usersQuery.error.message : "Failed to load users"}
        </p>
      ) : users.length === 0 ? (
        <p className="text-body text-muted-foreground">No users yet.</p>
      ) : (
        <div className="overflow-x-auto rounded-control border border-border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Username</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Workspaces</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="w-16" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {users.map((u: AuthUser) => (
                <TableRow key={u.username}>
                  <TableCell className="font-medium">{u.username}</TableCell>
                  <TableCell>
                    <Select
                      value={u.role}
                      onValueChange={(role) => {
                        void patchMutation.mutateAsync({
                          username: u.username,
                          patch: { role: role as AuthRole },
                        });
                      }}
                      disabled={patchMutation.isPending}
                    >
                      <SelectTrigger className="h-control-compact w-32">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {ROLES.map((r) => (
                          <SelectItem key={r} value={r}>
                            {r}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </TableCell>
                  <TableCell className="max-w-48 truncate font-mono text-micro">
                    {u.workspaces.join(", ")}
                  </TableCell>
                  <TableCell>
                    {u.disabled ? (
                      <Badge variant="destructive">disabled</Badge>
                    ) : (
                      <Badge variant="secondary">active</Badge>
                    )}
                  </TableCell>
                  <TableCell>
                    <WorkbenchIconAction
                      label={`Delete ${u.username}`}
                      disabled={deleteMutation.isPending || u.username === me?.username}
                      onClick={() => {
                        if (window.confirm(`Delete user ${u.username}? This cannot be undone.`)) {
                          void deleteMutation.mutateAsync(u.username);
                        }
                      }}
                    >
                      <Trash2 className="size-icon" />
                    </WorkbenchIconAction>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add user</DialogTitle>
          </DialogHeader>
          <div className="flex flex-col gap-3 py-2">
            <div className="flex flex-col gap-2">
              <Label htmlFor="new-username">Username</Label>
              <Input
                id="new-username"
                value={formUser}
                onChange={(e) => setFormUser(e.target.value)}
                autoComplete="off"
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="new-password">Password</Label>
              <Input
                id="new-password"
                type="password"
                value={formPassword}
                onChange={(e) => setFormPassword(e.target.value)}
                autoComplete="new-password"
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label>Role</Label>
              <Select value={formRole} onValueChange={(v) => setFormRole(v as AuthRole)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {ROLES.map((r) => (
                    <SelectItem key={r} value={r}>
                      {r}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="new-ws">Workspaces</Label>
              <Input
                id="new-ws"
                value={formWorkspaces}
                onChange={(e) => setFormWorkspaces(e.target.value)}
                placeholder="* or key1,key2"
              />
              <p className="text-micro text-muted-foreground">
                Comma-separated served keys, or * for all.
              </p>
            </div>
            {formError ? (
              <p className="text-body text-destructive" role="alert">
                {formError}
              </p>
            ) : null}
          </div>
          <DialogFooter>
            <WorkbenchIconAction label="Cancel" onClick={() => setCreateOpen(false)}>
              <X aria-hidden />
            </WorkbenchIconAction>
            <WorkbenchIconAction
              label={createMutation.isPending ? "Creating user…" : "Create user"}
              disabled={createMutation.isPending || !formUser.trim() || !formPassword}
              onClick={() => {
                setFormError(null);
                const workspaces = formWorkspaces
                  .split(",")
                  .map((s) => s.trim())
                  .filter(Boolean);
                void createMutation.mutateAsync({
                  username: formUser.trim(),
                  password: formPassword,
                  role: formRole,
                  workspaces: workspaces.length ? workspaces : ["*"],
                });
              }}
            >
              <Check aria-hidden />
            </WorkbenchIconAction>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </SettingsSection>
  );
}

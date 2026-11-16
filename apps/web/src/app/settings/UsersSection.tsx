/**
 * Settings › Users (L11, admin only): each account is a setting — its name
 * (You for the signed-in one, Disabled when it is), "workspaces" as the
 * description, and the role and Remove under it. Adding is the last setting.
 */

import {
  Button,
  Input,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@molcrafts/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type JSX, useState } from "react";
import { useAuth } from "@/app/auth/AuthContext";
import * as authApi from "@/app/auth/api";
import { authKeys } from "@/app/auth/keys";
import type { AuthRole, AuthUser } from "@/app/auth/types";
import { usePermissions } from "@/app/auth/usePermissions";
import { useConfirm } from "@/components/ConfirmDialog";
import { AppDialog } from "@/components/dialog/AppDialog";
import { SettingActions, SettingItem, SettingTag } from "@/components/settings";
import type { SettingEntry } from "./settingsModel";

const ROLES: AuthRole[] = ["admin", "operator", "viewer"];

const AddUser = ({ category }: { category?: string }): JSX.Element => {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<AuthRole>("operator");
  const [workspaces, setWorkspaces] = useState("*");
  const [error, setError] = useState<string | null>(null);
  const create = useMutation({
    mutationFn: authApi.createUser,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: authKeys.users() });
      setOpen(false);
      setUsername("");
      setPassword("");
      setRole("operator");
      setWorkspaces("*");
      setError(null);
    },
    onError: (cause: Error) => setError(cause.message),
  });
  return (
    <SettingItem
      id="users-add"
      category={category}
      title="Add a user"
      description="A filesystem account for this serve process."
    >
      <SettingActions>
        <Button size="sm" variant="secondary" onClick={() => setOpen(true)}>
          Add user
        </Button>
      </SettingActions>
      <AppDialog
        open={open}
        onOpenChange={setOpen}
        title="Add user"
        size="wide"
        primaryLabel="Add user"
        busyLabel="Adding…"
        busy={create.isPending}
        primaryDisabled={!username.trim() || !password}
        onPrimary={() => {
          setError(null);
          const keys = workspaces
            .split(",")
            .map((key) => key.trim())
            .filter(Boolean);
          void create.mutateAsync({
            username: username.trim(),
            password,
            role,
            workspaces: keys.length ? keys : ["*"],
          });
        }}
        error={error}
      >
        <div className="grid gap-2">
          <Label htmlFor="new-username">Username</Label>
          <Input
            id="new-username"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            autoComplete="off"
          />
        </div>
        <div className="grid gap-2">
          <Label htmlFor="new-password">Password</Label>
          <Input
            id="new-password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="new-password"
          />
        </div>
        <div className="grid gap-2">
          <Label>Role</Label>
          <Select value={role} onValueChange={(value) => setRole(value as AuthRole)}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {ROLES.map((item) => (
                <SelectItem key={item} value={item}>
                  {item}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="grid gap-2">
          <Label htmlFor="new-ws">Workspaces</Label>
          <Input
            id="new-ws"
            value={workspaces}
            onChange={(event) => setWorkspaces(event.target.value)}
            placeholder="* or key1,key2"
          />
          <p className="text-micro text-muted-foreground">
            Comma-separated served keys, or * for all.
          </p>
        </div>
      </AppDialog>
    </SettingItem>
  );
};

const UserSetting = ({
  account,
  self,
  category,
  busy,
  onRole,
  onRemove,
}: {
  account: AuthUser;
  self: boolean;
  category?: string;
  busy: boolean;
  onRole: (role: AuthRole) => void;
  onRemove: () => void;
}): JSX.Element => {
  const { confirm, dialog } = useConfirm();
  return (
    <SettingItem
      id={`user-${account.username}`}
      category={category}
      title={account.username}
      tag={
        self ? (
          <SettingTag>You</SettingTag>
        ) : account.disabled ? (
          <SettingTag>Disabled</SettingTag>
        ) : null
      }
      description={
        <span>
          Workspaces <span className="font-mono">{account.workspaces.join(", ")}</span>
        </span>
      }
    >
      <SettingActions>
        <Select
          value={account.role}
          disabled={busy}
          onValueChange={(role) => onRole(role as AuthRole)}
        >
          <SelectTrigger aria-label={`Role of ${account.username}`} className="w-36">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {ROLES.map((role) => (
              <SelectItem key={role} value={role}>
                {role}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button
          size="sm"
          variant="secondary"
          disabled={busy || self}
          title={self ? "You cannot remove yourself" : undefined}
          onClick={() =>
            void confirm({
              title: `Delete user “${account.username}”?`,
              description: "The account is removed. This cannot be undone.",
              confirmLabel: "Delete user",
              destructive: true,
            }).then((confirmed) => {
              if (confirmed) onRemove();
            })
          }
        >
          Remove
        </Button>
      </SettingActions>
      {dialog}
    </SettingItem>
  );
};

export const useUserEntries = (): SettingEntry[] => {
  const { user: me } = useAuth();
  const { usersDeniedReason, canManageUsers } = usePermissions();
  const queryClient = useQueryClient();
  const users = useQuery({
    queryKey: authKeys.users(),
    queryFn: authApi.fetchUsers,
    enabled: canManageUsers && me?.role === "admin",
  });
  const invalidate = (): Promise<void> =>
    queryClient.invalidateQueries({ queryKey: authKeys.users() });
  const remove = useMutation({ mutationFn: authApi.deleteUser, onSuccess: invalidate });
  const patch = useMutation({
    mutationFn: ({ username, role }: { username: string; role: AuthRole }) =>
      authApi.patchUser(username, { role }),
    onSuccess: invalidate,
  });

  if (!canManageUsers) {
    const text = usersDeniedReason ?? "You need the admin role to manage users.";
    return [
      {
        id: "users:denied",
        title: "Users",
        description: text,
        render: (category) => (
          <SettingItem key="denied" category={category} title="Users" description={text} />
        ),
      },
    ];
  }

  const userEntry = (account: AuthUser): SettingEntry => ({
    id: `user:${account.username}`,
    title: account.username,
    description: `${account.role} ${account.workspaces.join(" ")}`,
    keywords: ["user", "account"],
    render: (category) => (
      <UserSetting
        key={account.username}
        account={account}
        self={account.username === me?.username}
        category={category}
        busy={patch.isPending || remove.isPending}
        onRole={(role) => void patch.mutateAsync({ username: account.username, role })}
        onRemove={() => void remove.mutateAsync(account.username)}
      />
    ),
  });

  const add: SettingEntry = {
    id: "users:add",
    title: "Add a user",
    description: "A filesystem account for this serve process.",
    render: (category) => <AddUser key="add" category={category} />,
  };
  if (users.isPending || users.isError) {
    const text = users.isPending
      ? "Loading users…"
      : users.error instanceof Error
        ? users.error.message
        : "Could not load users";
    return [
      {
        id: "users:status",
        title: "Users",
        render: (category) => (
          <SettingItem key="status" category={category} title="Users">
            <p
              role={users.isError ? "alert" : undefined}
              className="text-label text-muted-foreground"
            >
              {text}
            </p>
          </SettingItem>
        ),
      },
      add,
    ];
  }
  return [...users.data.map(userEntry), add];
};

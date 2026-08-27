import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Search, ShieldCheck, ShieldOff } from "lucide-react";

import {
  Alert,
  Badge,
  Button,
  Card,
  Input,
  LoadingState,
  Select,
} from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import type { AdminUser, Paginated, UserRole } from "@/lib/types";
import { formatDate } from "@/lib/utils";
import { ROLE_LABELS, useAuthStore } from "@/store/auth";

const ROLES: UserRole[] = ["owner", "accountant", "hr", "admin"];

export function AdminUsersPage() {
  const queryClient = useQueryClient();
  const currentUser = useAuthStore((state) => state.user);
  const [search, setSearch] = useState("");
  const [error, setError] = useState<string | null>(null);

  const users = useQuery({
    queryKey: ["admin-users", search],
    queryFn: async () => {
      const { data } = await api.get<Paginated<AdminUser>>("/api/v1/admin/users", {
        params: { search: search.trim() || undefined },
      });
      return data;
    },
  });

  const update = useMutation({
    mutationFn: async ({
      id,
      ...payload
    }: {
      id: string;
      role?: UserRole;
      is_active?: boolean;
    }) => {
      await api.patch(`/api/v1/admin/users/${id}`, payload);
    },
    onSuccess: () => {
      setError(null);
      void queryClient.invalidateQueries({ queryKey: ["admin-users"] });
    },
    onError: (caught) => setError(errorMessage(caught, "Không cập nhật được tài khoản")),
  });

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-4xl px-4 py-6">
        <header className="mb-5">
          <h1 className="text-xl font-semibold text-ink">Quản lý người dùng</h1>
          <p className="mt-1 text-sm text-muted">
            {users.data?.total ?? 0} tài khoản. Vô hiệu hóa sẽ chặn đăng nhập ngay lần sau.
          </p>
        </header>

        {error && (
          <div className="mb-4">
            <Alert>{error}</Alert>
          </div>
        )}

        <div className="relative mb-4">
          <Search className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-2" aria-hidden />
          <Input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Tìm theo email, tên hoặc doanh nghiệp"
            className="pl-9"
          />
        </div>

        {users.isLoading && <LoadingState />}

        <ul className="space-y-2">
          {users.data?.items.map((user) => {
            const isSelf = user.id === currentUser?.id;
            return (
              <li key={user.id}>
                <Card className="flex flex-wrap items-center gap-3 p-4">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-medium text-ink">{user.full_name}</span>
                      {isSelf && <Badge tone="brand">bạn</Badge>}
                      {!user.is_active && <Badge tone="danger">đã vô hiệu hóa</Badge>}
                    </div>
                    <p className="text-xs text-muted-2">
                      {user.email}
                      {user.organization_name && ` · ${user.organization_name}`} · tạo{" "}
                      {formatDate(user.created_at)}
                    </p>
                  </div>

                  <Select
                    value={user.role}
                    // Tự hạ quyền chính mình là cách nhanh nhất để khóa cửa hệ thống.
                    disabled={isSelf}
                    onChange={(event) =>
                      update.mutate({ id: user.id, role: event.target.value as UserRole })
                    }
                    className="w-44"
                  >
                    {ROLES.map((role) => (
                      <option key={role} value={role}>
                        {ROLE_LABELS[role]}
                      </option>
                    ))}
                  </Select>

                  <Button
                    variant={user.is_active ? "ghost" : "secondary"}
                    size="sm"
                    disabled={isSelf}
                    onClick={() => update.mutate({ id: user.id, is_active: !user.is_active })}
                  >
                    {user.is_active ? (
                      <>
                        <ShieldOff className="size-4" aria-hidden />
                        Vô hiệu hóa
                      </>
                    ) : (
                      <>
                        <ShieldCheck className="size-4" aria-hidden />
                        Kích hoạt
                      </>
                    )}
                  </Button>
                </Card>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}

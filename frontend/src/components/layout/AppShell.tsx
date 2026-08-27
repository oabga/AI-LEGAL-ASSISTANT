/** Khung layout chung: sidebar điều hướng + vùng nội dung. */
import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import {
  BookText,
  CalendarCheck,
  FileSearch,
  FlaskConical,
  LayoutDashboard,
  LogOut,
  Database,
  Menu,
  MessagesSquare,
  Users,
  X,
} from "lucide-react";

import { Button } from "@/components/ui";
import { cn } from "@/lib/utils";
import { ROLE_LABELS, useAuthStore } from "@/store/auth";

type NavItem = {
  to: string;
  label: string;
  icon: typeof MessagesSquare;
  adminOnly?: boolean;
};

const NAV_GROUPS: { heading: string; items: NavItem[] }[] = [
  {
    heading: "Làm việc",
    items: [
      { to: "/chat", label: "Hỏi đáp pháp lý", icon: MessagesSquare },
      { to: "/laws", label: "Tra cứu văn bản", icon: BookText },
      { to: "/contracts", label: "Soát xét hợp đồng", icon: FileSearch },
      { to: "/compliance", label: "Lịch tuân thủ", icon: CalendarCheck },
    ],
  },
  {
    heading: "Quản trị",
    items: [
      { to: "/admin/corpus", label: "Kho văn bản", icon: Database, adminOnly: true },
      { to: "/admin/users", label: "Người dùng", icon: Users, adminOnly: true },
      { to: "/lab/competition", label: "Lab thi đấu", icon: FlaskConical, adminOnly: true },
    ],
  },
];

export function AppShell() {
  const user = useAuthStore((state) => state.user);
  const logout = useAuthStore((state) => state.logout);
  const navigate = useNavigate();
  const [mobileOpen, setMobileOpen] = useState(false);

  const isAdmin = user?.role === "admin";
  const groups = NAV_GROUPS.map((group) => ({
    ...group,
    items: group.items.filter((item) => !item.adminOnly || isAdmin),
  })).filter((group) => group.items.length > 0);

  async function handleLogout() {
    await logout();
    navigate("/login", { replace: true });
  }

  return (
    <div className="flex h-full">
      {/* Overlay cho sidebar trên mobile. */}
      {mobileOpen && (
        <button
          type="button"
          aria-label="Đóng menu"
          className="fixed inset-0 z-20 bg-black/60 md:hidden"
          onClick={() => setMobileOpen(false)}
        />
      )}

      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-30 flex w-64 flex-col border-r border-line bg-sidebar",
          "transition-transform md:static md:translate-x-0",
          mobileOpen ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <div className="flex items-center justify-between px-4 py-4">
          <div className="flex items-center gap-2">
            <span className="grid size-8 place-items-center rounded-lg bg-brand text-sm font-bold text-white">
              PL
            </span>
            <div className="leading-tight">
              <p className="text-sm font-semibold text-ink">Trợ lý Pháp lý</p>
              <p className="text-xs text-muted-2">Dành cho DNNVV</p>
            </div>
          </div>
          <Button
            variant="ghost"
            size="icon"
            className="md:hidden"
            onClick={() => setMobileOpen(false)}
            aria-label="Đóng menu"
          >
            <X className="size-4" />
          </Button>
        </div>

        <nav className="flex-1 overflow-y-auto px-2 pb-4">
          {groups.map((group) => (
            <div key={group.heading} className="mb-4">
              <p className="px-3 pb-1.5 text-xs font-medium tracking-wide text-muted-2 uppercase">
                {group.heading}
              </p>
              <ul className="space-y-0.5">
                {group.items.map((item) => (
                  <li key={item.to}>
                    <NavLink
                      to={item.to}
                      onClick={() => setMobileOpen(false)}
                      className={({ isActive }) =>
                        cn(
                          "flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm transition-colors",
                          isActive
                            ? "bg-brand-soft text-brand"
                            : "text-muted hover:bg-surface-2 hover:text-ink",
                        )
                      }
                    >
                      <item.icon className="size-4 shrink-0" aria-hidden />
                      {item.label}
                    </NavLink>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </nav>

        <div className="border-t border-line-soft p-3">
          <NavLink
            to="/profile"
            onClick={() => setMobileOpen(false)}
            className="flex items-center gap-2.5 rounded-lg px-2 py-2 hover:bg-surface-2"
          >
            <span className="grid size-8 shrink-0 place-items-center rounded-full bg-surface-3 text-xs font-semibold text-ink">
              {user?.full_name?.trim().charAt(0).toUpperCase() ?? "?"}
            </span>
            <span className="min-w-0 flex-1 leading-tight">
              <span className="block truncate text-sm text-ink">{user?.full_name}</span>
              <span className="block truncate text-xs text-muted-2">
                {user ? ROLE_LABELS[user.role] : ""}
              </span>
            </span>
          </NavLink>
          <Button
            variant="ghost"
            size="sm"
            className="mt-1 w-full justify-start"
            onClick={handleLogout}
          >
            <LogOut className="size-4" aria-hidden />
            Đăng xuất
          </Button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-12 items-center gap-2 border-b border-line px-3 md:hidden">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setMobileOpen(true)}
            aria-label="Mở menu"
          >
            <Menu className="size-4" />
          </Button>
          <span className="flex items-center gap-1.5 text-sm font-medium text-ink">
            <LayoutDashboard className="size-4 text-muted" aria-hidden />
            Trợ lý Pháp lý
          </span>
        </header>
        <main className="min-h-0 flex-1 overflow-hidden">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

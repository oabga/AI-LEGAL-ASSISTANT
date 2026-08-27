import { lazy, Suspense, useEffect } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Outlet, Route, Routes } from "react-router-dom";

import { AppShell } from "@/components/layout/AppShell";
import { LoadingState } from "@/components/ui";
import { ChatPage } from "@/pages/ChatPage";
import { CompliancePage } from "@/pages/CompliancePage";
import { ContractDetailPage } from "@/pages/ContractDetailPage";
import { ContractsPage } from "@/pages/ContractsPage";
import { LawDetailPage } from "@/pages/LawDetailPage";
import { LawsPage } from "@/pages/LawsPage";
import { LoginPage } from "@/pages/LoginPage";
import { ProfilePage } from "@/pages/ProfilePage";
import { RegisterPage } from "@/pages/RegisterPage";
import { useAuthStore } from "@/store/auth";

// Trang admin và lab chỉ dành cho một người trong cả hệ thống, tách khỏi bundle
// chính để người dùng thường không phải tải về.
const AdminCorpusPage = lazy(() =>
  import("@/pages/AdminCorpusPage").then((module) => ({ default: module.AdminCorpusPage })),
);
const AdminUsersPage = lazy(() =>
  import("@/pages/AdminUsersPage").then((module) => ({ default: module.AdminUsersPage })),
);
const LabCompetitionPage = lazy(() =>
  import("@/pages/LabCompetitionPage").then((module) => ({ default: module.LabCompetitionPage })),
);

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Dữ liệu pháp luật thay đổi rất chậm, không cần refetch khi đổi tab.
      refetchOnWindowFocus: false,
      staleTime: 30_000,
      retry: 1,
    },
  },
});

/** Chặn route cần đăng nhập; chờ restore xong để không nháy sang /login. */
function RequireAuth({ adminOnly = false }: { adminOnly?: boolean }) {
  const { user, initializing } = useAuthStore();

  if (initializing) return <LoadingState label="Đang kiểm tra phiên đăng nhập…" />;
  if (!user) return <Navigate to="/login" replace />;
  if (adminOnly && user.role !== "admin") return <Navigate to="/chat" replace />;
  return <Outlet />;
}

/** Người đã đăng nhập không cần thấy trang login/register nữa. */
function RequireAnonymous() {
  const { user, initializing } = useAuthStore();

  if (initializing) return <LoadingState label="Đang kiểm tra phiên đăng nhập…" />;
  return user ? <Navigate to="/chat" replace /> : <Outlet />;
}

function AppRoutes() {
  const restore = useAuthStore((state) => state.restore);

  useEffect(() => {
    void restore();
  }, [restore]);

  return (
    <Routes>
      <Route element={<RequireAnonymous />}>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
      </Route>

      <Route element={<RequireAuth />}>
        <Route element={<AppShell />}>
          <Route index element={<Navigate to="/chat" replace />} />
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/chat/:conversationId" element={<ChatPage />} />
          <Route path="/laws" element={<LawsPage />} />
          {/* Số hiệu văn bản chứa dấu "/" nên phải bắt phần còn lại của path. */}
          <Route path="/laws/:lawId/*" element={<LawDetailPage />} />
          <Route path="/contracts" element={<ContractsPage />} />
          <Route path="/contracts/:documentId" element={<ContractDetailPage />} />
          <Route path="/compliance" element={<CompliancePage />} />
          <Route path="/profile" element={<ProfilePage />} />

          <Route
            element={
              <Suspense fallback={<LoadingState />}>
                <RequireAuth adminOnly />
              </Suspense>
            }
          >
            <Route path="/admin/corpus" element={<AdminCorpusPage />} />
            <Route path="/admin/users" element={<AdminUsersPage />} />
            <Route path="/lab/competition" element={<LabCompetitionPage />} />
          </Route>
        </Route>
      </Route>

      <Route path="*" element={<Navigate to="/chat" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </QueryClientProvider>
  );
}

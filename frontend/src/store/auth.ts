/** Store xác thực: user hiện tại + hành động login/register/logout. */
import { create } from "zustand";

import { api, errorMessage, setAuthFailureHandler } from "@/lib/api";
import { clearTokens, readTokens, writeTokens } from "@/lib/tokens";
import type { AuthResponse, Organization, User, UserRole } from "@/lib/types";

export type RegisterPayload = {
  email: string;
  password: string;
  full_name: string;
  role?: UserRole;
  organization?: Partial<Organization> | null;
};

type AuthState = {
  user: User | null;
  /** true cho tới khi đã thử khôi phục phiên từ token đã lưu. */
  initializing: boolean;
  error: string | null;
  restore: () => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  register: (payload: RegisterPayload) => Promise<void>;
  logout: () => Promise<void>;
  setUser: (user: User) => void;
  clearError: () => void;
};

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  initializing: true,
  error: null,

  restore: async () => {
    if (!readTokens()) {
      set({ user: null, initializing: false });
      return;
    }
    try {
      const { data } = await api.get<User>("/api/v1/auth/me");
      set({ user: data, initializing: false });
    } catch {
      // Token hết hạn hoặc user đã bị vô hiệu hóa.
      clearTokens();
      set({ user: null, initializing: false });
    }
  },

  login: async (email, password) => {
    set({ error: null });
    try {
      const { data } = await api.post<AuthResponse>("/api/v1/auth/login", {
        email,
        password,
      });
      writeTokens({ access: data.tokens.access_token, refresh: data.tokens.refresh_token });
      set({ user: data.user, initializing: false });
    } catch (error) {
      const message = errorMessage(error, "Đăng nhập thất bại");
      set({ error: message });
      throw new Error(message);
    }
  },

  register: async (payload) => {
    set({ error: null });
    try {
      const { data } = await api.post<AuthResponse>("/api/v1/auth/register", payload);
      writeTokens({ access: data.tokens.access_token, refresh: data.tokens.refresh_token });
      set({ user: data.user, initializing: false });
    } catch (error) {
      const message = errorMessage(error, "Đăng ký thất bại");
      set({ error: message });
      throw new Error(message);
    }
  },

  logout: async () => {
    try {
      // Chỉ để lại dấu trong audit log; JWT là stateless nên client phải tự xóa.
      await api.post("/api/v1/auth/logout");
    } catch {
      /* đăng xuất phải thành công cả khi server không phản hồi */
    }
    clearTokens();
    set({ user: null });
  },

  setUser: (user) => set({ user }),
  clearError: () => set({ error: null }),
}));

// Refresh token hết hiệu lực thì đưa người dùng về trạng thái chưa đăng nhập.
setAuthFailureHandler(() => {
  useAuthStore.setState({ user: null, error: "Phiên đã hết hạn, vui lòng đăng nhập lại" });
});

export const ROLE_LABELS: Record<UserRole, string> = {
  owner: "Chủ doanh nghiệp",
  accountant: "Kế toán",
  hr: "Nhân sự",
  admin: "Quản trị",
};

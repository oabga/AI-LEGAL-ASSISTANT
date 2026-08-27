/**
 * Axios instance dùng chung, tự refresh access token khi gặp 401.
 *
 * Base URL để trống trong dev để đi qua proxy của Vite (giữ URL tương đối
 * ``/api``), và lấy từ ``VITE_API_BASE_URL`` khi deploy tách domain.
 */
import axios, {
  AxiosError,
  type AxiosInstance,
  type InternalAxiosRequestConfig,
} from "axios";

import { clearTokens, getAccessToken, readTokens, writeTokens } from "./tokens";

export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

export const api: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  headers: { "Content-Type": "application/json" },
});

/** Cho phép AuthProvider phản ứng khi refresh thất bại (đưa về trang login). */
let onAuthFailure: (() => void) | null = null;

export function setAuthFailureHandler(handler: (() => void) | null): void {
  onAuthFailure = handler;
}

api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = getAccessToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  // Instance mặc định gắn application/json. FormData phải để trình duyệt tự gắn
  // multipart kèm boundary, nếu không FastAPI không đọc được file.
  if (typeof FormData !== "undefined" && config.data instanceof FormData) {
    config.headers.delete("Content-Type");
  }
  return config;
});

type RetriableConfig = InternalAxiosRequestConfig & { _retried?: boolean };

// Nhiều request cùng gặp 401 chỉ được gọi refresh một lần, các request còn lại
// chờ chung promise này để không tạo ra chuỗi refresh song song.
let refreshPromise: Promise<string> | null = null;

async function refreshAccessToken(): Promise<string> {
  const tokens = readTokens();
  if (!tokens) throw new Error("Chưa đăng nhập");

  // Gọi bằng axios gốc để không bị interceptor này bắt lại lần nữa.
  const response = await axios.post<{
    access_token: string;
    refresh_token: string;
  }>(`${API_BASE_URL}/api/v1/auth/refresh`, { refresh_token: tokens.refresh });

  writeTokens({
    access: response.data.access_token,
    refresh: response.data.refresh_token ?? tokens.refresh,
  });
  return response.data.access_token;
}

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const config = error.config as RetriableConfig | undefined;
    const isAuthEndpoint = config?.url?.includes("/api/v1/auth/");

    if (error.response?.status !== 401 || !config || config._retried || isAuthEndpoint) {
      return Promise.reject(error);
    }

    config._retried = true;
    try {
      refreshPromise ??= refreshAccessToken().finally(() => {
        refreshPromise = null;
      });
      const token = await refreshPromise;
      config.headers.Authorization = `Bearer ${token}`;
      return api.request(config);
    } catch {
      clearTokens();
      onAuthFailure?.();
      return Promise.reject(error);
    }
  },
);

/** Bóc thông báo lỗi tiếng Việt mà backend trả về trong ``detail``. */
export function errorMessage(error: unknown, fallback = "Có lỗi xảy ra"): string {
  if (axios.isAxiosError(error)) {
    const detail = (error.response?.data as { detail?: unknown } | undefined)?.detail;
    if (typeof detail === "string") return detail;
    // Lỗi 422 của FastAPI trả về mảng các lỗi validate theo từng field.
    if (Array.isArray(detail)) {
      const first = detail[0] as { msg?: string } | undefined;
      if (first?.msg) return first.msg;
    }
    if (error.code === "ERR_NETWORK") return "Không kết nối được tới server";
    return error.message || fallback;
  }
  return error instanceof Error ? error.message : fallback;
}

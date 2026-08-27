/**
 * Lưu JWT trong localStorage.
 *
 * Access token cần đọc được từ JS để gắn vào header Authorization của cả axios
 * và fetch (đường SSE), nên không dùng httpOnly cookie. Bù lại access token chỉ
 * sống 15 phút và CORS đã khóa về danh sách origin cụ thể.
 */

const ACCESS_KEY = "legal.access_token";
const REFRESH_KEY = "legal.refresh_token";

export type StoredTokens = { access: string; refresh: string };

export function readTokens(): StoredTokens | null {
  const access = localStorage.getItem(ACCESS_KEY);
  const refresh = localStorage.getItem(REFRESH_KEY);
  return access && refresh ? { access, refresh } : null;
}

export function writeTokens(tokens: StoredTokens): void {
  localStorage.setItem(ACCESS_KEY, tokens.access);
  localStorage.setItem(REFRESH_KEY, tokens.refresh);
}

export function clearTokens(): void {
  localStorage.removeItem(ACCESS_KEY);
  localStorage.removeItem(REFRESH_KEY);
}

export function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_KEY);
}

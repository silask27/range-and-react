export type AuthUser = {
  user_id: string;
  email: string;
  display_name: string | null;
  role: "owner" | "admin" | "coach" | "member";
  is_active: boolean;
};

export const AUTH_TOKEN_KEY = "vrt_auth_token";
export const AUTH_USER_KEY = "vrt_auth_user";

export function getStoredAuthToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(AUTH_TOKEN_KEY);
}

export function getStoredAuthUser(): AuthUser | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(AUTH_USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as AuthUser;
  } catch {
    return null;
  }
}

export function persistAuth(_token: string, user: AuthUser) {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(AUTH_TOKEN_KEY);
  window.localStorage.setItem(AUTH_USER_KEY, JSON.stringify(user));
}

export function setStoredAuthUser(user: AuthUser) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(AUTH_USER_KEY, JSON.stringify(user));
}

export function clearStoredAuth() {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(AUTH_TOKEN_KEY);
  window.localStorage.removeItem(AUTH_USER_KEY);
}

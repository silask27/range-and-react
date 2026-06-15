import { clearStoredAuth, getStoredAuthToken } from "./auth";

const DEFAULT_API_BASE =
  process.env.NODE_ENV === "production"
    ? "https://range-and-react.up.railway.app"
    : "http://127.0.0.1:8000";

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? DEFAULT_API_BASE;

export async function apiFetch(
  input: RequestInfo | URL,
  init: RequestInit = {},
): Promise<Response> {
  const headers = new Headers(init.headers ?? {});
  const token = getStoredAuthToken();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(input, {
    ...init,
    headers,
    credentials: init.credentials ?? "include",
  });

  if (response.status === 401 && typeof window !== "undefined") {
    clearStoredAuth();
    window.location.href = "/login";
  }

  return response;
}

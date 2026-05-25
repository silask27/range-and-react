"use client";

import { useEffect, useState } from "react";
import { apiFetch, API_BASE } from "../api";
import { getStoredAuthUser, persistAuth, type AuthUser } from "../auth";

export function useRequireAuth() {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [isAuthLoading, setIsAuthLoading] = useState(true);
  const [authError, setAuthError] = useState<string | null>(null);

  useEffect(() => {
    const storedUser = getStoredAuthUser();

    if (storedUser) {
      setUser(storedUser);
    }

    let cancelled = false;

    async function loadUser() {
      setIsAuthLoading(true);
      setAuthError(null);
      try {
        const res = await apiFetch(`${API_BASE}/auth/me`, { cache: "no-store" });
        const data = await res.json();
        if (!res.ok) {
          setAuthError(typeof data.detail === "string" ? data.detail : "Unable to load account.");
          return;
        }
        const nextUser = data.user as AuthUser;
        persistAuth("", nextUser);
        if (!cancelled) {
          setUser(nextUser);
        }
      } catch {
        if (!cancelled) {
          setAuthError("Unable to reach the server.");
        }
      } finally {
        if (!cancelled) {
          setIsAuthLoading(false);
        }
      }
    }

    void loadUser();

    return () => {
      cancelled = true;
    };
  }, []);

  return { user, isAuthLoading, authError };
}

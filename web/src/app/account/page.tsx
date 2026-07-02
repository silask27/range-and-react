"use client";

import { useEffect, useState, type CSSProperties, type FormEvent } from "react";
import Link from "next/link";
import AppShell from "../../components/app/AppShell";
import { API_BASE, apiFetch } from "../../lib/api";
import { clearStoredAuth, getStoredAuthUser, setStoredAuthUser } from "../../lib/auth";
import { useRequireAuth } from "../../lib/hooks/useRequireAuth";

type ExternalIdentity = { provider: string; external_user_id: string; external_email: string | null; created_at: string };
type Organization = { organization_id: string; name: string; slug: string; membership_role?: string; external_provider: string | null };
type MePayload = { user: { user_id: string; email: string; display_name: string | null; role: string; is_active: boolean }; external_identities: ExternalIdentity[]; organizations: Organization[] };

const SUPPORT_EMAIL = process.env.NEXT_PUBLIC_SUPPORT_EMAIL ?? "support@rangeandreact.com";

export default function AccountPage() {
  const { user, isAuthLoading, authError } = useRequireAuth();
  const [payload, setPayload] = useState<MePayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [profileName, setProfileName] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");

  async function loadMe(showLoading = true) {
    if (showLoading) setIsLoading(true);
    setError(null);
    const res = await apiFetch(`${API_BASE}/auth/me`, { cache: "no-store" });
    const data = await res.json();
    if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Unable to load account.");
    const next = data as MePayload;
    setPayload(next);
    setProfileName(next.user.display_name ?? "");
    const stored = getStoredAuthUser();
    if (stored) {
      setStoredAuthUser({
        ...stored,
        display_name: next.user.display_name,
        is_active: next.user.is_active,
        role: next.user.role as typeof stored.role,
      });
    }
    setIsLoading(false);
  }

  useEffect(() => {
    if (!user) return;
    let cancelled = false;
    setPayload((current) => current ?? { user, external_identities: [], organizations: [] });
    setProfileName((current) => current || (user.display_name ?? ""));
    setIsLoading(false);
    void (async () => {
      try {
        await loadMe(false);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Unable to load account.");
          setIsLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [user]);

  async function handleProfileUpdate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setNotice(null);
    try {
      const res = await apiFetch(`${API_BASE}/auth/profile`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ display_name: profileName }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Unable to update profile.");
      const stored = getStoredAuthUser();
      if (stored) setStoredAuthUser({ ...stored, display_name: data.user.display_name });
      setNotice("Profile updated.");
      await loadMe();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to update profile.");
    }
  }

  async function handlePasswordChange(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setNotice(null);
    try {
      const res = await apiFetch(`${API_BASE}/auth/change-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Unable to change password.");
      clearStoredAuth();
      window.location.href = "/login";
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to change password.");
    }
  }

  async function handleExport() {
    setError(null);
    setNotice(null);
    try {
      const res = await apiFetch(`${API_BASE}/auth/export`, { cache: "no-store" });
      const data = await res.json();
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Unable to export account data.");
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "range-and-react-account-export.json";
      anchor.click();
      URL.revokeObjectURL(url);
      setNotice("Account export downloaded.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to export account data.");
    }
  }

  async function handleDeactivate() {
    const confirmed = window.confirm("Deactivate this account? You will be logged out immediately.");
    if (!confirmed) return;
    try {
      const res = await apiFetch(`${API_BASE}/auth/deactivate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ confirm: true }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Unable to deactivate account.");
      clearStoredAuth();
      window.location.href = "/login";
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to deactivate account.");
    }
  }

  async function handleLogout() {
    try {
      await apiFetch(`${API_BASE}/auth/logout`, { method: "POST" });
    } finally {
      clearStoredAuth();
      window.location.href = "/login";
    }
  }

  return (
    <AppShell title="Account" subtitle="Update profile, security, linked access, and account exports in one place.">
      {(isAuthLoading && !user) || (isLoading && !payload) ? <div style={copyStyle}>Loading account…</div> : null}
      {authError ? <div style={errorStyle}>{authError}</div> : null}
      {error ? <div style={errorStyle}>{error}</div> : null}
      {notice ? <div style={noticeStyle}>{notice}</div> : null}
      {payload ? (
        <div className="open-grid-two">
          <section className="open-section open-stack">
            <div>
              <div className="page-eyebrow">Profile</div>
              <h2 style={sectionTitleStyle}>Identity</h2>
            </div>
            <form onSubmit={handleProfileUpdate} style={formStyle}>
              <label style={labelStyle}>
                Email
                <input value={payload.user.email} readOnly className="field" style={{ opacity: 0.75 }} />
              </label>
              <label style={labelStyle}>
                Display name
                <input value={profileName} onChange={(e) => setProfileName(e.target.value)} className="field" />
              </label>
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                <span className="badge badge-muted">{payload.user.role}</span>
                <span className="badge badge-muted">{payload.user.is_active ? "active" : "inactive"}</span>
              </div>
              <button type="submit" className="btn-primary" style={wideButtonStyle}>Save profile</button>
            </form>

            <div className="divider" />

            <div>
              <div className="page-eyebrow">Linked access</div>
              <h2 style={sectionTitleStyle}>Organizations and identities</h2>
            </div>
            <div style={stackStyle}>
              {payload.organizations.length ? payload.organizations.map((org) => (
                <div key={org.organization_id} style={lineRowStyle}>
                  <strong>{org.name}</strong>
                  <span style={copyStyle}>{org.slug} · {org.membership_role || "member"}</span>
                </div>
              )) : <div style={copyStyle}>No organizations linked yet.</div>}
              {payload.external_identities.length ? payload.external_identities.map((identity) => (
                <div key={`${identity.provider}-${identity.external_user_id}`} style={lineRowStyle}>
                  <strong>{identity.provider}</strong>
                  <span style={copyStyle}>{identity.external_email || identity.external_user_id}</span>
                </div>
              )) : <div style={copyStyle}>No external identities linked yet.</div>}
            </div>
          </section>

          <section className="open-section open-stack">
            <div>
              <div className="page-eyebrow">Security</div>
              <h2 style={sectionTitleStyle}>Password</h2>
            </div>
            <form onSubmit={handlePasswordChange} style={formStyle}>
              <input type="password" value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)} placeholder="Current password" className="field" />
              <input type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} placeholder="New password" className="field" />
              <div style={copyStyle}>Use this form when you are already signed in and want to update your password.</div>
              <button type="submit" className="btn-primary" style={wideButtonStyle}>Change password</button>
            </form>

            <div className="divider" />

            <div>
              <div className="page-eyebrow">Account data</div>
              <h2 style={sectionTitleStyle}>Export or deactivate</h2>
            </div>
            <div style={stackStyle}>
              <button onClick={() => void handleExport()} className="btn" style={wideButtonStyle}>Download account export</button>
              <button onClick={() => void handleDeactivate()} className="btn-primary" style={wideButtonStyle}>Deactivate account</button>
              <div style={copyStyle}>Deactivation signs you out and marks the account inactive until an admin reactivates it.</div>
            </div>

            <div className="divider" />

            <div>
              <div className="page-eyebrow">Help and session</div>
              <h2 style={sectionTitleStyle}>Docs, support, and logout</h2>
            </div>
            <div style={linkGridStyle}>
              <Link href="/guide" style={accountLinkStyle}>Guide</Link>
              <Link href="/privacy" style={accountLinkStyle}>Privacy</Link>
              <Link href="/terms" style={accountLinkStyle}>Terms</Link>
              <Link href="/status" style={accountLinkStyle}>Status</Link>
              <a href={`mailto:${SUPPORT_EMAIL}`} style={accountLinkStyle}>Support</a>
              <button type="button" onClick={() => void handleLogout()} style={logoutButtonStyle}>Log out</button>
            </div>
          </section>
        </div>
      ) : null}
    </AppShell>
  );
}

const sectionTitleStyle: CSSProperties = { margin: "6px 0 0", fontSize: 34, lineHeight: 1.05, fontWeight: 800, letterSpacing: "-.04em" };
const formStyle: CSSProperties = { display: "grid", gap: 12 };
const labelStyle: CSSProperties = { display: "grid", gap: 8, color: "var(--text-65)" };
const stackStyle: CSSProperties = { display: "grid", gap: 12 };
const lineRowStyle: CSSProperties = { display: "grid", gap: 4, paddingTop: 10, borderTop: "1px solid var(--line-soft)" };
const wideButtonStyle: CSSProperties = { width: "100%", minHeight: 52 };
const linkGridStyle: CSSProperties = { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 150px), 1fr))", gap: 10 };
const accountLinkStyle: CSSProperties = { border: "1px solid var(--line)", borderRadius: 12, padding: "12px 13px", color: "var(--text)", fontWeight: 850, textAlign: "center", background: "var(--surface-fill)" };
const logoutButtonStyle: CSSProperties = { ...accountLinkStyle, cursor: "pointer" };
const copyStyle: CSSProperties = { color: "var(--text-65)", lineHeight: 1.7 };
const errorStyle: CSSProperties = { color: "var(--accent)", fontWeight: 700 };
const noticeStyle: CSSProperties = { color: "var(--success)", fontWeight: 700 };

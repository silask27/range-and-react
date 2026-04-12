"use client";

import { FormEvent, useEffect, useMemo, useState, type CSSProperties } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { clearStoredAuth, getStoredAuthToken, getStoredAuthUser, persistAuth } from "../../lib/auth";
import SiteFooter from "../../components/app/SiteFooter";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

type Mode = "login" | "signup";

type PublicConfig = {
  support_email?: string;
  features?: {
    invite_only_access?: boolean;
  };
};

type InvitePreview = {
  invite_code: string;
  email: string | null;
  role: string;
  organization_name: string | null;
  expires_at: string | null;
};

function prettyRole(role: string | null | undefined) {
  const value = (role || "").trim().toLowerCase();
  if (!value) return "member";
  return value.charAt(0).toUpperCase() + value.slice(1);
}

export default function LoginPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [mode, setMode] = useState<Mode>("login");
  const [inviteOnly, setInviteOnly] = useState(true);
  const [supportEmail, setSupportEmail] = useState("support@example.com");
  const [invitePreview, setInvitePreview] = useState<InvitePreview | null>(null);
  const [loginEmail, setLoginEmail] = useState("");
  const [loginPassword, setLoginPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [signupEmail, setSignupEmail] = useState("");
  const [signupPassword, setSignupPassword] = useState("");
  const [inviteCode, setInviteCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [sessionNotice, setSessionNotice] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);

  const queryMode = searchParams.get("mode");
  const inviteCodeFromQuery = useMemo(
    () => searchParams.get("invite_code")?.trim() || searchParams.get("code")?.trim() || "",
    [searchParams],
  );
  const emailFromQuery = useMemo(() => searchParams.get("email")?.trim().toLowerCase() || "", [searchParams]);
  const isInviteFlow = Boolean(inviteCode.trim()) || inviteOnly;

  useEffect(() => {
    const token = getStoredAuthToken();
    if (!token) return;
    if (inviteCodeFromQuery) {
      const currentUser = getStoredAuthUser();
      setSessionNotice(currentUser ? `You are currently signed in as ${currentUser.email}. Accepting this invite will switch this browser to the new account.` : "You are currently signed in in this browser. Accepting this invite will switch this browser to the new account.");
      return;
    }
    router.replace("/dashboard");
  }, [router, inviteCodeFromQuery]);

  useEffect(() => {
    let cancelled = false;
    void fetch(`${API_BASE}/platform/public-config`, { cache: "no-store" })
      .then(async (res) => {
        const data = (await res.json()) as PublicConfig;
        if (!cancelled) {
          setInviteOnly(Boolean(data.features?.invite_only_access ?? true));
          setSupportEmail(data.support_email || "support@example.com");
        }
      })
      .catch(() => {
        if (!cancelled) {
          setInviteOnly(true);
          setSupportEmail("support@example.com");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (queryMode === "signup" || inviteCodeFromQuery) {
      setMode("signup");
      if (emailFromQuery) setSignupEmail(emailFromQuery);
    } else if (emailFromQuery) {
      setLoginEmail(emailFromQuery);
    }
    if (inviteCodeFromQuery) setInviteCode(inviteCodeFromQuery);
  }, [queryMode, inviteCodeFromQuery, emailFromQuery]);

  useEffect(() => {
    if (!inviteCode.trim()) {
      setInvitePreview(null);
      return;
    }
    let cancelled = false;
    void fetch(`${API_BASE}/auth/signup-invites/${encodeURIComponent(inviteCode.trim())}`, { cache: "no-store" })
      .then(async (res) => {
        const data = (await res.json()) as { invite?: InvitePreview; detail?: string };
        if (cancelled) return;
        if (!res.ok || !data.invite) {
          setInvitePreview(null);
          if (mode === "signup") setError(typeof data.detail === "string" ? data.detail : "That invite could not be loaded.");
          return;
        }
        setInvitePreview(data.invite);
        setError((current) => {
          if (current && current.toLowerCase().includes("invite")) return null;
          return current;
        });
        if (!signupEmail && data.invite.email) setSignupEmail(data.invite.email.toLowerCase());
      })
      .catch(() => {
        if (!cancelled) setInvitePreview(null);
      });
    return () => {
      cancelled = true;
    };
  }, [inviteCode, mode, signupEmail]);


  async function handleInviteSessionReset() {
    const token = getStoredAuthToken();
    try {
      if (token) {
        await fetch(`${API_BASE}/auth/logout`, {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
        });
      }
    } catch {
      // best-effort logout for local browser state
    } finally {
      clearStoredAuth();
      setSessionNotice(null);
      setError(null);
    }
  }

  async function handleLogin(event: FormEvent) {
    event.preventDefault();
    setIsBusy(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: loginEmail.trim().toLowerCase(), password: loginPassword }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Unable to log in.");
      persistAuth(data.token, data.user);
      router.replace("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to log in.");
    } finally {
      setIsBusy(false);
    }
  }

  async function handleSignup(event: FormEvent) {
    event.preventDefault();
    setIsBusy(true);
    setError(null);
    try {
      const body: Record<string, string> = {
        display_name: displayName.trim(),
        email: signupEmail.trim().toLowerCase(),
        password: signupPassword,
      };
      if (inviteCode.trim()) body.invite_code = inviteCode.trim();
      const res = await fetch(`${API_BASE}/auth/signup`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) {
        const message = typeof data.detail === "string" ? data.detail : "Unable to create account.";
        if (message.toLowerCase().includes("already exists")) {
          setMode("login");
          setLoginEmail(signupEmail.trim().toLowerCase());
          setLoginPassword("");
          throw new Error("That account already exists. Please log in instead.");
        }
        throw new Error(message);
      }
      persistAuth(data.token, data.user);
      router.replace("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to create account.");
    } finally {
      setIsBusy(false);
    }
  }

  return (
    <main style={pageStyle}>
      <section style={authSectionStyle}>
        <div style={authWrapStyle}>
          <div style={{ textAlign: "center", display: "grid", gap: 10 }}>
            <div className="page-eyebrow">Range & React</div>
            <h1 style={titleStyle}>{mode === "login" ? "Log in" : inviteOnly ? "Accept your invite" : "Create your account"}</h1>
            <p style={subtitleStyle}>
              {mode === "login"
                ? "Simple access to your training, results, and assignments."
                : isInviteFlow
                  ? "Use the invite from your coach or company admin to create the right account and join the correct organization."
                  : "Create a member account and get into the lab."}
            </p>
          </div>

          {sessionNotice ? (
            <div style={sessionCardStyle}>
              <div style={sessionCardTitleStyle}>Signed-in browser session detected</div>
              <div style={sessionCardCopyStyle}>{sessionNotice}</div>
              <button type="button" onClick={handleInviteSessionReset} style={sessionCardButtonStyle}>Log out and continue with invite</button>
            </div>
          ) : null}

          {mode === "login" ? (
            <form onSubmit={handleLogin} style={formStyle}>
              <input className="field" value={loginEmail} onChange={(e) => setLoginEmail(e.target.value)} placeholder="Email" type="email" required />
              <input className="field" value={loginPassword} onChange={(e) => setLoginPassword(e.target.value)} placeholder="Password" type="password" required />
              <div style={helperRowStyle}>
                <button type="button" onClick={() => router.push("/forgot-password")} style={linkButtonStyle}>Forgot password?</button>
              </div>
              {error ? <div style={errorStyle}>{error}</div> : null}
              <button disabled={isBusy} className="btn-primary" style={primaryStyle}>{isBusy ? "Logging in…" : "Log in"}</button>
              <button type="button" onClick={() => { setError(null); setMode("signup"); }} style={switchStyle}>{inviteOnly ? "Have an invite? Create your account" : "Need an account? Sign up"}</button>
            </form>
          ) : (
            <form onSubmit={handleSignup} style={formStyle}>
              {invitePreview ? (
                <div style={inviteCardStyle}>
                  <div style={inviteCardTitleStyle}>{invitePreview.organization_name || "Organization invite"}</div>
                  <div style={inviteCardCopyStyle}>
                    {invitePreview.email ? `Invited email: ${invitePreview.email}` : "This invite can be claimed with a new account."}
                    {invitePreview.expires_at ? ` Expires ${new Date(invitePreview.expires_at).toLocaleString()}.` : ""}
                  </div>
                  <div style={inviteMetaWrapStyle}>
                    <span style={inviteRoleTagStyle}>Account role {prettyRole(invitePreview.role)}</span>
                    {invitePreview.organization_name ? <span style={inviteOrgTagStyle}>{invitePreview.organization_name}</span> : null}
                  </div>
                </div>
              ) : null}
              <input className="field" value={displayName} onChange={(e) => setDisplayName(e.target.value)} placeholder="Display name" required />
              <input className="field" value={signupEmail} onChange={(e) => setSignupEmail(e.target.value)} placeholder="Email" type="email" required />
              <input className="field" value={signupPassword} onChange={(e) => setSignupPassword(e.target.value)} placeholder="Password" type="password" required />
              {isInviteFlow ? <input className="field" value={inviteCode} onChange={(e) => setInviteCode(e.target.value)} placeholder="Invite code" required /> : null}
              {error ? <div style={errorStyle}>{error}</div> : null}
              <button disabled={isBusy} className="btn-primary" style={primaryStyle}>{isBusy ? "Creating account…" : isInviteFlow ? "Accept invite" : "Create account"}</button>
              <button type="button" onClick={() => { setError(null); setMode("login"); }} style={switchStyle}>Already have an account? Log in</button>
            </form>
          )}

          <p style={supportStyle}>Need help? Contact <a href={`mailto:${supportEmail}`} style={supportLinkStyle}>{supportEmail}</a>.</p>
        </div>
      </section>
      <div style={footerWrapStyle}><SiteFooter /></div>
    </main>
  );
}

const pageStyle: CSSProperties = { minHeight: "100vh", background: "var(--bg)", color: "var(--text)", display: "grid", gridTemplateRows: "1fr auto" };
const authSectionStyle: CSSProperties = { display: "grid", placeItems: "center", padding: "40px 24px" };
const authWrapStyle: CSSProperties = { width: "min(100%, 520px)", display: "grid", gap: 22 };
const titleStyle: CSSProperties = { margin: 0, fontSize: 60, lineHeight: 0.96, letterSpacing: "-.06em", fontWeight: 820 };
const subtitleStyle: CSSProperties = { margin: 0, color: "var(--text-65)", lineHeight: 1.6, fontSize: 18 };
const formStyle: CSSProperties = { display: "grid", gap: 12 };
const errorStyle: CSSProperties = { color: "var(--accent)", fontWeight: 700, textAlign: "center" };
const primaryStyle: CSSProperties = { width: "100%", minHeight: 58, fontSize: 20 };
const switchStyle: CSSProperties = { background: "transparent", border: 0, color: "var(--text-65)", fontWeight: 700, justifySelf: "center", padding: 0 };
const footerWrapStyle: CSSProperties = { width: "min(100%, 1280px)", margin: "0 auto", padding: "0 32px 24px" };
const helperRowStyle: CSSProperties = { display: "flex", justifyContent: "flex-end" };
const linkButtonStyle: CSSProperties = { background: "transparent", border: 0, color: "var(--text-65)", fontWeight: 700, padding: 0, cursor: "pointer" };
const inviteCardStyle: CSSProperties = { border: "1px solid var(--line)", borderRadius: 18, padding: "14px 16px", background: "var(--panel)", display: "grid", gap: 6 };
const inviteCardTitleStyle: CSSProperties = { fontSize: 15, fontWeight: 800, color: "var(--text)" };
const inviteCardCopyStyle: CSSProperties = { fontSize: 14, lineHeight: 1.5, color: "var(--text-65)" };
const inviteMetaWrapStyle: CSSProperties = { display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" };
const inviteRoleTagStyle: CSSProperties = { padding: "6px 10px", borderRadius: 999, border: "1px solid rgba(231,111,81,0.45)", background: "rgba(231,111,81,0.14)", color: "var(--accent)", fontSize: 12, fontWeight: 800, textTransform: "uppercase" };
const inviteOrgTagStyle: CSSProperties = { padding: "6px 10px", borderRadius: 999, border: "1px solid var(--line)", background: "var(--surface-fill)", color: "var(--text)", fontSize: 12, fontWeight: 700 };
const sessionCardStyle: CSSProperties = { border: "1px solid var(--line)", borderRadius: 18, padding: "14px 16px", background: "var(--panel)", display: "grid", gap: 10 };
const sessionCardTitleStyle: CSSProperties = { fontSize: 15, fontWeight: 800, color: "var(--text)" };
const sessionCardCopyStyle: CSSProperties = { fontSize: 14, lineHeight: 1.5, color: "var(--text-65)" };
const sessionCardButtonStyle: CSSProperties = { justifySelf: "start", background: "var(--accent)", color: "var(--text)", border: "none", borderRadius: 999, padding: "10px 14px", fontWeight: 800, cursor: "pointer" };
const supportStyle: CSSProperties = { margin: 0, textAlign: "center", color: "var(--text-65)", fontSize: 14 };
const supportLinkStyle: CSSProperties = { color: "var(--text)", textDecoration: "underline" };

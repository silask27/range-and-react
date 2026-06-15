"use client";

import { FormEvent, Suspense, useEffect, useMemo, useState, type CSSProperties } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import SiteFooter from "../../components/app/SiteFooter";
import { API_BASE } from "../../lib/api";

function ResetPasswordPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const tokenFromQuery = useMemo(() => searchParams.get("token")?.trim() || "", [searchParams]);
  const emailFromQuery = useMemo(() => searchParams.get("email")?.trim().toLowerCase() || "", [searchParams]);
  const [resetToken, setResetToken] = useState("");
  const [emailHint, setEmailHint] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);

  useEffect(() => {
    if (tokenFromQuery) setResetToken(tokenFromQuery);
    if (emailFromQuery) setEmailHint(emailFromQuery);
  }, [tokenFromQuery, emailFromQuery]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (newPassword !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }
    setIsBusy(true);
    setError(null);
    setNotice(null);
    try {
      const res = await fetch(`${API_BASE}/auth/reset-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reset_token: resetToken.trim(), new_password: newPassword }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Unable to reset your password.");
      setNotice(typeof data.message === "string" ? data.message : "Password reset complete.");
      setTimeout(() => router.push(`/login${emailHint ? `?email=${encodeURIComponent(emailHint)}` : ""}`), 900);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to reset your password.");
    } finally {
      setIsBusy(false);
    }
  }

  return (
    <main style={pageStyle}>
      <section style={authSectionStyle}>
        <div style={authWrapStyle}>
          <div style={{ textAlign: "center", display: "grid", gap: 10 }}>
            <div className="page-eyebrow">Account recovery</div>
            <h1 style={titleStyle}>Choose a new password</h1>
            <p style={subtitleStyle}>{emailHint ? `Resetting password for ${emailHint}.` : "Paste your reset token and choose a new password."}</p>
          </div>
          <form onSubmit={handleSubmit} style={formStyle}>
            <input className="field" value={resetToken} onChange={(event) => setResetToken(event.target.value)} placeholder="Reset token" required />
            <input className="field" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} placeholder="New password" type="password" required />
            <input className="field" value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} placeholder="Confirm new password" type="password" required />
            {notice ? <div style={noticeStyle}>{notice}</div> : null}
            {error ? <div style={errorStyle}>{error}</div> : null}
            <button disabled={isBusy} className="btn-primary" style={primaryStyle}>{isBusy ? "Saving…" : "Reset password"}</button>
            <button type="button" onClick={() => router.push("/login")} style={switchStyle}>Back to login</button>
          </form>
        </div>
      </section>
      <div style={footerWrapStyle}><SiteFooter /></div>
    </main>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={null}>
      <ResetPasswordPageContent />
    </Suspense>
  );
}

const pageStyle: CSSProperties = { minHeight: "100vh", background: "var(--bg)", color: "var(--text)", display: "grid", gridTemplateRows: "1fr auto" };
const authSectionStyle: CSSProperties = { display: "grid", placeItems: "center", padding: "40px 24px" };
const authWrapStyle: CSSProperties = { width: "min(100%, 520px)", display: "grid", gap: 22 };
const titleStyle: CSSProperties = { margin: 0, fontSize: 56, lineHeight: 0.98, letterSpacing: "-.06em", fontWeight: 820 };
const subtitleStyle: CSSProperties = { margin: 0, color: "var(--text-65)", lineHeight: 1.6, fontSize: 18 };
const formStyle: CSSProperties = { display: "grid", gap: 12 };
const noticeStyle: CSSProperties = { color: "var(--green)", fontWeight: 700, textAlign: "center" };
const errorStyle: CSSProperties = { color: "var(--accent)", fontWeight: 700, textAlign: "center" };
const primaryStyle: CSSProperties = { width: "100%", minHeight: 58, fontSize: 20 };
const switchStyle: CSSProperties = { background: "transparent", border: 0, color: "var(--text-65)", fontWeight: 700, justifySelf: "center", padding: 0 };
const footerWrapStyle: CSSProperties = { width: "min(100%, 1280px)", margin: "0 auto", padding: "0 32px 24px" };

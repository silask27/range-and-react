"use client";

import { FormEvent, useState, type CSSProperties } from "react";
import { useRouter } from "next/navigation";
import SiteFooter from "../../components/app/SiteFooter";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export default function ForgotPasswordPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isBusy, setIsBusy] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setIsBusy(true);
    setError(null);
    setNotice(null);
    try {
      const res = await fetch(`${API_BASE}/auth/request-password-reset`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: email.trim().toLowerCase() }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Unable to request a password reset.");
      setNotice(typeof data.message === "string" ? data.message : "If that email exists, we sent a password reset link.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to request a password reset.");
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
            <h1 style={titleStyle}>Reset your password</h1>
            <p style={subtitleStyle}>Enter your email and we’ll send you a reset link if the account exists.</p>
          </div>
          <form onSubmit={handleSubmit} style={formStyle}>
            <input className="field" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="Email" type="email" required />
            {notice ? <div style={noticeStyle}>{notice}</div> : null}
            {error ? <div style={errorStyle}>{error}</div> : null}
            <button disabled={isBusy} className="btn-primary" style={primaryStyle}>{isBusy ? "Sending…" : "Send reset link"}</button>
            <button type="button" onClick={() => router.push("/login")} style={switchStyle}>Back to login</button>
          </form>
        </div>
      </section>
      <div style={footerWrapStyle}><SiteFooter /></div>
    </main>
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

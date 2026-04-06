"use client";

import Link from "next/link";
import { useEffect, useMemo, useState, type CSSProperties } from "react";
import PublicShell from "../../components/app/PublicShell";
import { getStoredAuthToken } from "../../lib/auth";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

type DemoAccount = {
  label: string;
  email: string;
  role: string;
  password?: string;
};

type PublicConfig = {
  app_name: string;
  demo?: {
    enabled?: boolean;
    public_credentials?: boolean;
    organization_name?: string;
    accounts?: DemoAccount[];
    seed_command?: string;
  };
};

export default function DemoPage() {
  const [config, setConfig] = useState<PublicConfig | null>(null);
  const [hasToken, setHasToken] = useState(false);

  useEffect(() => {
    setHasToken(Boolean(getStoredAuthToken()));
    fetch(`${API_BASE}/platform/public-config`, { cache: "no-store" })
      .then((res) => res.json())
      .then((data) => setConfig(data as PublicConfig))
      .catch(() => undefined);
  }, []);

  const demoAccounts = config?.demo?.accounts ?? [];
  const accountMap = useMemo(() => Object.fromEntries(demoAccounts.map((item) => [item.role, item])), [demoAccounts]);

  const steps = [
    {
      role: "owner",
      title: "Show owner/platform value",
      copy: "Log in as the owner to show standalone accounts, admin controls, organization scaffolding, auditability, and the overall pitch story.",
      links: [
        { label: "Open dashboard", href: "/dashboard" },
        { label: "Open admin overview", href: "/admin" },
        { label: "Open account settings", href: "/account" },
      ],
    },
    {
      role: "coach",
      title: "Show coach workflow",
      copy: "Switch to the coach account to walk through assignments, practice targeting, results analytics, and how a coaching business would actually manage reps.",
      links: [
        { label: "Open assignments", href: "/assignments" },
        { label: "Open dashboard", href: "/dashboard" },
        { label: "Open results", href: "/results" },
      ],
    },
    {
      role: "member",
      title: "Show member experience",
      copy: "Finish with the member account: start a quick drill, resume an active hand, open debriefs, and show how weak-spot practice is surfaced automatically.",
      links: [
        { label: "Start training", href: "/screen-1" },
        { label: "Open dashboard", href: "/dashboard" },
        { label: "Open results", href: "/results" },
      ],
    },
  ];

  return (
    <PublicShell
      title="Guided demo walkthrough"
      subtitle="A clean owner → coach → member flow you can use in a pitch meeting, without hardcoding the product to one training site."
    >
      <div style={{ display: "grid", gap: 22 }}>
        <section style={heroStyle}>
          <div>
            <div style={eyebrowStyle}>Pitch flow</div>
            <h2 style={heroTitleStyle}>Use this page as your live demo script</h2>
            <p style={copyStyle}>
              The fastest way to explain the product is to show it from three perspectives: owner, coach, and member. That mirrors how a training company buys, manages, and uses the platform.
            </p>
          </div>
          <div style={ctaRowStyle}>
            <Link href={hasToken ? "/dashboard" : "/login"} style={primaryLinkStyle}>{hasToken ? "Open dashboard" : "Go to login"}</Link>
            <Link href="/" style={secondaryLinkStyle}>Back to home</Link>
          </div>
        </section>

        {config?.demo?.enabled ? (
          <section style={demoPanelStyle}>
            <div>
              <div style={sectionLabelStyle}>Demo environment</div>
              <div style={sectionTitleStyle}>{config.demo.organization_name ?? config.app_name ?? "Demo workspace"}</div>
            </div>
            <div style={helperStyle}>
              {config.demo.public_credentials
                ? "Public demo credentials are enabled in this environment."
                : `Seed demo data locally with: ${config.demo?.seed_command ?? "python -m api.scripts.seed_demo_data --reset"}`}
            </div>
          </section>
        ) : (
          <section style={warningPanelStyle}>
            Demo mode is not enabled. You can still use this walkthrough, but the public demo-account helpers will stay empty until demo seeding is enabled.
          </section>
        )}

        <section style={gridStyle}>
          {steps.map((step, index) => {
            const account = accountMap[step.role];
            return (
              <div key={step.role} style={panelStyle}>
                <div style={sectionLabelStyle}>Step {index + 1}</div>
                <div style={{ fontSize: 24, fontWeight: 800, marginTop: 8 }}>{step.title}</div>
                <p style={{ ...copyStyle, marginTop: 10 }}>{step.copy}</p>
                <div style={{ display: "grid", gap: 8, marginTop: 14 }}>
                  <div style={accountCardStyle}>
                    <div style={{ fontWeight: 800 }}>{account?.label ?? `${step.role} demo`}</div>
                    <div style={metaStyle}>{account?.email ?? "No seeded email available"}</div>
                    {account?.password ? <div style={metaStyle}>Password: {account.password}</div> : null}
                  </div>
                  <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                    <Link href="/login" style={primaryLinkStyle}>Go to login</Link>
                    {step.links.map((link) => (
                      <Link key={link.href} href={link.href} style={secondaryLinkStyle}>{link.label}</Link>
                    ))}
                  </div>
                </div>
              </div>
            );
          })}
        </section>

        <section style={panelStyle}>
          <div style={sectionLabelStyle}>What to say in the pitch</div>
          <div style={sectionTitleStyle}>Simple story, fast clicks</div>
          <div style={bulletGridStyle}>
            {[
              "Owner: this is the practice layer that turns coaching philosophy into measurable reps.",
              "Coach: assign exact spot types, then use results to see who is missing which thought-process steps.",
              "Member: complete fast drills, review debriefs, and practice weak spots without needing a full live session.",
              "Integration: works standalone today, with external member-link scaffolding ready for future sync/import flows.",
            ].map((item) => (
              <div key={item} style={bulletCardStyle}>{item}</div>
            ))}
          </div>
        </section>
      </div>
    </PublicShell>
  );
}

const gridStyle: CSSProperties = { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 18 };
const heroStyle: CSSProperties = { display: "flex", justifyContent: "space-between", gap: 18, alignItems: "flex-start", flexWrap: "wrap", padding: 22, borderRadius: 20, border: "1px solid rgba(240,235,224,0.08)", background: "var(--surface-fill)" };
const ctaRowStyle: CSSProperties = { display: "flex", gap: 12, flexWrap: "wrap" };
const heroTitleStyle: CSSProperties = { margin: "8px 0 0", fontSize: 34, lineHeight: 1.08, letterSpacing: "-0.03em" };
const eyebrowStyle: CSSProperties = { color: "#E76F51", fontSize: 12, fontWeight: 800, textTransform: "uppercase", letterSpacing: 1.3 };
const copyStyle: CSSProperties = { color: "rgba(240,235,224,0.45)", lineHeight: 1.7, margin: "10px 0 0" };
const panelStyle: CSSProperties = { background: "var(--surface-fill)", border: "1px solid rgba(240,235,224,0.08)", borderRadius: 20, padding: 22 };
const demoPanelStyle: CSSProperties = { display: "flex", justifyContent: "space-between", gap: 18, alignItems: "center", flexWrap: "wrap", padding: 20, borderRadius: 18, border: "1px solid rgba(231,111,81,0.24)", background: "rgba(231,111,81,0.08)" };
const warningPanelStyle: CSSProperties = { padding: 18, borderRadius: 18, border: "1px solid rgba(231,111,81,0.4)", background: "rgba(231,111,81,0.1)", color: "var(--text)" };
const sectionLabelStyle: CSSProperties = { color: "rgba(240,235,224,0.45)", fontSize: 12, textTransform: "uppercase", letterSpacing: 1.2 };
const sectionTitleStyle: CSSProperties = { marginTop: 8, fontSize: 24, fontWeight: 800 };
const helperStyle: CSSProperties = { color: "rgba(240,235,224,0.65)", fontSize: 14, lineHeight: 1.6 };
const metaStyle: CSSProperties = { color: "rgba(240,235,224,0.45)", fontSize: 13, marginTop: 4 };
const accountCardStyle: CSSProperties = { padding: 14, borderRadius: 14, background: "var(--surface-fill)", border: "1px solid rgba(240,235,224,0.06)" };
const primaryLinkStyle: CSSProperties = { padding: "12px 16px", borderRadius: 12, border: "1px solid var(--accent)", background: "var(--accent)", color: "var(--text)", textDecoration: "none", fontWeight: 800 };
const secondaryLinkStyle: CSSProperties = { padding: "12px 16px", borderRadius: 12, border: "1px solid var(--line)", color: "var(--text)", textDecoration: "none", fontWeight: 700 };
const bulletGridStyle: CSSProperties = { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 12, marginTop: 14 };
const bulletCardStyle: CSSProperties = { padding: 16, borderRadius: 16, background: "var(--surface-fill)", border: "1px solid rgba(240,235,224,0.06)", color: "rgba(240,235,224,0.65)", lineHeight: 1.6 };

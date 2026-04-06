"use client";

import { useEffect, useState } from "react";
import PublicShell from "../../components/app/PublicShell";
import { API_BASE } from "../../lib/api";
import type { PublicConfig } from "../../lib/publicConfig";

type StatusPayload = {
  status: string;
  service: string;
  environment: string;
  database?: string;
  sentry?: string;
  version?: string;
  error_count?: number;
  warning_count?: number;
  detail_visibility?: "summary" | "full";
  checks?: Array<{ name: string; status: string; detail: string; required: boolean }>;
};

export default function StatusPage() {
  const [status, setStatus] = useState<StatusPayload | null>(null);
  const [config, setConfig] = useState<PublicConfig | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const [statusRes, configRes] = await Promise.all([
          fetch(`${API_BASE}/readyz`, { cache: "no-store" }),
          fetch(`${API_BASE}/platform/public-config`, { cache: "no-store" }),
        ]);
        const statusData = await statusRes.json();
        const configData = await configRes.json();
        if (!cancelled) {
          setStatus(statusData as StatusPayload);
          setConfig(configData as PublicConfig);
        }
      } catch {
        if (!cancelled) setError("Unable to reach the backend status endpoints.");
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  const demo = config?.demo;
  const showDemoDetails = Boolean(config?.ops?.public_status_show_demo_details);
  const showCheckDetails = status?.detail_visibility === "full" && Boolean(status?.checks?.length);

  return (
    <PublicShell title="Platform status" subtitle="Operational readiness for staging, launches, and coach-facing demos.">
      {error ? <div style={panelStyle}>{error}</div> : null}
      <div style={{ display: "grid", gap: 16 }}>
        <div style={gridStyle}>
          <div style={panelStyle}>
            <div style={labelStyle}>Service</div>
            <div style={valueStyle}>{status?.service ?? config?.app_name ?? "Live Range Lab"}</div>
            <div style={metaStyle}>Environment: {status?.environment ?? config?.environment ?? "unknown"} · Version: {status?.version ?? config?.version ?? "unknown"}</div>
          </div>
          <div style={panelStyle}>
            <div style={labelStyle}>Readiness</div>
            <div style={valueStyle}>{status?.status ?? "checking"}</div>
            <div style={metaStyle}>Database: {status?.database ?? "unknown"} · Sentry: {status?.sentry ?? "unknown"} · Required errors: {status?.error_count ?? 0} · Warnings: {status?.warning_count ?? 0}</div>
          </div>
          <div style={panelStyle}>
            <div style={labelStyle}>Support</div>
            <div style={valueStyle}>{config?.support_email ?? "support@example.com"}</div>
            <div style={metaStyle}>This address should be monitored before launch.</div>
          </div>
        </div>

        {showCheckDetails ? (
          <div style={panelStyle}>
            <div style={labelStyle}>Runtime checks</div>
            <div style={{ display: "grid", gap: 10, marginTop: 12 }}>
              {status?.checks?.map((check) => (
                <div key={check.name} style={{ border: "1px solid rgba(240,235,224,0.08)", borderRadius: 14, padding: 12, background: "rgba(240,235,224,0.02)" }}>
                  <div style={{ fontWeight: 700, textTransform: "capitalize" }}>{check.name.replaceAll("_", " ")} · {check.status}</div>
                  <div style={{ marginTop: 4, color: "rgba(240,235,224,0.65)" }}>{check.detail}</div>
                  <div style={{ marginTop: 4, color: "rgba(240,235,224,0.45)", fontSize: 12 }}>{check.required ? "Required" : "Optional"}</div>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div style={panelStyle}>
            <div style={labelStyle}>Runtime checks</div>
            <div style={metaStyle}>
              Detailed runtime checks are hidden on this public status page. Use the authenticated admin runtime-check endpoint for the full operational checklist.
            </div>
          </div>
        )}

        <div style={panelStyle}>
          <div style={labelStyle}>Demo mode</div>
          <div style={valueStyle}>{demo?.enabled ? "enabled" : "disabled"}</div>
          <div style={metaStyle}>
            {demo?.enabled
              ? `${demo.organization_name ?? "Demo workspace"}${showDemoDetails ? ` · ${demo.accounts?.length ?? 0} seeded demo accounts` : " · public demo details hidden"}`
              : "Demo mode is off. Enable it only for local demos, sales previews, or white-label staging."}
          </div>
          {demo?.enabled && showDemoDetails && demo?.seed_command ? (
            <div style={{ marginTop: 14, color: "rgba(240,235,224,0.65)", lineHeight: 1.6 }}>
              Seed command: <code>{demo.seed_command}</code>
            </div>
          ) : null}
        </div>
      </div>
    </PublicShell>
  );
}

const gridStyle = { display: "grid", gap: 16, gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))" } as const;
const panelStyle = { background: "rgba(240,235,224,0.03)", border: "1px solid rgba(240,235,224,0.08)", borderRadius: 18, padding: 18 };
const labelStyle = { color: "rgba(240,235,224,0.45)", fontSize: 12, textTransform: "uppercase", letterSpacing: 1.2 } as const;
const valueStyle = { marginTop: 8, fontSize: 28, fontWeight: 800 } as const;
const metaStyle = { marginTop: 8, color: "rgba(240,235,224,0.65)" } as const;

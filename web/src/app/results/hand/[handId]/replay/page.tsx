"use client";

import { useEffect, useMemo, useState, type CSSProperties } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import AppShell from "../../../../../components/app/AppShell";
import { API_BASE, apiFetch } from "../../../../../lib/api";
import { useRequireAuth } from "../../../../../lib/hooks/useRequireAuth";

type ReplayStep = {
  kind: string;
  street: string;
  title: string;
  summary: string;
  board: string[];
  details: Record<string, unknown> | null;
};

type ReplayPayload = {
  hand_id: string;
  session_id: string;
  scenario_display_name: string | null;
  villain_display_name: string | null;
  hero_hand: string[];
  villain_hand: string[];
  final_board: string[];
  review: {
    flagged: boolean;
    sent_to_coaches: boolean;
    status: string;
  };
  steps: ReplayStep[];
};

const PALETTE = {
  cream: "#F0EBE0",
  coral: "#E76F51",
  green: "#6A9E72",
  muted: "rgba(240,235,224,0.65)",
  soft: "rgba(240,235,224,0.45)",
};

export default function HandReplayPage() {
  const params = useParams<{ handId: string }>();
  const handId = Array.isArray(params?.handId) ? params.handId[0] : params?.handId;
  const { user, isAuthLoading, authError } = useRequireAuth();
  const [payload, setPayload] = useState<ReplayPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [stepIndex, setStepIndex] = useState(0);

  useEffect(() => {
    if (!user || !handId) return;
    let cancelled = false;
    async function load() {
      try {
        const res = await apiFetch(`${API_BASE}/results/hand/${encodeURIComponent(handId)}/replay`, { cache: "no-store" });
        const data = await res.json();
        if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Unable to load hand replay.");
        if (!cancelled) setPayload(data as ReplayPayload);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Unable to load hand replay.");
      }
    }
    void load();
    return () => { cancelled = true; };
  }, [user, handId]);

  const currentStep = payload?.steps[stepIndex] ?? null;
  const detailRows = useMemo(() => buildDetailRows(currentStep), [currentStep]);
  const totalSteps = payload?.steps.length ?? 0;

  return (
    <AppShell
      title="Hand replay"
      subtitle="Step through the saved hand exactly as it was recorded. Replay is read-only."
    >
      {isAuthLoading ? <div style={emptyStyle}>Loading hand replay…</div> : null}
      {authError ? <div style={errorStyle}>{authError}</div> : null}
      {error ? <div style={errorStyle}>{error}</div> : null}
      {payload ? (
        <div style={pageStackStyle}>
          <section style={summaryGridStyle}>
            <InfoTile label="Scenario" value={payload.scenario_display_name || "Scenario"} />
            <InfoTile label="Villain" value={payload.villain_display_name || "Villain"} />
            <InfoTile label="Hero hand" value={payload.hero_hand.join(" ")} />
            <InfoTile label="Villain hand" value={payload.villain_hand.join(" ")} />
          </section>

          <section style={panelStyle}>
            <div style={replayHeaderStyle}>
              <button
                type="button"
                aria-label="Previous replay step"
                onClick={() => setStepIndex((value) => Math.max(0, value - 1))}
                disabled={stepIndex <= 0}
                style={arrowButtonStyle}
              >
                ‹
              </button>
              <div style={{ minWidth: 0 }}>
                <div style={eyebrowStyle}>Step {stepIndex + 1} of {totalSteps}</div>
                <h2 style={stepTitleStyle}>{currentStep?.title ?? "Replay step"}</h2>
                <div style={stepSummaryStyle}>{currentStep?.summary}</div>
              </div>
              <button
                type="button"
                aria-label="Next replay step"
                onClick={() => setStepIndex((value) => Math.min(totalSteps - 1, value + 1))}
                disabled={stepIndex >= totalSteps - 1}
                style={arrowButtonStyle}
              >
                ›
              </button>
            </div>

            <div style={boardRowStyle}>
              {(currentStep?.board?.length ? currentStep.board : payload.final_board).map((card) => (
                <span key={`${currentStep?.kind}-${card}`} style={cardStyle}>{card}</span>
              ))}
            </div>

            <div style={stepRailStyle}>
              {payload.steps.map((step, index) => (
                <button
                  key={`${step.kind}-${step.street}-${index}`}
                  type="button"
                  aria-label={`Go to step ${index + 1}`}
                  onClick={() => setStepIndex(index)}
                  style={{ ...railDotStyle, ...(index === stepIndex ? activeRailDotStyle : null) }}
                />
              ))}
            </div>

            {detailRows.length ? (
              <div style={detailListStyle}>
                {detailRows.map((row) => (
                  <div key={row.label} style={detailRowStyle}>
                    <span style={detailLabelStyle}>{row.label}</span>
                    <span style={detailValueStyle}>{row.value}</span>
                  </div>
                ))}
              </div>
            ) : <div style={emptyStyle}>No additional details were stored for this step.</div>}
          </section>

          <div style={footerActionsStyle}>
            <Link href={`/results/hand/${encodeURIComponent(payload.hand_id)}`} style={secondaryLinkStyle}>Debrief</Link>
            <Link href="/results" style={secondaryLinkStyle}>Results</Link>
          </div>
        </div>
      ) : null}
    </AppShell>
  );
}

function buildDetailRows(step: ReplayStep | null) {
  if (!step?.details) return [];
  const details = step.details;
  if (step.kind === "preflop_range") {
    const tokens = Array.isArray(details.range_tokens) ? details.range_tokens.map(String) : [];
    return [
      { label: "Saved labels", value: tokens.length ? tokens.join(", ") : "None recorded" },
    ];
  }
  if (step.kind === "action") {
    const event = isRecord(details.event) ? details.event : {};
    return [
      { label: "Street", value: String(event.street ?? step.street) },
      { label: "Actor", value: String(event.actor ?? "Unknown") },
      { label: "Action", value: formatActionValue(String(event.action ?? "")) },
      { label: "Amount", value: Number(event.amount ?? 0) > 0 ? `${Number(event.amount).toFixed(1)}bb` : "None" },
    ];
  }
  if (step.kind === "response_matrix") {
    return [
      { label: "Bucket", value: `${String(details.actual_bucket ?? "Bucket")} · ${String(details.actual_subgroup ?? "Subgroup")}` },
      { label: "Hero action", value: formatActionValue(String(details.hero_action ?? "")) },
      { label: "Selected", value: String(details.predicted ?? "None") },
      { label: "Actual", value: String(details.actual ?? "Unscored") },
      { label: "Score", value: details.score == null ? "Unscored" : `${Number(details.score).toFixed(0)}` },
    ];
  }
  if (step.kind === "range_prune") {
    return [
      { label: "Actual bucket", value: `${String(details.actual_bucket ?? "Bucket")} · ${String(details.actual_subgroup ?? "Subgroup")}` },
      { label: "Live combos", value: `${String(details.start_live_combos ?? "—")} → ${String(details.end_live_combos ?? "—")}` },
      { label: "Exact combo kept", value: details.combo_alive ? "Yes" : "No" },
      { label: "Bucket kept", value: details.bucket_alive ? "Yes" : "No" },
      { label: "Score", value: details.overall_score == null ? "Unscored" : `${Number(details.overall_score).toFixed(0)}` },
    ];
  }
  return Object.entries(details)
    .filter(([, value]) => typeof value === "string" || typeof value === "number" || typeof value === "boolean")
    .slice(0, 8)
    .map(([label, value]) => ({ label: humanize(label), value: String(value) }));
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function humanize(value: string) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatActionValue(value: string) {
  if (!value) return "Action";
  return humanize(value);
}

function InfoTile({ label, value }: { label: string; value: string }) {
  return (
    <div style={infoTileStyle}>
      <div style={tileLabelStyle}>{label}</div>
      <div style={tileValueStyle}>{value}</div>
    </div>
  );
}

const pageStackStyle: CSSProperties = { display: "grid", gap: 28 };
const summaryGridStyle: CSSProperties = { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 180px), 1fr))", gap: 14 };
const panelStyle: CSSProperties = { borderTop: "1px solid var(--line-soft)", paddingTop: 18 };
const replayHeaderStyle: CSSProperties = { display: "grid", gridTemplateColumns: "48px minmax(0, 1fr) 48px", gap: 16, alignItems: "center" };
const arrowButtonStyle: CSSProperties = { width: 48, height: 48, borderRadius: 16, border: "1px solid var(--line)", background: "var(--surface-fill-strong)", color: PALETTE.cream, fontSize: 34, lineHeight: 1, fontWeight: 900 };
const eyebrowStyle: CSSProperties = { color: PALETTE.coral, fontSize: 12, textTransform: "uppercase", letterSpacing: 1.3, fontWeight: 900 };
const stepTitleStyle: CSSProperties = { margin: "6px 0 0", fontSize: 32, lineHeight: 1.05, color: PALETTE.cream };
const stepSummaryStyle: CSSProperties = { marginTop: 8, color: PALETTE.muted, lineHeight: 1.55 };
const boardRowStyle: CSSProperties = { display: "flex", gap: 10, flexWrap: "wrap", marginTop: 22 };
const cardStyle: CSSProperties = { width: 58, height: 74, borderRadius: 12, background: PALETTE.cream, color: "#141210", display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: 21, fontWeight: 900, border: "1px solid rgba(20,18,16,0.12)" };
const stepRailStyle: CSSProperties = { display: "flex", gap: 8, flexWrap: "wrap", marginTop: 24 };
const railDotStyle: CSSProperties = { width: 28, height: 8, borderRadius: 999, border: "0", background: "rgba(240,235,224,0.22)" };
const activeRailDotStyle: CSSProperties = { background: PALETTE.coral };
const detailListStyle: CSSProperties = { display: "grid", gap: 0, marginTop: 24, borderTop: "1px solid var(--line-soft)" };
const detailRowStyle: CSSProperties = { display: "grid", gridTemplateColumns: "minmax(120px, 180px) minmax(0, 1fr)", gap: 16, padding: "13px 0", borderBottom: "1px solid var(--line-soft)" };
const detailLabelStyle: CSSProperties = { color: PALETTE.soft, fontSize: 12, textTransform: "uppercase", letterSpacing: 1.05, fontWeight: 900 };
const detailValueStyle: CSSProperties = { color: PALETTE.cream, fontSize: 14, lineHeight: 1.45, overflowWrap: "anywhere" };
const infoTileStyle: CSSProperties = { padding: 16, borderRadius: 18, border: "1px solid var(--line)", background: "var(--surface-fill-strong)" };
const tileLabelStyle: CSSProperties = { color: PALETTE.soft, fontSize: 11, textTransform: "uppercase", letterSpacing: 1.05, fontWeight: 900 };
const tileValueStyle: CSSProperties = { marginTop: 8, color: PALETTE.cream, fontSize: 17, fontWeight: 850, lineHeight: 1.25 };
const footerActionsStyle: CSSProperties = { display: "flex", gap: 10, flexWrap: "wrap" };
const secondaryLinkStyle: CSSProperties = { padding: "10px 14px", borderRadius: 999, border: "1px solid var(--line)", background: "var(--surface-fill-strong)", color: PALETTE.cream, textDecoration: "none", fontWeight: 800, fontSize: 14, whiteSpace: "nowrap" };
const errorStyle: CSSProperties = { color: "var(--accent)", fontWeight: 700 };
const emptyStyle: CSSProperties = { color: PALETTE.soft, fontSize: 14, lineHeight: 1.6 };

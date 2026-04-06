"use client";

import { useEffect, useState, type CSSProperties } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import AppShell from "../../../../components/app/AppShell";
import { API_BASE, apiFetch } from "../../../../lib/api";
import { useRequireAuth } from "../../../../lib/hooks/useRequireAuth";

type DebriefPayload = {
  hand_id: string;
  session_id: string;
  scenario_id: string | null;
  villain_profile_id: string | null;
  street: string;
  hero_hand: string[];
  villain_hand: string[];
  board: string[];
  summary: {
    prune_steps_scored?: number;
    response_nodes_scored?: number;
    ranging_score?: number | null;
    response_score?: number | null;
    overall_score?: number | null;
  };
  actual_final_bucket: {
    bucket_label: string;
    subgroup_label: string;
    equity_vs_hero: number;
    hero_range_source: string;
  };
  prune_evaluations: Array<{
    street: string;
    villain_action: string | null;
    actual_bucket: string;
    actual_subgroup: string;
    start_live_combos: number;
    end_live_combos: number;
    combo_alive: boolean;
    bucket_alive: boolean;
    subgroup_alive: boolean;
    efficiency_score: number;
    overall_score: number;
  }>;
  response_evaluations: Array<{
    street: string;
    actual_bucket: string;
    actual_subgroup: string;
    hero_action: string;
    column: string | null;
    predicted: string | null;
    actual: string | null;
    villain_action: string | null;
    supported: boolean;
    score: number | null;
    correct: boolean | null;
    reason: string | null;
  }>;
  recommendations: string[];
  history: Array<{
    street: string;
    actor: string;
    action: string;
    amount: number | null;
    note: string;
    forced: boolean;
  }>;
};

export default function HandDebriefPage() {
  const params = useParams<{ handId: string }>();
  const handId = Array.isArray(params?.handId) ? params.handId[0] : params?.handId;
  const { user, isAuthLoading, authError } = useRequireAuth();
  const [payload, setPayload] = useState<DebriefPayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!user || !handId) return;
    let cancelled = false;
    async function load() {
      try {
        const res = await apiFetch(`${API_BASE}/results/hand/${encodeURIComponent(handId)}`, { cache: "no-store" });
        const data = await res.json();
        if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Unable to load hand debrief.");
        if (!cancelled) setPayload(data as DebriefPayload);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Unable to load hand debrief.");
      }
    }
    void load();
    return () => { cancelled = true; };
  }, [user, handId]);

  return (
    <AppShell title="Hand debrief" subtitle="Review what the true hand was, whether you kept it alive, and how your response predictions matched what actually happened.">
      {isAuthLoading ? <div style={emptyStyle}>Loading hand debrief…</div> : null}
      {authError ? <div style={errorStyle}>{authError}</div> : null}
      {error ? <div style={errorStyle}>{error}</div> : null}
      {payload ? (
        <>
          <section className="open-grid-four">
            <MetricCard label="Avg ranging" value={payload.summary.ranging_score ?? "—"} />
            <MetricCard label="Avg response" value={payload.summary.response_score ?? "—"} />
            <MetricCard label="Overall" value={payload.summary.overall_score ?? "—"} />
            <MetricCard label="Prune steps" value={payload.summary.prune_steps_scored ?? 0} />
            <MetricCard label="Response nodes" value={payload.summary.response_nodes_scored ?? 0} />
          </section>

          <section className="open-grid-two">
            <div style={{ display: "grid", gap: 18 }}>
              <div style={panelStyle}>
                <div style={panelLabelStyle}>Reveal</div>
                <div style={panelTitleStyle}>Final truth</div>
                <div style={{ display: "grid", gap: 10, marginTop: 12 }}>
                  <InfoRow label="Hero hand" value={payload.hero_hand.join(" ")} />
                  <InfoRow label="Villain hand" value={payload.villain_hand.join(" ")} />
                  <InfoRow label="Board" value={payload.board.join(" ")} />
                  <InfoRow label="Final bucket" value={`${payload.actual_final_bucket.bucket_label} · ${payload.actual_final_bucket.subgroup_label}`} />
                  <InfoRow label="Equity vs hero" value={payload.actual_final_bucket.equity_vs_hero.toFixed(3)} />
                </div>
              </div>

              <div style={panelStyle}>
                <div style={panelLabelStyle}>Prune evaluation</div>
                <div style={panelTitleStyle}>Did you keep the real hand alive?</div>
                <div style={listStyle}>
                  {payload.prune_evaluations.length ? payload.prune_evaluations.map((item, index) => (
                    <div key={`${item.street}-${index}`} style={listRowStyle}>
                      <div>
                        <div style={rowTitleStyle}>{item.street.toUpperCase()} · {item.villain_action ?? "villain action"}</div>
                        <div style={rowMetaStyle}>Bucket {item.actual_bucket} · Subgroup {item.actual_subgroup}</div>
                        <div style={rowMetaStyle}>Combos {item.start_live_combos} → {item.end_live_combos}</div>
                      </div>
                      <div style={{ textAlign: "right" }}>
                        <div style={{ ...tagStyle, ...(item.combo_alive ? successTagStyle : dangerTagStyle) }}>{item.combo_alive ? "kept alive" : "removed"}</div>
                        <div style={{ marginTop: 8, color: "rgba(240,235,224,0.65)", fontSize: 13 }}>Score {item.overall_score}</div>
                      </div>
                    </div>
                  )) : <div style={emptyStyle}>No prune evaluations were recorded for this hand.</div>}
                </div>
              </div>
            </div>

            <div style={{ display: "grid", gap: 18 }}>
              <div style={panelStyle}>
                <div style={panelLabelStyle}>Response matrix</div>
                <div style={panelTitleStyle}>Prediction vs actual</div>
                <div style={listStyle}>
                  {payload.response_evaluations.length ? payload.response_evaluations.map((item, index) => (
                    <div key={`${item.street}-${index}`} style={listRowStyle}>
                      <div>
                        <div style={rowTitleStyle}>{item.street.toUpperCase()} · {item.hero_action}</div>
                        <div style={rowMetaStyle}>Predicted {item.predicted ?? "—"} · Actual {item.actual ?? "—"}</div>
                        <div style={rowMetaStyle}>{item.reason ?? `${item.actual_bucket} / ${item.actual_subgroup}`}</div>
                      </div>
                      <div style={{ textAlign: "right" }}>
                        <div style={{ ...tagStyle, ...(item.supported ? item.correct ? successTagStyle : dangerTagStyle : neutralTagStyle) }}>
                          {item.supported ? item.correct ? "correct" : "miss" : "unscored"}
                        </div>
                        <div style={{ marginTop: 8, color: "rgba(240,235,224,0.65)", fontSize: 13 }}>Score {item.score ?? "—"}</div>
                      </div>
                    </div>
                  )) : <div style={emptyStyle}>No response evaluations were recorded for this hand.</div>}
                </div>
              </div>

              <div style={panelStyle}>
                <div style={panelLabelStyle}>Recommendations</div>
                <div style={panelTitleStyle}>Coaching takeaways</div>
                <ul style={{ margin: "14px 0 0", paddingLeft: 18, color: "rgba(240,235,224,0.65)", lineHeight: 1.7 }}>
                  {payload.recommendations.map((item) => <li key={item}>{item}</li>)}
                </ul>
              </div>
            </div>
          </section>

          <section style={panelStyle}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 14, alignItems: "center" }}>
              <div>
                <div style={panelLabelStyle}>Action history</div>
                <div style={panelTitleStyle}>Street-by-street sequence</div>
              </div>
              <Link href={`/screen-3?session_id=${encodeURIComponent(payload.session_id)}&hand_id=${encodeURIComponent(payload.hand_id)}`} style={secondaryLinkStyle}>Open hand replay</Link>
            </div>
            <div style={listStyle}>
              {payload.history.map((event, index) => (
                <div key={`${event.street}-${event.actor}-${index}`} style={listRowStyle}>
                  <div>
                    <div style={rowTitleStyle}>{event.street.toUpperCase()} · {event.actor} {event.action}{event.amount ? ` ${event.amount}` : ""}</div>
                    <div style={rowMetaStyle}>{event.note || (event.forced ? "Forced action" : "Action event")}</div>
                  </div>
                </div>
              ))}
            </div>
          </section>
        </>
      ) : null}
    </AppShell>
  );
}

function MetricCard({ label, value }: { label: string; value: string | number }) {
  return <div style={panelStyle}><div style={panelLabelStyle}>{label}</div><div style={{ fontSize: 30, fontWeight: 800, marginTop: 8 }}>{value}</div></div>;
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return <div style={{ display: "flex", justifyContent: "space-between", gap: 12, borderBottom: "1px solid rgba(240,235,224,0.06)", paddingBottom: 8 }}><div style={rowMetaStyle}>{label}</div><div style={{ fontWeight: 700 }}>{value}</div></div>;
}

const panelStyle: CSSProperties = { borderTop: "1px solid var(--line-soft)", paddingTop: 18 };
const errorStyle: CSSProperties = { color: "var(--accent)", fontWeight: 700 };
const panelLabelStyle: CSSProperties = { color: "rgba(240,235,224,0.45)", fontSize: 12, textTransform: "uppercase", letterSpacing: 1.2 };
const panelTitleStyle: CSSProperties = { marginTop: 8, fontSize: 22, fontWeight: 800 };
const listStyle: CSSProperties = { display: "grid", gap: 12, marginTop: 14 };
const listRowStyle: CSSProperties = { display: "flex", justifyContent: "space-between", alignItems: "center", gap: 14, paddingTop: 12, borderTop: "1px solid var(--line-soft)" };
const rowTitleStyle: CSSProperties = { fontWeight: 800, fontSize: 15 };
const rowMetaStyle: CSSProperties = { color: "rgba(240,235,224,0.45)", fontSize: 13, marginTop: 3 };
const emptyStyle: CSSProperties = { color: "rgba(240,235,224,0.45)", fontSize: 14 };
const tagStyle: CSSProperties = { padding: "6px 10px", borderRadius: 999, fontSize: 12, fontWeight: 800, textTransform: "uppercase" };
const successTagStyle: CSSProperties = { background: "var(--success)", border: "1px solid var(--success)", color: "var(--bg)" };
const dangerTagStyle: CSSProperties = { background: "var(--accent)", border: "1px solid var(--accent)", color: "var(--text)" };
const neutralTagStyle: CSSProperties = { background: "rgba(240,235,224,0.07)", border: "1px solid rgba(240,235,224,0.12)", color: "var(--text)" };
const secondaryLinkStyle: CSSProperties = { padding: "10px 16px", borderRadius: 999, border: "1px solid var(--line)", background: "transparent", color: "var(--text)", textDecoration: "none", fontWeight: 700, fontSize: 14 };

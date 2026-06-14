"use client";

import { useEffect, useState, type CSSProperties, type ReactNode } from "react";
import Link from "next/link";
import AppShell from "../../components/app/AppShell";
import TrendChart from "../../components/app/TrendChart";
import { apiFetch, API_BASE } from "../../lib/api";
import { useRequireAuth } from "../../lib/hooks/useRequireAuth";

type DashboardAssignment = {
  assignment_id: string;
  title: string;
  scenario_display_name?: string | null;
  villain_display_name?: string | null;
  progress: { progress_count: number; repetition_target: number; is_overdue: boolean };
};
type SuggestedPractice = { title: string; description: string; reason: string; quick_start_url: string };
type DashboardResult = { hand_id: string; scenario_display_name?: string | null; villain_display_name?: string | null; ranging_score: number | null; response_score: number | null; completed_at: string | null };
type OverviewPayload = {
  summary: { completed_hands: number; avg_ranging_score: number | null; avg_response_score: number | null; assignments_active: number };
  assignments: DashboardAssignment[];
  suggested_practice: SuggestedPractice[];
  recent_results: DashboardResult[];
  trend_points: Array<{ label: string; ranging_score: number | null; response_score: number | null }>;
};

export default function DashboardPage() {
  const { user, isAuthLoading, authError } = useRequireAuth();
  const [overview, setOverview] = useState<OverviewPayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;
    let cancelled = false;
    async function loadOverview() {
      try {
        const res = await apiFetch(`${API_BASE}/dashboard/overview`, { cache: "no-store" });
        const data = await res.json();
        if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Unable to load home.");
        if (!cancelled) setOverview(data as OverviewPayload);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Unable to load home.");
      }
    }
    void loadOverview();
    return () => { cancelled = true; };
  }, [user]);

  const latest = overview?.recent_results?.[0] ?? null;
  const suggestion = overview?.suggested_practice?.[0] ?? null;
  const topAssignment = overview?.assignments?.[0] ?? null;
  const isCoach = user?.role === "owner" || user?.role === "admin" || user?.role === "coach";
  const cleanedSuggestionReason = cleanTrainCopy(suggestion?.reason);

  return (
    <AppShell title={`Welcome back, ${user?.display_name || "player"}`} subtitle="One place to start training, review results, and check what matters right now.">
      {isAuthLoading ? <div style={copyStyle}>Loading home…</div> : null}
      {authError ? <div style={errorStyle}>{authError}</div> : null}
      {error ? <div style={errorStyle}>{error}</div> : null}
      {overview ? (
        <div style={{ display: "grid", gap: 28 }}>
          <section className="open-grid-four">
            <HomeLinkCard href="/account" icon={<PersonIcon />} title="Account" copy={`Signed in as ${user?.display_name || user?.email || "your account"}. Update profile, password, and access settings.`} extra={<span className="badge badge-primary">{user?.role}</span>} />
            <HomeLinkCard href={suggestion?.quick_start_url || "/screen-1"} icon={<TableIcon />} title="Train" copy={cleanedSuggestionReason || "Open the trainer and run the next live rep."} extra={suggestion ? <span className="badge badge-primary">Start next rep</span> : null} />
            <HomeLinkCard href="/results" icon={<ChartIcon />} title="Results" copy={latest ? `Latest finished hand: ${latest.scenario_display_name || "Scenario"} vs ${latest.villain_display_name || "Villain"}.` : "Finished hands, score trends, and debriefs live here."} extra={<div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}><span className="badge badge-success">Range Score {formatScore(overview.summary.avg_ranging_score)}</span><span className="badge badge-primary">Action Score {formatScore(overview.summary.avg_response_score)}</span></div>} />
            {isCoach ? (
              <HomeLinkCard href="/admin" icon={<CoachIcon />} title="Coach" copy={topAssignment ? `Active assignment: ${topAssignment.title}. Review pool analytics and assign the next reps.` : "Pool analytics, member oversight, and assignments all in one place."} extra={<span className="badge badge-primary">{overview.summary.completed_hands} finished hands</span>} />
            ) : (
              <HomeLinkCard href="/assignments" icon={<ClipboardIcon />} title="Assignments" copy={topAssignment ? `${topAssignment.title} · ${topAssignment.progress.progress_count}/${topAssignment.progress.repetition_target} reps complete.` : "Coach work and guided practice appear here."} extra={<span className="badge badge-muted">{overview.summary.assignments_active} active</span>} />
            )}
          </section>

          <section style={growthGridStyle}>
            <div style={growthPanelStyle}>
              <div style={eyebrowStyle}>Member growth</div>
              <h2 style={sectionTitleStyle}>Your recent score trend</h2>
              {overview.trend_points.length ? <TrendChart points={overview.trend_points.map((point) => ({ label: point.label, ranging: point.ranging_score, response: point.response_score }))} /> : <div style={copyStyle}>Finish a few reps to unlock your range and action trendline.</div>}
            </div>
            <div style={growthPanelStyle}>
              <div style={eyebrowStyle}>Next work</div>
              <h2 style={sectionTitleStyle}>Recommended drill</h2>
              {suggestion ? (
                <div style={stackStyle}>
                  <div>
                    <div style={smallTitleStyle}>{suggestion.title}</div>
                    <div style={copyStyle}>{suggestion.description}</div>
                    <div style={metaStyle}>{cleanedSuggestionReason || suggestion.reason}</div>
                  </div>
                  <Link href={suggestion.quick_start_url || "/screen-1"} style={buttonLinkStyle}>Start drill</Link>
                </div>
              ) : <div style={copyStyle}>No recommendation yet. Complete more reps to build your profile.</div>}
            </div>
            <div style={growthPanelStyle}>
              <div style={eyebrowStyle}>Assigned work</div>
              <h2 style={sectionTitleStyle}>Coach queue</h2>
              <div style={stackStyle}>
                {overview.assignments.length ? overview.assignments.slice(0, 4).map((assignment) => (
                  <div key={assignment.assignment_id} style={miniRowStyle}>
                    <div>
                      <div style={smallTitleStyle}>{assignment.title}</div>
                      <div style={metaStyle}>{assignment.scenario_display_name || "Any scenario"} · {assignment.villain_display_name || "Any villain"}</div>
                    </div>
                    <div style={miniMetricStyle}>{assignment.progress.progress_count}/{assignment.progress.repetition_target}</div>
                  </div>
                )) : <div style={copyStyle}>No active coach assignments.</div>}
              </div>
            </div>
            <div style={growthPanelStyle}>
              <div style={eyebrowStyle}>Recent reps</div>
              <h2 style={sectionTitleStyle}>Latest finished hands</h2>
              <div style={stackStyle}>
                {overview.recent_results.length ? overview.recent_results.slice(0, 4).map((result) => (
                  <div key={result.hand_id} style={miniRowStyle}>
                    <div>
                      <div style={smallTitleStyle}>{result.scenario_display_name || "Scenario"} vs {result.villain_display_name || "Villain"}</div>
                      <div style={metaStyle}>{result.completed_at ? new Date(result.completed_at).toLocaleDateString() : "Finished rep"}</div>
                    </div>
                    <div style={miniMetricStyle}>R {formatScore(result.ranging_score)} · A {formatScore(result.response_score)}</div>
                  </div>
                )) : <div style={copyStyle}>Finished hands will appear here.</div>}
              </div>
            </div>
          </section>
        </div>
      ) : null}
    </AppShell>
  );
}


function cleanTrainCopy(copy?: string | null) {
  if (!copy) return "";
  return copy
    .replace(/Average overall score:\s*\d+(?:\.\d+)?/gi, "")
    .replace(/\s{2,}/g, " ")
    .replace(/\s+([.,;:!?])/g, "$1")
    .trim();
}

function HomeLinkCard({ href, icon, title, copy, extra }: { href: string; icon: ReactNode; title: string; copy: string; extra?: ReactNode }) {
  return (
    <Link href={href} style={cardStyle}>
      <div style={iconWrapStyle}>{icon}</div>
      <div style={{ display: "grid", gap: 8 }}>
        <div style={titleStyle}>{title}</div>
        <div style={copyStyle}>{copy}</div>
        {extra ? <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginTop: 4 }}>{extra}</div> : null}
      </div>
    </Link>
  );
}

function iconShell(children: ReactNode) {
  return <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">{children}</svg>;
}
function PersonIcon() { return iconShell(<><circle cx="12" cy="8" r="3.4" /><path d="M5.8 19c1.8-3 4.1-4.5 6.2-4.5S16.4 16 18.2 19" /></>); }
function TableIcon() { return iconShell(<><rect x="4" y="6" width="16" height="12" rx="2" /><path d="M8 6v12M16 6v12M4 12h16" /></>); }
function ChartIcon() { return iconShell(<><path d="M5 18V8" /><path d="M12 18V5" /><path d="M19 18v-9" /></>); }
function ClipboardIcon() { return iconShell(<><rect x="6" y="5" width="12" height="15" rx="2" /><path d="M9 5.5h6v3H9z" /></>); }
function CoachIcon() { return iconShell(<><circle cx="8" cy="10" r="2.5" /><circle cx="16" cy="10" r="2.5" /><path d="M4.8 18c.9-2 2.1-3 3.2-3s2.3 1 3.2 3" /><path d="M12.8 18c.9-2 2.1-3 3.2-3s2.3 1 3.2 3" /></>); }
function formatScore(value: number | null | undefined): string { return value == null ? "—" : `${Math.round(value)}`; }

const cardStyle: CSSProperties = { display: "grid", gap: 14, alignContent: "start", paddingTop: 18, borderTop: "1px solid var(--line-soft)", minHeight: 210 };
const iconWrapStyle: CSSProperties = { width: 56, height: 56, borderRadius: 999, background: "rgba(20,18,16,1)", color: "var(--text)", display: "grid", placeItems: "center", border: "1px solid var(--line)" };
const titleStyle: CSSProperties = { fontSize: 34, fontWeight: 780, letterSpacing: "-.04em" };
const copyStyle: CSSProperties = { color: "var(--text-65)", lineHeight: 1.7, fontSize: 16 };
const errorStyle: CSSProperties = { color: "var(--accent)", fontWeight: 700 };
const growthGridStyle: CSSProperties = { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 340px), 1fr))", gap: 20, alignItems: "start" };
const growthPanelStyle: CSSProperties = { borderTop: "1px solid var(--line-soft)", paddingTop: 18, display: "grid", gap: 14 };
const eyebrowStyle: CSSProperties = { color: "var(--accent)", fontSize: 12, textTransform: "uppercase", letterSpacing: 1.2, fontWeight: 900 };
const sectionTitleStyle: CSSProperties = { margin: 0, fontSize: 26, lineHeight: 1.12 };
const smallTitleStyle: CSSProperties = { color: "var(--text)", fontWeight: 850, lineHeight: 1.4 };
const metaStyle: CSSProperties = { color: "var(--text-45)", fontSize: 13, lineHeight: 1.55, marginTop: 4 };
const stackStyle: CSSProperties = { display: "grid", gap: 12 };
const miniRowStyle: CSSProperties = { display: "grid", gridTemplateColumns: "minmax(0, 1fr) auto", gap: 14, alignItems: "center", padding: "13px 0", borderTop: "1px solid var(--line-soft)" };
const miniMetricStyle: CSSProperties = { color: "var(--text)", fontSize: 12, fontWeight: 850, textAlign: "right" };
const buttonLinkStyle: CSSProperties = { width: "fit-content", padding: "11px 15px", borderRadius: 14, border: "1px solid var(--accent)", background: "var(--accent)", color: "var(--text)", textDecoration: "none", fontWeight: 850 };

"use client";

import { useEffect, useState, type CSSProperties, type ReactNode } from "react";
import Link from "next/link";
import AppShell from "../../components/app/AppShell";
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
  coach_summary?: { completed_hands: number; avg_ranging_score: number | null; avg_response_score: number | null } | null;
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
    const activeUser = user;
    let cancelled = false;
    async function loadOverview() {
      try {
        const res = await apiFetch(`${API_BASE}/dashboard/overview`, { cache: "no-store" });
        const data = await res.json();
        if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Unable to load home.");
        if (!cancelled) {
          setOverview(data as OverviewPayload);
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Unable to load home.");
      }
    }
    void loadOverview();
    return () => { cancelled = true; };
  }, [user]);

  const suggestion = overview?.suggested_practice?.[0] ?? null;
  const topAssignment = overview?.assignments?.[0] ?? null;
  const isCoach = user?.role === "owner" || user?.role === "admin" || user?.role === "coach";
  const coachSummary = overview?.coach_summary ?? overview?.summary;
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
            {isCoach ? (
              <>
                <HomeLinkCard href="/results" icon={<ChartIcon />} title="Results" copy="Pool and member score trends, filters, and debrief history." extra={<div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}><span className="badge badge-success">Range Score {formatScore(coachSummary?.avg_ranging_score ?? null)}</span><span className="badge badge-primary">Action Score {formatScore(coachSummary?.avg_response_score ?? null)}</span></div>} />
                <HomeLinkCard href="/review" icon={<ReviewIcon />} title="Review" copy="Flagged member hands for replay, notes, and coaching follow-up." extra={<span className="badge badge-primary">Flagged hands</span>} />
                <HomeLinkCard href="/admin" icon={<CoachIcon />} title="Coach" copy={topAssignment ? `Active assignment: ${topAssignment.title}. Review analytics and assign the next reps.` : "Analytics, assignments, cohorts, and member oversight."} extra={<span className="badge badge-primary">{coachSummary?.completed_hands ?? overview.summary.completed_hands} finished hands</span>} />
              </>
            ) : (
              <>
                <HomeLinkCard href={suggestion?.quick_start_url || "/screen-1"} icon={<TableIcon />} title="Train" copy={cleanedSuggestionReason || "Open the trainer and run the next live rep."} extra={<span className="badge badge-primary">{suggestion ? "Start next rep" : "Train"}</span>} />
                <HomeLinkCard href="/study" icon={<StudyIcon />} title="Study" copy="Review default charts and adjustment points before live reps." extra={<span className="badge badge-primary">Preflop charts</span>} />
                <HomeLinkCard href="/assignments" icon={<ClipboardIcon />} title="Assignments" copy={topAssignment ? `${topAssignment.title} · ${topAssignment.progress.progress_count}/${topAssignment.progress.repetition_target} reps complete.` : "Coach work and guided practice appear here."} extra={<span className="badge badge-primary">{overview.summary.assignments_active} active</span>} />
              </>
            )}
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
      <div style={cardBodyStyle}>
        <div style={titleStyle}>{title}</div>
        <div style={copyStyle}>{copy}</div>
        {extra ? <div style={extraRowStyle}>{extra}</div> : null}
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
function StudyIcon() { return iconShell(<><path d="M5 6.5h6a3 3 0 0 1 3 3V19H8a3 3 0 0 1-3-3z" /><path d="M19 6.5h-5v12.5h2a3 3 0 0 0 3-3z" /></>); }
function ReviewIcon() { return iconShell(<><path d="M6 5h12v14H6z" /><path d="M9 9h6" /><path d="M9 13h4" /><path d="M15.5 14.5l1.2 1.2 2.1-2.4" /></>); }
function formatScore(value: number | null | undefined): string { return value == null ? "—" : `${Math.round(value)}`; }

const cardStyle: CSSProperties = { display: "flex", flexDirection: "column", gap: 14, paddingTop: 18, borderTop: "1px solid var(--line-soft)", minHeight: 210 };
const iconWrapStyle: CSSProperties = { width: 56, height: 56, borderRadius: 999, background: "rgba(20,18,16,1)", color: "var(--text)", display: "grid", placeItems: "center", border: "1px solid var(--line)" };
const cardBodyStyle: CSSProperties = { display: "flex", flexDirection: "column", gap: 8, flex: 1 };
const extraRowStyle: CSSProperties = { display: "flex", gap: 10, flexWrap: "wrap", marginTop: "auto", paddingTop: 4 };
const titleStyle: CSSProperties = { fontSize: 34, fontWeight: 780, letterSpacing: "-.04em" };
const copyStyle: CSSProperties = { color: "var(--text-65)", lineHeight: 1.7, fontSize: 16 };
const errorStyle: CSSProperties = { color: "var(--accent)", fontWeight: 700 };

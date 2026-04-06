"use client";

import { useEffect, useState, type CSSProperties } from "react";
import Link from "next/link";
import AppShell from "../../components/app/AppShell";
import { API_BASE, apiFetch } from "../../lib/api";
import { useRequireAuth } from "../../lib/hooks/useRequireAuth";

type AssignmentRow = {
  assignment_id: string;
  title: string;
  description: string | null;
  scenario_id: string | null;
  scenario_display_name?: string | null;
  villain_profile_id: string | null;
  villain_display_name?: string | null;
  due_at: string | null;
  status: string;
  minimum_overall_score: number | null;
  progress: {
    progress_count: number;
    repetition_target: number;
    progress_percent: number;
    remaining_reps: number;
    avg_overall_score: number | null;
    status: string;
    is_overdue: boolean;
  };
};

type Suggestion = {
  title: string;
  description: string;
  reason: string;
  quick_start_url: string;
};

type Payload = {
  summary: { total: number; active: number; completed: number; overdue: number };
  assignments: AssignmentRow[];
  suggested_practice: Suggestion[];
};

const PALETTE = { cream: "#F0EBE0", coral: "#E76F51", green: "#6A9E72", muted: "rgba(240,235,224,0.45)" };

export default function AssignmentsPage() {
  const { user, isAuthLoading, authError } = useRequireAuth();
  const [payload, setPayload] = useState<Payload | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;
    let cancelled = false;
    async function load() {
      try {
        const res = await apiFetch(`${API_BASE}/assignments/my`, { cache: "no-store" });
        const data = await res.json();
        if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Unable to load assignments.");
        if (!cancelled) setPayload(data as Payload);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Unable to load assignments.");
      }
    }
    void load();
    return () => { cancelled = true; };
  }, [user]);

  const headerStats = payload ? (
    <>
      <HeaderStat label="Active" value={payload.summary.active} tone="coral" />
      <HeaderStat label="Completed" value={payload.summary.completed} tone="green" />
      <HeaderStat label="Overdue" value={payload.summary.overdue} tone="neutral" />
    </>
  ) : null;

  return (
    <AppShell title="Assignments" subtitle="A simple queue: coach work first, smart practice suggestions second." headerContent={headerStats}>
      {isAuthLoading ? <div style={panelStyle}>Loading assignments…</div> : null}
      {authError ? <div style={errorStyle}>{authError}</div> : null}
      {error ? <div style={errorStyle}>{error}</div> : null}
      {payload ? (
        <section style={gridStyle}>
          <section style={panelStyle}>
            <SectionHeader eyebrow="Assigned reps" title="Your current queue" />
            <div style={stackStyle}>
              {payload.assignments.length ? payload.assignments.map((assignment) => (
                <AssignmentCard key={assignment.assignment_id} assignment={assignment} />
              )) : <div style={emptyStateStyle}>No coach assignments yet.</div>}
            </div>
          </section>

          <section style={panelStyle}>
            <SectionHeader eyebrow="Suggested practice" title="Smart next reps" />
            <div style={stackStyle}>
              {payload.suggested_practice.length ? payload.suggested_practice.map((item) => (
                <SuggestionCard key={`${item.title}-${item.quick_start_url}`} item={item} />
              )) : <div style={emptyStateStyle}>Complete more scored hands to unlock suggestions.</div>}
            </div>
          </section>
        </section>
      ) : null}
    </AppShell>
  );
}

function buildQuickStartUrl(assignment: AssignmentRow): string {
  const params = new URLSearchParams();
  if (assignment.scenario_id) params.set("scenario_id", assignment.scenario_id);
  if (assignment.villain_profile_id) params.set("villain_profile_id", assignment.villain_profile_id);
  const query = params.toString();
  return query ? `/screen-1?${query}` : "/screen-1";
}

function SectionHeader({ eyebrow, title }: { eyebrow: string; title: string }) {
  return <div style={sectionHeaderStyle}><div style={eyebrowStyle}>{eyebrow}</div><h2 style={sectionTitleStyle}>{title}</h2></div>;
}

function HeaderStat({ label, value, tone }: { label: string; value: string | number; tone: "coral" | "green" | "neutral" }) {
  const toneStyle = tone === "coral"
    ? { borderColor: PALETTE.coral, background: PALETTE.coral, color: PALETTE.cream }
    : tone === "green"
      ? { borderColor: PALETTE.green, background: PALETTE.green, color: "#141210" }
      : { borderColor: "var(--line)", background: "var(--surface-fill-strong)", color: PALETTE.cream };
  return <div style={{ ...headerStatStyle, ...toneStyle }}><div style={headerStatLabelStyle}>{label}</div><div style={headerStatValueStyle}>{value}</div></div>;
}

function AssignmentCard({ assignment }: { assignment: AssignmentRow }) {
  const progressWidth = `${Math.max(6, Math.min(100, Math.round(assignment.progress.progress_percent || 0)))}%`;
  const statusTone = assignment.progress.is_overdue ? "overdue" : assignment.status === "completed" ? "completed" : "active";
  const dueText = assignment.due_at ? `Due ${new Date(assignment.due_at).toLocaleDateString()}` : "No due date";
  const scope = [assignment.scenario_display_name, assignment.villain_display_name].filter(Boolean);

  return (
    <div style={assignmentCardStyle}>
      <div style={assignmentCardTopStyle}>
        <div style={{ minWidth: 0 }}>
          <div style={assignmentTitleStyle}>{assignment.title}</div>
          <div style={assignmentScopeStyle}>{scope.length ? scope.join(" · ") : "Open practice scope"}</div>
        </div>
        <div style={assignmentMetaWrapStyle}>
          <span style={{ ...statusPillStyle, ...(statusTone === "overdue" ? overduePillStyle : statusTone === "completed" ? completedPillStyle : activePillStyle) }}>
            {assignment.progress.is_overdue ? "Overdue" : assignment.status}
          </span>
          <span style={metaPillStyle}>{dueText}</span>
        </div>
      </div>

      {assignment.description ? <div style={assignmentDescriptionStyle}>{assignment.description}</div> : null}

      <div style={assignmentProgressMetaStyle}>
        <span>{assignment.progress.progress_count}/{assignment.progress.repetition_target} reps complete</span>
        {assignment.minimum_overall_score != null ? <span>Minimum score {assignment.minimum_overall_score}</span> : null}
        {assignment.progress.avg_overall_score != null ? <span>Average score {Math.round(assignment.progress.avg_overall_score)}</span> : null}
      </div>

      <div style={progressTrackStyle}>
        <div style={{ ...progressFillStyle, width: progressWidth }} />
      </div>

      <div style={assignmentFooterStyle}>
        <div style={remainingCopyStyle}>
          {assignment.progress.remaining_reps > 0 ? `${assignment.progress.remaining_reps} reps remaining` : "Rep target reached"}
        </div>
        <Link href={buildQuickStartUrl(assignment)} style={primaryLinkStyle}>Start reps</Link>
      </div>
    </div>
  );
}

function SuggestionCard({ item }: { item: Suggestion }) {
  return (
    <div style={suggestionCardStyle}>
      <div style={{ minWidth: 0 }}>
        <div style={suggestionTitleStyle}>{item.title}</div>
        <div style={suggestionDescriptionStyle}>{item.description}</div>
        <div style={suggestionReasonStyle}>{item.reason}</div>
      </div>
      <Link href={item.quick_start_url} style={secondaryLinkStyle}>Quick start</Link>
    </div>
  );
}

const panelStyle: CSSProperties = { borderTop: "1px solid var(--line-soft)", paddingTop: 18 };
const errorStyle: CSSProperties = { color: "var(--accent)", fontWeight: 700 };
const gridStyle: CSSProperties = { display: "grid", gridTemplateColumns: "minmax(0, 1.08fr) minmax(340px, 0.92fr)", gap: 28, alignItems: "start" };
const sectionHeaderStyle: CSSProperties = { display: "grid", gap: 8, marginBottom: 18 };
const eyebrowStyle: CSSProperties = { color: PALETTE.coral, fontSize: 12, textTransform: "uppercase", letterSpacing: 1.3, fontWeight: 900 };
const sectionTitleStyle: CSSProperties = { margin: 0, fontSize: 24, lineHeight: 1.08 };
const headerStatStyle: CSSProperties = { minWidth: 140, borderRadius: 18, padding: "14px 16px", border: "1px solid var(--line)", background: "rgba(20,18,16,1)" };
const headerStatLabelStyle: CSSProperties = { fontSize: 11, textTransform: "uppercase", letterSpacing: 1.1, fontWeight: 800, opacity: 0.9 };
const headerStatValueStyle: CSSProperties = { marginTop: 6, fontSize: 24, fontWeight: 900 };
const stackStyle: CSSProperties = { display: "grid", gap: 14 };
const assignmentCardStyle: CSSProperties = {
  display: "grid",
  gap: 14,
  padding: "18px 18px 16px",
  borderRadius: 18,
  border: "1px solid var(--line)",
  background: "var(--surface-fill-strong)",
  boxShadow: "0 10px 28px rgba(20,18,16,0.18)",
};
const assignmentCardTopStyle: CSSProperties = { display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 14, flexWrap: "wrap" };
const assignmentTitleStyle: CSSProperties = { fontSize: 27, fontWeight: 820, lineHeight: 1.02, letterSpacing: "-.04em", color: PALETTE.cream };
const assignmentScopeStyle: CSSProperties = { marginTop: 8, fontSize: 14, lineHeight: 1.55, color: "rgba(240,235,224,0.72)" };
const assignmentDescriptionStyle: CSSProperties = { fontSize: 14, lineHeight: 1.65, color: "rgba(240,235,224,0.65)" };
const assignmentMetaWrapStyle: CSSProperties = { display: "flex", gap: 8, flexWrap: "wrap", justifyContent: "flex-end" };
const statusPillStyle: CSSProperties = { padding: "8px 12px", borderRadius: 999, fontSize: 12, fontWeight: 800, textTransform: "uppercase", border: "1px solid var(--line)" };
const activePillStyle: CSSProperties = { background: "var(--surface-fill-strong)", color: PALETTE.cream };
const overduePillStyle: CSSProperties = { background: PALETTE.coral, borderColor: PALETTE.coral, color: PALETTE.cream };
const completedPillStyle: CSSProperties = { background: PALETTE.green, borderColor: PALETTE.green, color: "#141210" };
const metaPillStyle: CSSProperties = { padding: "8px 12px", borderRadius: 999, fontSize: 12, fontWeight: 800, border: "1px solid var(--line)", color: PALETTE.cream, background: "rgba(20,18,16,1)" };
const assignmentProgressMetaStyle: CSSProperties = { display: "flex", gap: 12, flexWrap: "wrap", fontSize: 13, color: "rgba(240,235,224,0.65)" };
const progressTrackStyle: CSSProperties = { width: "100%", height: 10, borderRadius: 999, overflow: "hidden", background: "rgba(240,235,224,0.12)" };
const progressFillStyle: CSSProperties = { height: "100%", borderRadius: 999, background: PALETTE.coral };
const assignmentFooterStyle: CSSProperties = { display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16, flexWrap: "wrap" };
const remainingCopyStyle: CSSProperties = { fontSize: 13, color: PALETTE.muted, fontWeight: 700 };
const primaryLinkStyle: CSSProperties = { padding: "11px 18px", borderRadius: 999, background: PALETTE.coral, color: PALETTE.cream, fontWeight: 800, textDecoration: "none", whiteSpace: "nowrap" };
const suggestionCardStyle: CSSProperties = { display: "flex", justifyContent: "space-between", gap: 16, alignItems: "center", padding: "18px", borderRadius: 18, border: "1px solid var(--line)", background: "var(--surface-fill-strong)" };
const suggestionTitleStyle: CSSProperties = { fontSize: 18, fontWeight: 800, color: PALETTE.cream };
const suggestionDescriptionStyle: CSSProperties = { marginTop: 6, fontSize: 14, lineHeight: 1.6, color: "rgba(240,235,224,0.72)" };
const suggestionReasonStyle: CSSProperties = { marginTop: 8, fontSize: 13, lineHeight: 1.55, color: PALETTE.muted };
const secondaryLinkStyle: CSSProperties = { padding: "10px 16px", borderRadius: 999, border: "1px solid var(--line)", color: PALETTE.cream, textDecoration: "none", fontWeight: 700, whiteSpace: "nowrap", background: "transparent" };
const emptyStateStyle: CSSProperties = { color: PALETTE.muted, padding: "12px 0 4px" };

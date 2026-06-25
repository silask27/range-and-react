"use client";

import { useEffect, useMemo, useState, type CSSProperties } from "react";
import Link from "next/link";
import AppShell from "../../components/app/AppShell";
import { API_BASE, apiFetch } from "../../lib/api";
import { useRequireAuth } from "../../lib/hooks/useRequireAuth";

type ReviewState = {
  flagged: boolean;
  sent_to_coaches: boolean;
  status: string;
  flagged_at: string | null;
  sent_at: string | null;
};

type ReviewEntry = {
  hand_id: string;
  session_id: string;
  owner_user_id?: string | null;
  owner_display_name?: string | null;
  owner_email?: string | null;
  scenario_display_name?: string | null;
  villain_display_name?: string | null;
  completed_at: string | null;
  ranging_score: number | null;
  response_score: number | null;
  overall_score: number | null;
  review?: ReviewState;
};

export default function ReviewPage() {
  const { user, isAuthLoading, authError } = useRequireAuth();
  const [rows, setRows] = useState<ReviewEntry[]>([]);
  const [memberId, setMemberId] = useState("all");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    if (!user) return;
    let cancelled = false;
    async function loadQueue() {
      setIsLoading(true);
      setError(null);
      try {
        const res = await apiFetch(`${API_BASE}/results/review-queue`, { cache: "no-store" });
        const data = await res.json();
        if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Unable to load review queue.");
        if (!cancelled) setRows((data as { review_queue?: ReviewEntry[] }).review_queue ?? []);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Unable to load review queue.");
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }
    void loadQueue();
    return () => {
      cancelled = true;
    };
  }, [user]);

  const memberOptions = useMemo(() => {
    const map = new Map<string, string>();
    rows.forEach((row) => {
      const id = row.owner_user_id || "";
      if (!id || id === user?.user_id) return;
      map.set(id, row.owner_display_name || row.owner_email || "Member");
    });
    return Array.from(map.entries())
      .map(([id, display_name]) => ({ id, display_name }))
      .sort((a, b) => a.display_name.localeCompare(b.display_name));
  }, [rows, user?.user_id]);

  const memberRows = rows.filter((row) => row.owner_user_id !== user?.user_id);
  const exampleRows = rows.filter((row) => row.owner_user_id === user?.user_id);
  const filteredMemberRows = memberId === "all"
    ? memberRows
    : memberRows.filter((row) => row.owner_user_id === memberId);

  const headerStats = (
    <>
      <HeaderStat label="Member Flags" value={memberRows.length} tone="coral" />
      <HeaderStat label="Coach Examples" value={exampleRows.length} tone="green" />
      <HeaderStat label="Members" value={memberOptions.length} tone="neutral" />
    </>
  );

  return (
    <AppShell title="Review" subtitle="Replay flagged member hands and keep coach example hands separate." headerContent={headerStats}>
      {isAuthLoading || isLoading ? <div style={panelStyle}>Loading review queue…</div> : null}
      {authError ? <div style={errorStyle}>{authError}</div> : null}
      {error ? <div style={errorStyle}>{error}</div> : null}

      <section style={panelStyle}>
        <div style={barHeaderStyle}>
          <div>
            <div style={eyebrowStyle}>Member filter</div>
            <h2 style={sectionTitleStyle}>Flagged hands from members</h2>
          </div>
          <label style={filterLabelStyle}>
            <span style={captionStyle}>Member</span>
            <select value={memberId} onChange={(event) => setMemberId(event.target.value)} style={selectStyle}>
              <option value="all">All members</option>
              {memberOptions.map((option) => (
                <option key={option.id} value={option.id}>{option.display_name}</option>
              ))}
            </select>
          </label>
        </div>
        <ReviewList rows={filteredMemberRows} emptyCopy="No member hands are waiting for review." />
      </section>

      <section style={panelStyle}>
        <div style={sectionHeaderStyle}>
          <div>
            <div style={eyebrowStyle}>Walkthroughs</div>
            <h2 style={sectionTitleStyle}>Coach example hands</h2>
          </div>
        </div>
        <ReviewList rows={exampleRows} emptyCopy="Flag one of your own completed hands to save it here as a walkthrough example." />
      </section>
    </AppShell>
  );
}

function ReviewList({ rows, emptyCopy }: { rows: ReviewEntry[]; emptyCopy: string }) {
  if (!rows.length) return <div style={emptyStyle}>{emptyCopy}</div>;
  return (
    <div style={scrollListStyle}>
      {rows.map((row) => (
        <div key={row.hand_id} style={rowStyle}>
          <div style={{ minWidth: 0 }}>
            <div style={rowTitleStyle}>{row.scenario_display_name || "Scenario"} · {row.villain_display_name || "Villain"}</div>
            <div style={rowMetaStyle}>
              {row.owner_display_name || row.owner_email || "Member"} · {compactDate(row.completed_at)} · {row.review?.status || "flagged"}
            </div>
            <div style={rowHelperStyle}>
              Range {formatScore(row.ranging_score)} · Action {formatScore(row.response_score)} · Overall {formatScore(row.overall_score)}
            </div>
          </div>
          <div style={rowActionsStyle}>
            <Link href={replayHref(row)} style={secondaryLinkStyle}>Replay</Link>
            <Link href={`/results/hand/${encodeURIComponent(row.hand_id)}`} style={secondaryLinkStyle}>Debrief</Link>
          </div>
        </div>
      ))}
    </div>
  );
}

function HeaderStat({ label, value, tone }: { label: string; value: string | number; tone: "coral" | "green" | "neutral" }) {
  const toneStyle = tone === "coral"
    ? { borderColor: "#E76F51", background: "#E76F51", color: "#F0EBE0" }
    : tone === "green"
      ? { borderColor: "#6A9E72", background: "#6A9E72", color: "#141210" }
      : { borderColor: "var(--line)", background: "var(--surface-fill-strong)", color: "#F0EBE0" };
  return <div style={{ ...headerStatStyle, ...toneStyle }}><div style={headerStatLabelStyle}>{label}</div><div style={headerStatValueStyle}>{value}</div></div>;
}

function replayHref(row: ReviewEntry) {
  const params = new URLSearchParams({ hand_id: row.hand_id, replay: "1" });
  if (row.session_id) params.set("session_id", row.session_id);
  return `/screen-1?${params.toString()}`;
}

function compactDate(value: string | null) {
  return value ? new Date(value).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }) : "Completed";
}

function formatScore(value: number | null | undefined) {
  return value == null ? "—" : `${Math.round(value)}`;
}

const panelStyle: CSSProperties = { borderTop: "1px solid var(--line-soft)", paddingTop: 18 };
const errorStyle: CSSProperties = { color: "var(--accent)", fontWeight: 800 };
const barHeaderStyle: CSSProperties = { display: "flex", justifyContent: "space-between", alignItems: "flex-end", gap: 16, flexWrap: "wrap", marginBottom: 18 };
const sectionHeaderStyle: CSSProperties = { display: "grid", gap: 8, marginBottom: 16 };
const eyebrowStyle: CSSProperties = { color: "#E76F51", fontSize: 12, textTransform: "uppercase", letterSpacing: 1.2, fontWeight: 900 };
const sectionTitleStyle: CSSProperties = { margin: 0, fontSize: 26, lineHeight: 1.1 };
const captionStyle: CSSProperties = { color: "var(--text-45)", fontSize: 11, textTransform: "uppercase", letterSpacing: 1.1, fontWeight: 800 };
const filterLabelStyle: CSSProperties = { minWidth: 240, display: "grid", gap: 8 };
const selectStyle: CSSProperties = { width: "100%", borderRadius: 12, border: "1px solid var(--line)", background: "var(--surface-fill)", color: "var(--text)", padding: "12px 13px", fontWeight: 800 };
const headerStatStyle: CSSProperties = { width: 174, minHeight: 86, borderRadius: 18, padding: "13px 15px", border: "1px solid var(--line)", display: "flex", flexDirection: "column", justifyContent: "space-between" };
const headerStatLabelStyle: CSSProperties = { color: "inherit", opacity: 0.9, fontSize: 11, textTransform: "uppercase", letterSpacing: 1.1, fontWeight: 800 };
const headerStatValueStyle: CSSProperties = { marginTop: 6, fontSize: 28, fontWeight: 900, color: "inherit" };
const listStyle: CSSProperties = { display: "grid", gap: 12 };
const scrollListStyle: CSSProperties = { ...listStyle, maxHeight: 560, overflowY: "auto", paddingRight: 6 };
const rowStyle: CSSProperties = { display: "grid", gridTemplateColumns: "minmax(0, 1fr) auto", gap: 16, alignItems: "center", padding: "15px 0", borderTop: "1px solid var(--line-soft)" };
const rowTitleStyle: CSSProperties = { color: "var(--text)", fontWeight: 900, lineHeight: 1.35 };
const rowMetaStyle: CSSProperties = { color: "var(--text-45)", fontSize: 13, lineHeight: 1.55, marginTop: 4 };
const rowHelperStyle: CSSProperties = { color: "var(--text-65)", fontSize: 13, lineHeight: 1.55, marginTop: 4 };
const rowActionsStyle: CSSProperties = { display: "flex", gap: 10, flexWrap: "wrap", justifyContent: "flex-end" };
const secondaryLinkStyle: CSSProperties = { padding: "10px 13px", borderRadius: 12, border: "1px solid var(--line)", color: "var(--text)", textDecoration: "none", fontWeight: 850 };
const emptyStyle: CSSProperties = { color: "var(--text-65)", borderTop: "1px solid var(--line-soft)", paddingTop: 14, lineHeight: 1.6 };

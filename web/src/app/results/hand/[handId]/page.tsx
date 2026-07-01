"use client";

import { useEffect, useMemo, useState, type CSSProperties, type ReactNode } from "react";
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
    current_strength_vs_hero?: number;
    hero_range_source: string;
  };
  review?: {
    flagged: boolean;
    sent_to_coaches: boolean;
    status: string;
    member_note?: string | null;
    coach_note?: string | null;
    reviewed_at?: string | null;
    reviewed_by_user_id?: string | null;
  };
  prune_evaluations: Array<{
    street: string;
    villain_action: string | null;
    actual_bucket: string;
    actual_subgroup: string;
    actual_display_subgroup?: string;
    start_live_combos: number;
    end_live_combos: number;
    combo_alive: boolean;
    bucket_alive: boolean;
    subgroup_alive: boolean;
    efficiency_score: number | null;
    overall_score: number;
    posterior_scoring?: {
      observed_action_key?: string;
      posterior_mass_kept?: number;
      low_posterior_junk_removed?: number;
      overall_score?: number;
      raw_overall_score?: number;
      survival_cap?: number;
      prior_combo_count?: number;
      scored_combo_count?: number;
      kept_combo_count?: number;
    } | null;
  }>;
  response_evaluations: Array<{
    street: string;
    actual_bucket: string;
    actual_subgroup: string;
    actual_display_subgroup?: string;
    hero_action: string;
    column: string | null;
    predicted: string | null;
    actual: string | null;
    villain_action: string | null;
    supported: boolean;
    score: number | null;
    correct: boolean | null;
    reason: string | null;
    score_method?: string;
    bucket_level_scores?: Array<{
      bucket: string;
      predicted: string | null;
      best_response?: string | null;
      probabilities: Record<string, number>;
      selected_probability: number;
      best_probability: number;
      score: number | null;
      combo_count: number;
      combos_scored?: number;
    }>;
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

const PALETTE = {
  cream: "#F0EBE0",
  coral: "#E76F51",
  green: "#6A9E72",
  muted: "rgba(240,235,224,0.65)",
  soft: "rgba(240,235,224,0.45)",
};

export default function HandDebriefPage() {
  const params = useParams<{ handId: string }>();
  const handId = Array.isArray(params?.handId) ? params.handId[0] : params?.handId;
  const { user, isAuthLoading, authError } = useRequireAuth();
  const [payload, setPayload] = useState<DebriefPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reviewDraft, setReviewDraft] = useState({ member_note: "", coach_note: "" });
  const [reviewMessage, setReviewMessage] = useState<string | null>(null);
  const [isSavingReview, setIsSavingReview] = useState(false);

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

  useEffect(() => {
    setReviewDraft({
      member_note: payload?.review?.member_note ?? "",
      coach_note: payload?.review?.coach_note ?? "",
    });
    setReviewMessage(null);
  }, [payload?.hand_id, payload?.review?.member_note, payload?.review?.coach_note]);

  const rangeTakeaway = useMemo(() => {
    if (!payload) return null;
    return summarizePruning(payload.prune_evaluations);
  }, [payload]);

  const responseTakeaway = useMemo(() => {
    if (!payload) return null;
    return summarizeResponses(payload.response_evaluations);
  }, [payload]);

  const canCoachReview = user?.role === "owner" || user?.role === "admin" || user?.role === "coach";
  const replayHref = payload
    ? `/screen-1?session_id=${encodeURIComponent(payload.session_id)}&hand_id=${encodeURIComponent(payload.hand_id)}&replay=1`
    : "#";

  async function saveReviewNote(markReviewed = false) {
    if (!payload) return;
    setIsSavingReview(true);
    setReviewMessage(null);
    try {
      const body = canCoachReview
        ? { coach_note: reviewDraft.coach_note, mark_reviewed: markReviewed }
        : { member_note: reviewDraft.member_note };
      const res = await apiFetch(`${API_BASE}/results/hand/${encodeURIComponent(payload.hand_id)}/review`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Unable to save review note.");
      setPayload((current) => current ? { ...current, review: data.review } : current);
      setReviewMessage(markReviewed ? "Marked reviewed." : "Review note saved.");
    } catch (err) {
      setReviewMessage(err instanceof Error ? err.message : "Unable to save review note.");
    } finally {
      setIsSavingReview(false);
    }
  }

  return (
    <AppShell
      title="Hand debrief"
      subtitle="The big-picture review: final truth, Range Score, Action Score, and the exact streets that mattered."
    >
      {isAuthLoading ? <div style={emptyStyle}>Loading hand debrief…</div> : null}
      {authError ? <div style={errorStyle}>{authError}</div> : null}
      {error ? <div style={errorStyle}>{error}</div> : null}
      {payload ? (
        <div style={pageStackStyle}>
          <section style={summaryGridStyle}>
            <ScoreCard
              eyebrow="Overall"
              title={formatScore(payload.summary.overall_score)}
              copy="Combined result for this hand."
              tone="neutral"
            />
            <ScoreCard
              eyebrow="Range Score"
              title={formatScore(payload.summary.ranging_score)}
              copy={rangeTakeaway?.headline ?? "No ranging steps were scored."}
              tone="green"
            />
            <ScoreCard
              eyebrow="Action Score"
              title={formatScore(payload.summary.response_score)}
              copy={responseTakeaway?.headline ?? "No Action Score nodes were scored."}
              tone="coral"
            />
          </section>

          <section style={truthPanelStyle}>
            <div style={{ minWidth: 0 }}>
              <div style={eyebrowStyle}>Final truth</div>
              <h2 style={sectionTitleStyle}>What villain actually had</h2>
              <div style={truthHeadlineStyle}>
                {payload.actual_final_bucket.bucket_label} · {payload.actual_final_bucket.subgroup_label}
              </div>
              <div style={truthMetaStyle}>
                Bucket score vs hero:{" "}
                {(payload.actual_final_bucket.current_strength_vs_hero ?? payload.actual_final_bucket.equity_vs_hero).toFixed(3)}
              </div>
              <div style={truthMetaStyle}>
                Total equity vs hero: {payload.actual_final_bucket.equity_vs_hero.toFixed(3)}
              </div>
            </div>
            <div style={truthGridStyle}>
              <InfoChip label="Hero hand" value={payload.hero_hand.join(" ")} />
              <InfoChip label="Villain hand" value={payload.villain_hand.join(" ")} />
              <InfoChip label="Board" value={payload.board.join(" ")} />
            </div>
          </section>

          {payload.review?.flagged ? (
            <section style={reviewPanelStyle}>
              <div style={sectionHeaderStyle}>
                <div>
                  <div style={eyebrowStyle}>Coach review</div>
                  <h2 style={sectionTitleStyle}>Replay discussion</h2>
                  <div style={sectionHeadlineStyle}>
                    Use this space to prep or capture the coaching note that goes with the hand replay.
                  </div>
                </div>
                <Link href={replayHref} style={secondaryLinkStyle}>Open replay</Link>
              </div>
              <div style={reviewGridStyle}>
                <label style={reviewFieldStyle}>
                  <span style={reviewLabelStyle}>Member note</span>
                  <textarea
                    value={reviewDraft.member_note}
                    onChange={(event) => setReviewDraft((current) => ({ ...current, member_note: event.target.value }))}
                    disabled={canCoachReview}
                    rows={5}
                    placeholder="No member note yet."
                    style={reviewTextAreaStyle}
                  />
                </label>
                <label style={reviewFieldStyle}>
                  <span style={reviewLabelStyle}>Coach comment</span>
                  <textarea
                    value={reviewDraft.coach_note}
                    onChange={(event) => setReviewDraft((current) => ({ ...current, coach_note: event.target.value }))}
                    disabled={!canCoachReview}
                    rows={5}
                    placeholder={canCoachReview ? "Add the coaching point to discuss during replay." : "No coach comment yet."}
                    style={reviewTextAreaStyle}
                  />
                </label>
              </div>
              <div style={reviewFooterStyle}>
                <div style={rowMetaStyle}>
                  Status: {payload.review.status || "flagged"}
                  {payload.review.reviewed_at ? ` · Reviewed ${formatDate(payload.review.reviewed_at)}` : ""}
                </div>
                <div style={reviewActionsStyle}>
                  <button type="button" onClick={() => void saveReviewNote(false)} disabled={isSavingReview} style={secondaryButtonStyle}>
                    {isSavingReview ? "Saving..." : "Save note"}
                  </button>
                  {canCoachReview ? (
                    <button type="button" onClick={() => void saveReviewNote(true)} disabled={isSavingReview} style={primaryButtonStyle}>
                      Mark reviewed
                    </button>
                  ) : null}
                </div>
              </div>
              {reviewMessage ? <div style={reviewMessage.startsWith("Unable") ? errorStyle : emptyStyle}>{reviewMessage}</div> : null}
            </section>
          ) : null}

          <section style={twoColumnStyle}>
            <MetricSection
              eyebrow="Ranging"
              title="How close was your remaining range?"
              score={payload.summary.ranging_score}
              accent={PALETTE.green}
              headline={rangeTakeaway?.detail ?? "No prune evaluations were recorded for this hand."}
            >
              <div style={compactListStyle}>
                {payload.prune_evaluations.length ? payload.prune_evaluations.map((item, index) => (
                  <PruneRow key={`${item.street}-${index}`} item={item} />
                )) : <EmptyState copy="No prune evaluations were recorded for this hand." />}
              </div>
            </MetricSection>

            <MetricSection
              eyebrow="Action Score"
              title="How close were your bucket reads?"
              score={payload.summary.response_score}
              accent={PALETTE.coral}
              headline={responseTakeaway?.detail ?? "No response evaluations were recorded for this hand."}
            >
              <div style={compactListStyle}>
                {payload.response_evaluations.length ? payload.response_evaluations.map((item, index) => (
                  <ResponseRow key={`${item.street}-${index}`} item={item} />
                )) : <EmptyState copy="No response evaluations were recorded for this hand." />}
              </div>
            </MetricSection>
          </section>

          <section style={twoColumnStyle}>
            <section style={panelStyle}>
              <div style={sectionHeaderStyle}>
                <div>
                  <div style={eyebrowStyle}>Coaching takeaways</div>
                  <h2 style={sectionTitleStyle}>What to carry forward</h2>
                </div>
              </div>
              {payload.recommendations.length ? (
                <div style={takeawayListStyle}>
                  {payload.recommendations.map((item, index) => (
                    <div key={`${item}-${index}`} style={takeawayItemStyle}>
                      <span style={takeawayNumberStyle}>{index + 1}</span>
                      <span>{item}</span>
                    </div>
                  ))}
                </div>
              ) : <EmptyState copy="No coaching takeaways were generated for this hand." />}
            </section>

            <section style={panelStyle}>
              <div style={sectionHeaderStyle}>
                <div>
                  <div style={eyebrowStyle}>Line recap</div>
                  <h2 style={sectionTitleStyle}>Street-by-street sequence</h2>
                </div>
                {payload.review?.flagged ? (
                  <Link href={replayHref} style={secondaryLinkStyle}>Open replay</Link>
                ) : null}
              </div>
              <div style={historyListStyle}>
                {payload.history.map((event, index) => (
                  <div key={`${event.street}-${event.actor}-${index}`} style={historyRowStyle}>
                    <div style={historyStreetStyle}>{event.street}</div>
                    <div style={{ minWidth: 0 }}>
                      <div style={rowTitleStyle}>{capitalize(event.actor)} {formatAction(event.action)}{event.amount ? ` ${formatAmount(event.amount)}` : ""}</div>
                      <div style={rowMetaStyle}>{event.note || (event.forced ? "Forced action" : "Action event")}</div>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          </section>
        </div>
      ) : null}
    </AppShell>
  );
}

function ScoreCard({ eyebrow, title, copy, tone }: { eyebrow: string; title: string; copy: string; tone: "coral" | "green" | "neutral" }) {
  const toneStyle = tone === "coral"
    ? { background: PALETTE.coral, borderColor: PALETTE.coral, color: PALETTE.cream }
    : tone === "green"
      ? { background: PALETTE.green, borderColor: PALETTE.green, color: "#141210" }
      : { background: "var(--surface-fill-strong)", borderColor: "var(--line)", color: PALETTE.cream };

  return (
    <div style={{ ...scoreCardStyle, ...toneStyle }}>
      <div style={scoreEyebrowStyle}>{eyebrow}</div>
      <div style={scoreValueStyle}>{title}</div>
      <div style={scoreCopyStyle}>{copy}</div>
    </div>
  );
}

function MetricSection({ eyebrow, title, score, accent, headline, children }: { eyebrow: string; title: string; score: number | null | undefined; accent: string; headline: string; children: ReactNode }) {
  return (
    <section style={panelStyle}>
      <div style={sectionHeaderStyle}>
        <div>
          <div style={{ ...eyebrowStyle, color: accent }}>{eyebrow}</div>
          <h2 style={sectionTitleStyle}>{title}</h2>
          <div style={sectionHeadlineStyle}>{headline}</div>
        </div>
        <div style={{ ...scorePillStyle, borderColor: accent, color: accent }}>{formatScore(score)}</div>
      </div>
      {children}
    </section>
  );
}

function InfoChip({ label, value }: { label: string; value: string }) {
  return (
    <div style={infoChipStyle}>
      <div style={infoChipLabelStyle}>{label}</div>
      <div style={infoChipValueStyle}>{value}</div>
    </div>
  );
}

function PruneRow({ item }: { item: DebriefPayload["prune_evaluations"][number] }) {
  const score = Number(item.overall_score ?? 0);
  const status = score >= 85 ? "Strong" : score >= 65 ? "Close" : "Review";
  const tone = score >= 85 ? successTagStyle : score >= 65 ? neutralTagStyle : dangerTagStyle;
  const posterior = item.posterior_scoring;
  const posteriorLine = posterior
    ? `Model-likely kept ${formatScore(posterior.posterior_mass_kept)} · Unlikely removed ${formatScore(posterior.low_posterior_junk_removed)}`
    : `Live combos ${item.start_live_combos} → ${item.end_live_combos}`;
  const capLine = posterior?.survival_cap != null && posterior.survival_cap < 100
    ? `Score capped at ${formatScore(posterior.survival_cap)} because the exact combo was removed.`
    : null;
  return (
    <div style={compactRowStyle}>
      <div style={{ minWidth: 0 }}>
        <div style={rowTitleStyle}>{formatStreet(item.street)} · {item.villain_action ?? "Villain action"}</div>
        <div style={rowMetaStyle}>{item.actual_bucket} · {item.actual_display_subgroup ?? item.actual_subgroup}</div>
        <div style={rowMetaStyle}>{posteriorLine}</div>
        {capLine ? <div style={rowMetaStyle}>{capLine}</div> : null}
      </div>
      <div style={rowRightStyle}>
        <span style={{ ...tagStyle, ...tone }}>{status}</span>
        <span style={scoreTextStyle}>Score {formatScore(item.overall_score)}</span>
      </div>
    </div>
  );
}

function ResponseRow({ item }: { item: DebriefPayload["response_evaluations"][number] }) {
  const score = item.score == null ? null : Number(item.score);
  const status = !item.supported ? "Unscored" : score != null && score >= 85 ? "Strong" : score != null && score >= 65 ? "Close" : "Review";
  const tone = !item.supported ? neutralTagStyle : score != null && score >= 85 ? successTagStyle : score != null && score >= 65 ? neutralTagStyle : dangerTagStyle;
  const actualBucketScore = item.bucket_level_scores?.find((bucket) => bucket.bucket === item.actual_bucket);
  const probabilityLine = actualBucketScore
    ? `Selected ${formatResponseCode(actualBucketScore.predicted)} was ${formatProbability(actualBucketScore.selected_probability)} for this bucket; top response ${formatResponseCode(actualBucketScore.best_response)} was ${formatProbability(actualBucketScore.best_probability)}.`
    : "Scored by bucket-level model probability closeness.";
  return (
    <div style={compactRowStyle}>
      <div style={{ minWidth: 0 }}>
        <div style={rowTitleStyle}>{formatStreet(item.street)} · Hero {formatAction(item.hero_action)}</div>
        <div style={rowMetaStyle}>{item.actual_bucket} · {item.actual_display_subgroup ?? item.actual_subgroup}</div>
        <div style={rowMetaStyle}>Sampled action: villain {formatResponseCode(item.actual)}</div>
        <div style={rowMetaStyle}>{probabilityLine}</div>
      </div>
      <div style={rowRightStyle}>
        <span style={{ ...tagStyle, ...tone }}>{status}</span>
        <span style={scoreTextStyle}>Score {formatScore(item.score)}</span>
      </div>
    </div>
  );
}

function EmptyState({ copy }: { copy: string }) {
  return <div style={emptyStyle}>{copy}</div>;
}

function summarizePruning(items: DebriefPayload["prune_evaluations"]) {
  if (!items.length) return { headline: "No Range Score yet.", detail: "No prune evaluations were recorded for this hand." };
  const scored = items.filter((item) => item.overall_score != null);
  const posteriorItems = items.filter((item) => item.posterior_scoring?.posterior_mass_kept != null);
  const avgPosterior = posteriorItems.length
    ? posteriorItems.reduce((sum, item) => sum + Number(item.posterior_scoring?.posterior_mass_kept ?? 0), 0) / posteriorItems.length
    : null;
  const removedExact = items.filter((item) => !item.combo_alive).length;
  return {
    headline: `${scored.length} posterior range read${scored.length === 1 ? "" : "s"} scored.`,
    detail: avgPosterior == null
      ? "Ranging is scored by how well your remaining range matches the model-likely post-action range."
      : removedExact
        ? `You kept about ${Math.round(avgPosterior)}% of model-likely posterior range on average. Exact-combo survival is tracked, but it is no longer the whole score.`
        : `You kept about ${Math.round(avgPosterior)}% of model-likely posterior range on average.`,
  };
}

function formatResponseCode(value: string | null | undefined): string {
  if (!value) return "—";
  if (value === "P") return "X";
  if (value === "A") return "B";
  return value;
}

function summarizeResponses(items: DebriefPayload["response_evaluations"]) {
  const scored = items.filter((item) => item.supported && item.score != null);
  if (!scored.length) return { headline: "No Action Score yet.", detail: "No scored response nodes were recorded for this hand." };
  const avgScore = scored.reduce((sum, item) => sum + Number(item.score ?? 0), 0) / scored.length;
  return {
    headline: `${scored.length} bucket reaction read${scored.length === 1 ? "" : "s"} scored.`,
    detail: `Average bucket-response closeness: ${Math.round(avgScore)}. Scores compare your selection to each bucket's highest-probability model response.`,
  };
}

function formatScore(value: number | null | undefined) {
  return value == null ? "—" : `${Math.round(value)}`;
}

function formatProbability(value: number | null | undefined) {
  if (value == null) return "—";
  const percent = value <= 1 ? value * 100 : value;
  return `${Math.round(percent)}%`;
}

function formatStreet(value: string) {
  return capitalize(value);
}

function formatAction(value: string) {
  return value.replaceAll("_", " ");
}

function formatAmount(value: number) {
  return `${Number(value.toFixed(2)).toString()}bb`;
}

function formatDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

function capitalize(value: string) {
  if (!value) return value;
  return value.slice(0, 1).toUpperCase() + value.slice(1);
}

const pageStackStyle: CSSProperties = { display: "grid", gap: 28 };
const summaryGridStyle: CSSProperties = { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 220px), 1fr))", gap: 16 };
const twoColumnStyle: CSSProperties = { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 420px), 1fr))", gap: 28, alignItems: "start" };
const panelStyle: CSSProperties = { borderTop: "1px solid var(--line-soft)", paddingTop: 18 };
const truthPanelStyle: CSSProperties = { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 320px), 1fr))", gap: 22, alignItems: "center", borderTop: "1px solid var(--line-soft)", paddingTop: 18 };
const truthGridStyle: CSSProperties = { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 12 };
const truthHeadlineStyle: CSSProperties = { marginTop: 10, fontSize: 30, lineHeight: 1.08, fontWeight: 900, letterSpacing: "-0.04em", color: PALETTE.cream };
const truthMetaStyle: CSSProperties = { marginTop: 8, color: PALETTE.muted, fontSize: 14 };
const reviewPanelStyle: CSSProperties = { borderTop: "1px solid var(--line-soft)", paddingTop: 18, display: "grid", gap: 14 };
const reviewGridStyle: CSSProperties = { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 280px), 1fr))", gap: 14 };
const reviewFieldStyle: CSSProperties = { display: "grid", gap: 8 };
const reviewLabelStyle: CSSProperties = { color: PALETTE.soft, fontSize: 12, textTransform: "uppercase", letterSpacing: 1.05, fontWeight: 900 };
const reviewTextAreaStyle: CSSProperties = { width: "100%", minHeight: 118, resize: "vertical", borderRadius: 14, border: "1px solid var(--line)", background: "var(--surface-fill-strong)", color: PALETTE.cream, padding: "12px 14px", font: "inherit", lineHeight: 1.45 };
const reviewFooterStyle: CSSProperties = { display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center", flexWrap: "wrap" };
const reviewActionsStyle: CSSProperties = { display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" };
const sectionHeaderStyle: CSSProperties = { display: "flex", justifyContent: "space-between", gap: 16, alignItems: "flex-start", marginBottom: 16 };
const eyebrowStyle: CSSProperties = { color: PALETTE.coral, fontSize: 12, textTransform: "uppercase", letterSpacing: 1.3, fontWeight: 900 };
const sectionTitleStyle: CSSProperties = { margin: 0, fontSize: 25, lineHeight: 1.08, letterSpacing: "-0.035em", color: PALETTE.cream };
const sectionHeadlineStyle: CSSProperties = { marginTop: 8, color: PALETTE.muted, lineHeight: 1.55, fontSize: 14 };
const scoreCardStyle: CSSProperties = { minHeight: 148, borderRadius: 20, border: "1px solid var(--line)", padding: 18, display: "flex", flexDirection: "column", justifyContent: "space-between" };
const scoreEyebrowStyle: CSSProperties = { fontSize: 11, textTransform: "uppercase", letterSpacing: 1.15, fontWeight: 900, opacity: 0.9 };
const scoreValueStyle: CSSProperties = { marginTop: 12, fontSize: 36, lineHeight: 1, fontWeight: 950, letterSpacing: "-0.05em" };
const scoreCopyStyle: CSSProperties = { marginTop: 12, fontSize: 13, lineHeight: 1.45, opacity: 0.84 };
const scorePillStyle: CSSProperties = { minWidth: 64, textAlign: "center", padding: "9px 12px", borderRadius: 999, border: "1px solid var(--line)", fontSize: 20, fontWeight: 950 };
const infoChipStyle: CSSProperties = { padding: "14px 16px", borderRadius: 18, border: "1px solid var(--line)", background: "var(--surface-fill-strong)" };
const infoChipLabelStyle: CSSProperties = { color: PALETTE.soft, fontSize: 11, textTransform: "uppercase", letterSpacing: 1.05, fontWeight: 900 };
const infoChipValueStyle: CSSProperties = { marginTop: 8, color: PALETTE.cream, fontSize: 17, fontWeight: 850, lineHeight: 1.25 };
const compactListStyle: CSSProperties = { display: "grid", gap: 12 };
const compactRowStyle: CSSProperties = { display: "grid", gridTemplateColumns: "minmax(0, 1fr) auto", gap: 16, alignItems: "center", padding: "15px 16px", borderRadius: 18, border: "1px solid var(--line)", background: "var(--surface-fill-strong)" };
const rowTitleStyle: CSSProperties = { fontWeight: 850, fontSize: 15, color: PALETTE.cream, lineHeight: 1.3, textTransform: "capitalize" };
const rowMetaStyle: CSSProperties = { color: PALETTE.soft, fontSize: 13, marginTop: 4, lineHeight: 1.45 };
const rowRightStyle: CSSProperties = { display: "grid", gap: 8, justifyItems: "end", textAlign: "right" };
const tagStyle: CSSProperties = { display: "inline-flex", alignItems: "center", justifyContent: "center", minHeight: 30, padding: "0 11px", borderRadius: 999, fontSize: 11, fontWeight: 900, textTransform: "uppercase", letterSpacing: 0.5 };
const successTagStyle: CSSProperties = { background: PALETTE.green, border: `1px solid ${PALETTE.green}`, color: "#141210" };
const dangerTagStyle: CSSProperties = { background: PALETTE.coral, border: `1px solid ${PALETTE.coral}`, color: PALETTE.cream };
const neutralTagStyle: CSSProperties = { background: "rgba(240,235,224,0.07)", border: "1px solid var(--line)", color: PALETTE.cream };
const scoreTextStyle: CSSProperties = { color: PALETTE.muted, fontSize: 12, fontWeight: 800 };
const takeawayListStyle: CSSProperties = { display: "grid", gap: 12 };
const takeawayItemStyle: CSSProperties = { display: "grid", gridTemplateColumns: "34px minmax(0, 1fr)", gap: 12, alignItems: "start", padding: "14px 16px", borderRadius: 18, border: "1px solid var(--line)", background: "var(--surface-fill-strong)", color: PALETTE.muted, lineHeight: 1.55 };
const takeawayNumberStyle: CSSProperties = { width: 28, height: 28, borderRadius: 999, display: "inline-flex", alignItems: "center", justifyContent: "center", background: PALETTE.coral, color: PALETTE.cream, fontWeight: 900, fontSize: 12 };
const historyListStyle: CSSProperties = { display: "grid", gap: 10 };
const historyRowStyle: CSSProperties = { display: "grid", gridTemplateColumns: "76px minmax(0, 1fr)", gap: 12, padding: "13px 0", borderTop: "1px solid var(--line-soft)" };
const historyStreetStyle: CSSProperties = { color: PALETTE.coral, fontSize: 12, fontWeight: 900, textTransform: "uppercase", letterSpacing: 1 };
const secondaryLinkStyle: CSSProperties = { padding: "10px 14px", borderRadius: 999, border: "1px solid var(--line)", background: "var(--surface-fill-strong)", color: PALETTE.cream, textDecoration: "none", fontWeight: 800, fontSize: 14, whiteSpace: "nowrap" };
const secondaryButtonStyle: CSSProperties = { padding: "10px 14px", borderRadius: 999, border: "1px solid var(--line)", background: "var(--surface-fill-strong)", color: PALETTE.cream, fontWeight: 800, fontSize: 14, cursor: "pointer" };
const primaryButtonStyle: CSSProperties = { padding: "10px 14px", borderRadius: 999, border: `1px solid ${PALETTE.coral}`, background: PALETTE.coral, color: PALETTE.cream, fontWeight: 850, fontSize: 14, cursor: "pointer" };
const errorStyle: CSSProperties = { color: "var(--accent)", fontWeight: 700 };
const emptyStyle: CSSProperties = { color: PALETTE.soft, fontSize: 14, lineHeight: 1.6 };

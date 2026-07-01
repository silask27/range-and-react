"use client";

import { useEffect, useMemo, useState, type CSSProperties } from "react";
import Link from "next/link";
import AppShell from "../../components/app/AppShell";
import TrendChart from "../../components/app/TrendChart";
import { API_BASE, apiFetch } from "../../lib/api";
import { useRequireAuth } from "../../lib/hooks/useRequireAuth";

type Option = { id: string; display_name: string };

type ReviewState = {
  flagged: boolean;
  sent_to_coaches: boolean;
  status: string;
  flagged_at: string | null;
  sent_at: string | null;
  coach_recipient_user_ids: string[];
  organization_ids: string[];
};

type ResultEntry = {
  hand_id: string;
  owner_user_id?: string | null;
  session_id: string;
  scenario_id: string | null;
  scenario_display_name: string | null;
  villain_profile_id: string | null;
  villain_display_name: string | null;
  street: string | null;
  position: string;
  timer_seconds: number | null;
  timer_label: string;
  ranging_score: number | null;
  response_score: number | null;
  overall_score: number | null;
  completed_at: string | null;
  streets_played: string[];
  street_scores: Array<{ street: string; ranging_score: number | null; response_score: number | null }>;
  review?: ReviewState;
};

type ResultsPayload = {
  summary: {
    completed_hands: number;
    ranging_score: number | null;
    response_score: number | null;
    overall_score: number | null;
  };
  meta?: {
    limit: number;
    offset: number;
    returned: number;
    total_completed: number;
    has_more: boolean;
  };
  filter_options: {
    scenarios: Option[];
    villains: Option[];
    positions: Option[];
    timers: Option[];
    streets: Option[];
  };
  completed_results: ResultEntry[];
  recent_results: ResultEntry[];
};

type BreakdownDimension = "scenario" | "villain" | "street" | "position" | "timer";
type MetricKey = "ranging" | "response";

type Filters = {
  scenario: string;
  villain: string;
  street: string;
  position: string;
  timer: string;
};

type InsightCardData = {
  key: string;
  title: string;
  tone: "coral" | "green";
  focus: string;
  detail: string;
};

const EMPTY_FILTERS: Filters = {
  scenario: "all",
  villain: "all",
  street: "all",
  position: "all",
  timer: "all",
};

const BREAKDOWN_OPTIONS: Array<{ id: BreakdownDimension; label: string }> = [
  { id: "villain", label: "Villain" },
  { id: "scenario", label: "Scenario" },
  { id: "street", label: "Street" },
  { id: "position", label: "IP / OOP" },
  { id: "timer", label: "Timer" },
];

const PALETTE = {
  cream: "#F0EBE0",
  coral: "#E76F51",
  green: "#6A9E72",
};

const MEMBER_PAGE_SIZE = 1000;
const MEMBER_OPTION_CAP = 2500;
const RESULTS_OVERVIEW_LIMIT = 250;
const MIN_DRIVER_SAMPLES = 3;
const MIN_DRIVER_DELTA = 3;
const MIN_DRIVER_SAMPLE_SHARE = 0.15;
const MAX_DRIVER_SAMPLE_SHARE = 0.85;

async function loadMemberOptions(): Promise<Option[]> {
  const options: Option[] = [];
  let offset = 0;
  let total = Number.POSITIVE_INFINITY;
  while (offset < total && options.length < MEMBER_OPTION_CAP) {
    const res = await apiFetch(`${API_BASE}/admin/users?limit=${MEMBER_PAGE_SIZE}&offset=${offset}&role=member`, { cache: "no-store" });
    const data = await res.json();
    if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Unable to load members.");
    const rows = ((data as { users?: Array<{ user_id: string; display_name: string | null; email: string; role: string }> }).users ?? [])
      .filter((entry) => entry.role === "member")
      .map((entry) => ({ id: entry.user_id, display_name: entry.display_name || entry.email }));
    options.push(...rows);
    const meta = (data as { meta?: { total?: number; limit?: number } }).meta;
    total = typeof meta?.total === "number" ? meta.total : options.length;
    const step = typeof meta?.limit === "number" ? meta.limit : MEMBER_PAGE_SIZE;
    if (rows.length === 0 || step <= 0) break;
    offset += step;
  }
  return options.slice(0, MEMBER_OPTION_CAP);
}

export default function ResultsPage() {
  const { user, isAuthLoading, authError } = useRequireAuth();
  const [payload, setPayload] = useState<ResultsPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [breakdown, setBreakdown] = useState<BreakdownDimension>("villain");
  const [memberOptions, setMemberOptions] = useState<Option[]>([]);
  const [membersLoaded, setMembersLoaded] = useState(false);
  const [reviewMessage, setReviewMessage] = useState<string | null>(null);
  const [flagBusyHandId, setFlagBusyHandId] = useState<string | null>(null);
  const [sendBusy, setSendBusy] = useState(false);
  const [csvBusy, setCsvBusy] = useState(false);
  const [selectedMemberId, setSelectedMemberId] = useState(() => {
    if (typeof window === "undefined") return "";
    return new URLSearchParams(window.location.search).get("member_id") ?? "";
  });

  const isCoachResultsView = user?.role === "owner" || user?.role === "admin" || user?.role === "coach";

  useEffect(() => {
    if (!user) return;
    if (!isCoachResultsView) {
      setMembersLoaded(true);
      return;
    }

    let cancelled = false;
    async function loadMembers() {
      setMembersLoaded(false);
      try {
        const options = await loadMemberOptions();
        if (cancelled) return;
        setMemberOptions(options);
        setSelectedMemberId((current) => current || options[0]?.id || "");
        setMembersLoaded(true);
      } catch (err) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Unable to load members.");
        setMembersLoaded(true);
      }
    }

    void loadMembers();
    return () => {
      cancelled = true;
    };
  }, [user, isCoachResultsView]);

  useEffect(() => {
    if (!user) return;
    if (isCoachResultsView && !membersLoaded) return;
    if (isCoachResultsView && memberOptions.length > 0 && !selectedMemberId) return;
    if (isCoachResultsView && memberOptions.length === 0) {
      setPayload(null);
      setIsLoading(false);
      return;
    }

    let cancelled = false;
    void loadResults({ cancelled: () => cancelled });
    return () => {
      cancelled = true;
    };
  }, [user, selectedMemberId, isCoachResultsView, membersLoaded, memberOptions.length]);

  async function loadResults({ cancelled }: { cancelled?: () => boolean } = {}) {
    setIsLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({
        limit: String(RESULTS_OVERVIEW_LIMIT),
        offset: "0",
      });
      if (selectedMemberId) params.set("user_id", selectedMemberId);
      const query = `?${params.toString()}`;
      const res = await apiFetch(`${API_BASE}/results/overview${query}`, { cache: "no-store" });
      const data = await res.json();
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Unable to load results.");
      if (!cancelled?.()) setPayload(data as ResultsPayload);
    } catch (err) {
      if (!cancelled?.()) setError(err instanceof Error ? err.message : "Unable to load results.");
    } finally {
      if (!cancelled?.()) setIsLoading(false);
    }
  }

  function handleMemberChange(memberId: string) {
    setSelectedMemberId(memberId);
    setFilters(EMPTY_FILTERS);
    setBreakdown("villain");
    if (typeof window !== "undefined") {
      const url = new URL(window.location.href);
      if (memberId) url.searchParams.set("member_id", memberId);
      else url.searchParams.delete("member_id");
      window.history.replaceState(null, "", `${url.pathname}${url.search}`);
    }
  }

  function applyReviewState(handId: string, review: ReviewState) {
    const patchRows = (rows: ResultEntry[]) => rows.map((row) => row.hand_id === handId ? { ...row, review } : row);
    setPayload((current) => current ? {
      ...current,
      completed_results: patchRows(current.completed_results),
      recent_results: patchRows(current.recent_results),
    } : current);
  }

  async function toggleFlag(result: ResultEntry) {
    const nextFlagged = !result.review?.flagged;
    setFlagBusyHandId(result.hand_id);
    setReviewMessage(null);
    try {
      const res = await apiFetch(`${API_BASE}/results/hand/${encodeURIComponent(result.hand_id)}/flag`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ flagged: nextFlagged }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Unable to update review flag.");
      applyReviewState(result.hand_id, (data as { review: ReviewState }).review);
    } catch (err) {
      setReviewMessage(err instanceof Error ? err.message : "Unable to update review flag.");
    } finally {
      setFlagBusyHandId(null);
    }
  }

  async function sendFlaggedToCoaches() {
    setSendBusy(true);
    setReviewMessage(null);
    try {
      const res = await apiFetch(`${API_BASE}/results/review/send`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Unable to send flagged hands.");
      const count = Number((data as { sent_count?: number }).sent_count ?? 0);
      setReviewMessage(count ? `Sent ${count} flagged hand${count === 1 ? "" : "s"} to your coach queue.` : "No flagged hands were waiting to send.");
      await loadResults();
    } catch (err) {
      setReviewMessage(err instanceof Error ? err.message : "Unable to send flagged hands.");
    } finally {
      setSendBusy(false);
    }
  }

  async function downloadResultsCsv() {
    setCsvBusy(true);
    setReviewMessage(null);
    try {
      const params = new URLSearchParams();
      if (selectedMemberId) params.set("user_id", selectedMemberId);
      const query = params.toString();
      const res = await apiFetch(`${API_BASE}/results/member-summary.csv${query ? `?${query}` : ""}`, { cache: "no-store" });
      const blob = await res.blob();
      if (!res.ok) throw new Error("Unable to download member summary.");
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      const disposition = res.headers.get("Content-Disposition") || "";
      const filenameMatch = disposition.match(/filename="?([^";]+)"?/i);
      link.download = filenameMatch?.[1] || "member-summary.csv";
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
      setReviewMessage("Member summary CSV downloaded.");
    } catch (err) {
      setReviewMessage(err instanceof Error ? err.message : "Unable to download member summary.");
    } finally {
      setCsvBusy(false);
    }
  }

  const filteredResults = useMemo(() => {
    if (!payload) return [];
    return payload.completed_results.filter((row) => {
      if (filters.scenario !== "all" && row.scenario_id !== filters.scenario) return false;
      if (filters.villain !== "all" && row.villain_profile_id !== filters.villain) return false;
      if (filters.position !== "all" && row.position !== filters.position) return false;
      if (filters.timer !== "all" && row.timer_label !== filters.timer) return false;
      if (filters.street !== "all" && !row.streets_played.includes(filters.street)) return false;
      return true;
    });
  }, [payload, filters]);

  const hasActiveFilters = filters.scenario !== "all" || filters.villain !== "all" || filters.street !== "all" || filters.position !== "all" || filters.timer !== "all";
  const filteredSummary = useMemo(() => {
    if (!hasActiveFilters && payload) {
      return {
        hands: payload.summary.completed_hands,
        ranging: payload.summary.ranging_score,
        response: payload.summary.response_score,
      };
    }
    return {
      hands: filteredResults.length,
      ranging: average(filteredResults.map((row) => metricScoreForResult(row, "ranging", filters.street))),
      response: average(filteredResults.map((row) => metricScoreForResult(row, "response", filters.street))),
    };
  }, [filteredResults, filters.street, hasActiveFilters, payload]);

  const trendPoints = useMemo(() => {
    const ordered = [...filteredResults]
      .sort((a, b) => (a.completed_at || "").localeCompare(b.completed_at || ""))
      .slice(-10);
    const seenRanges: number[] = [];
    const seenResponses: number[] = [];
    return ordered.map((row, index) => {
      const rangingScore = metricScoreForResult(row, "ranging", filters.street);
      const responseScore = metricScoreForResult(row, "response", filters.street);
      if (rangingScore != null) seenRanges.push(rangingScore);
      if (responseScore != null) seenResponses.push(responseScore);
      return {
        label: row.completed_at ? compactTrendLabel(row.completed_at, index) : `Rep ${index + 1}`,
        ranging: average(seenRanges),
        response: average(seenResponses),
      };
    });
  }, [filteredResults, filters.street]);

  const breakdownRows = useMemo(() => buildBreakdownRows(filteredResults, breakdown, filters.street), [filteredResults, breakdown, filters.street]);
  const driverInsights = useMemo(() => buildDriverInsights(filteredResults, filters), [filteredResults, filters]);
  const debriefRows = filteredResults.slice().sort((a, b) => (b.completed_at || "").localeCompare(a.completed_at || "")).slice(0, 5);
  const canSendFlagged = !isCoachResultsView && Boolean(payload?.completed_results.some((row) => row.review?.flagged && !row.review.sent_to_coaches));

  const headerStats = (
    <>
      <HeaderStat label="Range Score" value={formatScore(filteredSummary.ranging)} tone="green" />
      <HeaderStat label="Action Score" value={formatScore(filteredSummary.response)} tone="coral" />
      <HeaderStat label="Finished hands" value={filteredSummary.hands} tone="neutral" />
    </>
  );

  return (
    <AppShell title="Results" subtitle="Full-history score totals with fast recent-hand exploration for filters, trends, and debriefs." headerContent={headerStats}>
      {isAuthLoading || isLoading ? <div style={panelStyle}>Loading results…</div> : null}
      {authError ? <div style={errorStyle}>{authError}</div> : null}
      {error ? <div style={errorStyle}>{error}</div> : null}
      {reviewMessage ? <div style={noticeStyle}>{reviewMessage}</div> : null}
      {payload?.meta?.has_more ? (
        <div style={noticeStyle}>Loaded the latest {payload.meta.returned} of {payload.meta.total_completed} finished hands for fast filtering and breakdowns. Headline scores use the full history.</div>
      ) : null}
      {payload ? (
        <>
          <section style={panelStyle}>
            <div style={barHeaderStyle}>
              <div>
                <div style={eyebrowStyle}>Filters</div>
                <h2 style={sectionTitleStyle}>Filter recent hands, then choose one breakdown</h2>
              </div>
              <div style={filterActionsStyle}>
                <button type="button" onClick={downloadResultsCsv} disabled={csvBusy} style={primaryButtonStyle}>
                  {csvBusy ? "Downloading…" : "Member summary CSV"}
                </button>
                <button type="button" onClick={() => { setFilters(EMPTY_FILTERS); setBreakdown("villain"); }} style={ghostButtonStyle}>Clear</button>
              </div>
            </div>
            {isCoachResultsView ? (
              <div style={memberFilterWrapStyle}>
                {memberOptions.length ? (
                  <SelectField label="Member" value={selectedMemberId} onChange={handleMemberChange} options={memberOptions} />
                ) : (
                  <EmptyState copy="No organization members are available to review yet." />
                )}
              </div>
            ) : null}
            <div style={filterBarStyle}>
              <SelectField label="Breakdown" value={breakdown} onChange={(value) => setBreakdown(value as BreakdownDimension)} options={BREAKDOWN_OPTIONS.map((option) => ({ id: option.id, display_name: option.label }))} compact />
              <SelectField label="Scenario" value={filters.scenario} onChange={(value) => setFilters((current) => ({ ...current, scenario: value }))} options={[{ id: "all", display_name: "All scenarios" }, ...payload.filter_options.scenarios]} compact />
              <SelectField label="Villain" value={filters.villain} onChange={(value) => setFilters((current) => ({ ...current, villain: value }))} options={[{ id: "all", display_name: "All villains" }, ...payload.filter_options.villains]} compact />
              <SelectField label="Street" value={filters.street} onChange={(value) => setFilters((current) => ({ ...current, street: value }))} options={[{ id: "all", display_name: "All streets" }, ...payload.filter_options.streets]} compact />
              <SelectField label="IP / OOP" value={filters.position} onChange={(value) => setFilters((current) => ({ ...current, position: value }))} options={[{ id: "all", display_name: "All positions" }, ...payload.filter_options.positions]} compact />
              <SelectField label="Timer" value={filters.timer} onChange={(value) => setFilters((current) => ({ ...current, timer: value }))} options={[{ id: "all", display_name: "All timer settings" }, ...payload.filter_options.timers]} compact />
            </div>
          </section>

          <section style={topGridStyle}>
            <section style={panelStyle}>
              <div style={sectionHeaderStyle}>
                <div>
                  <div style={eyebrowStyle}>Trend</div>
                  <h2 style={sectionTitleStyle}>Recent metric progression</h2>
                </div>
              </div>
              {trendPoints.length ? <TrendChart points={trendPoints} /> : <EmptyState copy="Finish more hands to unlock your trend line." />}
            </section>

            <section style={panelStyle}>
              <div style={sectionHeaderStyle}>
                <div>
                  <div style={eyebrowStyle}>Breakdown</div>
                  <h2 style={sectionTitleStyle}>Recent scores by {labelForBreakdown(breakdown).toLowerCase()}</h2>
                </div>
              </div>
              {breakdownRows.length ? (
                <div style={tableStackStyle}>
                  {breakdownRows.map((row) => (
                    <div key={row.key} style={breakdownRowStyle}>
                      <div style={{ minWidth: 0 }}>
                        <div style={rowTitleStyle}>{row.label}</div>
                        <div style={rowMetaStyle}>{row.hands} samples</div>
                      </div>
                      <div style={railColumnStyle}>
                        <ScoreRail label="Range" value={row.ranging_score} color={PALETTE.green} />
                        <ScoreRail label="Action" value={row.response_score} color={PALETTE.coral} />
                      </div>
                    </div>
                  ))}
                </div>
              ) : <EmptyState copy="No finished hands match the current filters." />}
            </section>
          </section>

          <section style={panelStyle}>
            <div style={sectionHeaderStyle}>
              <div>
                <div style={eyebrowStyle}>Insights</div>
                <h2 style={sectionTitleStyle}>Recent score drivers</h2>
              </div>
            </div>
            <div style={insightGridStyle}>
              {driverInsights.map((insight) => <InsightCard key={insight.key} data={insight} />)}
            </div>
          </section>

          <section style={panelStyle}>
            <div style={sectionHeaderStyle}>
              <div>
                <div style={eyebrowStyle}>Debriefs</div>
                <h2 style={sectionTitleStyle}>Most recent finished hands</h2>
              </div>
              {canSendFlagged ? (
                <button type="button" onClick={sendFlaggedToCoaches} disabled={sendBusy} style={primaryButtonStyle}>
                  {sendBusy ? "Sending…" : "Send flagged to coach"}
                </button>
              ) : null}
            </div>
            {debriefRows.length ? (
              <div style={scrollTableStackStyle}>
                {debriefRows.map((result) => (
                  <div key={result.hand_id} style={rowStyle}>
                    <div style={{ minWidth: 0 }}>
                      <div style={rowTitleStyle}>{result.scenario_display_name || "Scenario"} · {result.villain_display_name || "Villain"}</div>
                      <div style={rowMetaStyle}>{compactDateTime(result.completed_at)} · {result.position} · {result.timer_label}</div>
                      <div style={rowHelperStyle}>
                        Range Score {formatScore(result.ranging_score)} · {result.response_score == null ? "Action Score unscored for this hand path" : `Action Score ${formatScore(result.response_score)}`}
                      </div>
                      {result.review?.flagged ? (
                        <div style={rowHelperStyle}>{result.review.sent_to_coaches ? "Flagged and sent to coach queue" : "Flagged for review"}</div>
                      ) : null}
                    </div>
                    <div style={rowActionsStyle}>
                      {!isCoachResultsView || result.owner_user_id === user?.user_id ? (
                        <button
                          type="button"
                          aria-label={result.review?.flagged ? "Remove review flag" : "Flag hand for review"}
                          title={result.review?.flagged ? "Remove review flag" : "Flag hand for review"}
                          onClick={() => toggleFlag(result)}
                          disabled={flagBusyHandId === result.hand_id}
                          style={{ ...iconButtonStyle, ...(result.review?.flagged ? activeIconButtonStyle : null) }}
                        >
                          {result.review?.flagged ? "★" : "☆"}
                        </button>
                      ) : null}
                      {result.review?.flagged ? (
                        <Link href={replayHref(result)} style={secondaryLinkStyle}>Replay</Link>
                      ) : null}
                      <Link href={`/results/hand/${encodeURIComponent(result.hand_id)}`} style={secondaryLinkStyle}>Open debrief</Link>
                    </div>
                  </div>
                ))}
              </div>
            ) : <EmptyState copy="Complete a postflop hand to unlock debrief history." />}
          </section>
        </>
      ) : null}
    </AppShell>
  );
}

function buildBreakdownRows(results: ResultEntry[], dimension: BreakdownDimension, streetFilter: string) {
  const groups = new Map<string, { label: string; hands: number; ranging: number[]; response: number[] }>();
  if (dimension === "street") {
    for (const result of results) {
      for (const streetRow of result.street_scores) {
        if (streetFilter !== "all" && streetRow.street !== streetFilter) continue;
        const current = groups.get(streetRow.street) || { label: capitalize(streetRow.street), hands: 0, ranging: [], response: [] };
        if (streetRow.ranging_score != null) current.ranging.push(streetRow.ranging_score);
        if (streetRow.response_score != null) current.response.push(streetRow.response_score);
        current.hands += 1;
        groups.set(streetRow.street, current);
      }
    }
    return Array.from(groups.entries()).map(([key, value]) => ({ key, label: value.label, hands: value.hands, ranging_score: average(value.ranging), response_score: average(value.response) })).sort((a, b) => streetOrder(a.key) - streetOrder(b.key));
  }

  for (const result of results) {
    const key = dimension === "scenario"
      ? (result.scenario_id || "unknown")
      : dimension === "villain"
        ? (result.villain_profile_id || "unknown")
        : dimension === "position"
          ? result.position
          : result.timer_label;
    const label = dimension === "scenario"
      ? (result.scenario_display_name || "Unknown")
      : dimension === "villain"
        ? (result.villain_display_name || "Unknown")
        : dimension === "position"
          ? result.position
          : result.timer_label;
    const current = groups.get(key) || { label, hands: 0, ranging: [], response: [] };
    const rangingScore = metricScoreForResult(result, "ranging", streetFilter);
    const responseScore = metricScoreForResult(result, "response", streetFilter);
    if (rangingScore != null) current.ranging.push(rangingScore);
    if (responseScore != null) current.response.push(responseScore);
    current.hands += 1;
    groups.set(key, current);
  }

  return Array.from(groups.entries()).map(([key, value]) => ({ key, label: value.label, hands: value.hands, ranging_score: average(value.ranging), response_score: average(value.response) })).sort((a, b) => b.hands - a.hands || a.label.localeCompare(b.label));
}

function buildDriverInsights(results: ResultEntry[], filters: Filters): InsightCardData[] {
  return [
    bestDriverInsight(results, "ranging", "low", filters),
    bestDriverInsight(results, "ranging", "high", filters),
    bestDriverInsight(results, "response", "low", filters),
    bestDriverInsight(results, "response", "high", filters),
  ];
}

function bestDriverInsight(results: ResultEntry[], metric: MetricKey, direction: "low" | "high", filters: Filters): InsightCardData {
  const titlePrefix = metricLabel(metric);
  const tone = metricTone(metric);
  if (!results.length) {
    return {
      key: `${metric}-${direction}`,
      title: `${titlePrefix} ${direction === "low" ? "struggle" : "strength"}`,
      tone,
      focus: "Need more finished hands",
      detail: "Complete more finished hands to unlock a reliable insight.",
    };
  }
  const scoreValues = results.map((row) => metricScoreForResult(row, metric, filters.street));
  const scoreableSampleCount = scoreValues.filter((value): value is number => value != null).length;
  const baseline = average(scoreValues);
  if (baseline == null) {
    return {
      key: `${metric}-${direction}`,
      title: `${titlePrefix} ${direction === "low" ? "struggle" : "strength"}`,
      tone,
      focus: "No scoreable sample yet",
      detail: "The current filtered sample does not contain enough scoreable nodes yet.",
    };
  }
  if (scoreableSampleCount < MIN_DRIVER_SAMPLES) {
    return {
      key: `${metric}-${direction}`,
      title: `${titlePrefix} ${direction === "low" ? "struggle" : "strength"}`,
      tone,
      focus: "Need more matching hands",
      detail: `Only ${scoreableSampleCount} matching scored hand${scoreableSampleCount === 1 ? "" : "s"} are available. Add more reps before calling a driver reliable.`,
    };
  }

  const candidates: Array<{ focus: string; delta: number; samples: number }> = [];
  const dimensions: BreakdownDimension[] = ["villain", "scenario", "position", "timer", "street"].filter((dimension) => {
    if (dimension === "villain" && filters.villain !== "all") return false;
    if (dimension === "scenario" && filters.scenario !== "all") return false;
    if (dimension === "position" && filters.position !== "all") return false;
    if (dimension === "timer" && filters.timer !== "all") return false;
    if (dimension === "street" && filters.street !== "all") return false;
    return true;
  }) as BreakdownDimension[];
  const minSamples = Math.max(MIN_DRIVER_SAMPLES, Math.ceil(scoreableSampleCount * MIN_DRIVER_SAMPLE_SHARE));
  for (const dimension of dimensions) {
    for (const row of buildBreakdownRows(results, dimension, filters.street)) {
      const score = metric === "ranging" ? row.ranging_score : row.response_score;
      if (score == null || row.hands < minSamples) continue;
      if (row.hands / scoreableSampleCount > MAX_DRIVER_SAMPLE_SHARE) continue;
      const focusLabel = `${labelForBreakdown(dimension)}: ${row.label}`;
      const delta = round(score - baseline);
      if (Math.abs(delta) < MIN_DRIVER_DELTA) continue;
      candidates.push({ focus: focusLabel, delta, samples: row.hands });
    }
  }

  const filtered = candidates.filter((item) => direction === "low" ? item.delta < 0 : item.delta > 0);
  if (!filtered.length) {
    return {
      key: `${metric}-${direction}`,
      title: `${titlePrefix} ${direction === "low" ? "struggle" : "strength"}`,
      tone,
      focus: direction === "low" ? "No clear weakness" : "No clear strength",
      detail: direction === "low" ? "No filtered group has enough sample and score gap to call a reliable drag yet." : "No filtered group has enough sample and score gap to call a reliable lift yet.",
    };
  }
  filtered.sort((a, b) => direction === "low" ? a.delta - b.delta : b.delta - a.delta);
  const best = filtered[0];
  const points = Math.abs(best.delta).toFixed(1);
  return {
    key: `${metric}-${direction}`,
    title: `${titlePrefix} ${direction === "low" ? "struggle" : "strength"}`,
    tone,
    focus: best.focus,
    detail: direction === "low"
      ? `Within the current filters, this is lowering the score by about ${points} points across ${best.samples} matching hands.`
      : `Within the current filters, this is lifting the score by about ${points} points across ${best.samples} matching hands.`,
  };
}

function metricScoreForResult(result: ResultEntry, metric: MetricKey, streetFilter: string) {
  if (streetFilter !== "all") {
    const streetRow = result.street_scores.find((row) => row.street === streetFilter);
    return metric === "ranging" ? streetRow?.ranging_score ?? null : streetRow?.response_score ?? null;
  }
  return metric === "ranging" ? result.ranging_score : result.response_score;
}

function metricLabel(metric: MetricKey) {
  return metric === "ranging" ? "Range Score" : "Action Score";
}

function metricTone(metric: MetricKey): "coral" | "green" {
  return metric === "ranging" ? "green" : "coral";
}

function SelectField({ label, value, onChange, options, compact }: { label: string; value: string; onChange: (value: string) => void; options: Array<{ id: string; display_name: string }>; compact?: boolean }) {
  return (
    <label style={{ ...filterLabelStyle, ...(compact ? compactFilterLabelStyle : null) }}>
      <span style={captionStyle}>{label}</span>
      <div style={selectWrapStyle}>
        <select value={value} onChange={(event) => onChange(event.target.value)} style={selectStyle}>
          {options.map((option) => <option key={option.id} value={option.id}>{option.display_name}</option>)}
        </select>
      </div>
    </label>
  );
}

function HeaderStat({ label, value, tone, helper }: { label: string; value: string | number; tone: "coral" | "green" | "neutral"; helper?: string }) {
  const toneStyle = tone === "coral"
    ? { borderColor: PALETTE.coral, background: PALETTE.coral, color: PALETTE.cream }
    : tone === "green"
      ? { borderColor: PALETTE.green, background: PALETTE.green, color: "#141210" }
      : { borderColor: "var(--line)", background: "var(--surface-fill-strong)", color: PALETTE.cream };
  return (
    <div style={{ ...headerStatStyle, ...toneStyle }}>
      <div style={headerStatLabelStyle}>{label}</div>
      <div style={headerStatValueStyle}>{value}</div>
      {helper ? <div style={headerStatHelperStyle}>{helper}</div> : null}
    </div>
  );
}

function ScoreRail({ label, value, color }: { label: string; value: number | null; color: string }) {
  const width = `${Math.max(6, Math.min(100, Math.round(value ?? 0)))}%`;
  return (
    <div style={railWrapStyle}>
      <div style={railHeaderStyle}>
        <span>{label}</span>
        <span>{formatScore(value)}</span>
      </div>
      <div style={railTrackStyle}>
        <div style={{ ...railFillStyle, width, background: color }} />
      </div>
    </div>
  );
}

function InsightCard({ data }: { data: InsightCardData }) {
  const borderColor = data.tone === "coral" ? PALETTE.coral : PALETTE.green;
  const titleColor = data.tone === "coral" ? PALETTE.coral : PALETTE.green;
  return (
    <div style={{ ...insightCardStyle, borderColor }}>
      <div style={{ ...eyebrowStyle, color: titleColor }}>{data.title}</div>
      <div style={insightFocusStyle}>{data.focus}</div>
      <div style={insightCopyStyle}>{data.detail}</div>
    </div>
  );
}

function EmptyState({ copy }: { copy: string }) {
  return <div style={emptyStateStyle}>{copy}</div>;
}

function average(values: Array<number | null | undefined>) {
  const clean = values.filter((value): value is number => value != null);
  return clean.length ? round(clean.reduce((sum, value) => sum + value, 0) / clean.length) : null;
}

function round(value: number) { return Math.round(value * 100) / 100; }
function formatScore(value: number | null | undefined) { return value == null ? "—" : `${Math.round(value)}`; }
function compactTrendLabel(value: string, index: number) {
  const date = new Date(value);
  return `${date.toLocaleDateString(undefined, { month: "short", day: "numeric" })} #${index + 1}`;
}
function compactDateTime(value: string | null) { return value ? new Date(value).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }) : "Completed"; }
function capitalize(value: string) { return value.slice(0, 1).toUpperCase() + value.slice(1); }
function streetOrder(value: string) { return ["flop", "turn", "river"].indexOf(value); }
function labelForBreakdown(value: BreakdownDimension) {
  return value === "position" ? "IP / OOP" : value === "timer" ? "Timer" : capitalize(value);
}

function replayHref(result: ResultEntry) {
  const params = new URLSearchParams({
    hand_id: result.hand_id,
    replay: "1",
  });
  if (result.session_id) params.set("session_id", result.session_id);
  return `/screen-1?${params.toString()}`;
}

const panelStyle: CSSProperties = { borderTop: "1px solid var(--line-soft)", paddingTop: 18 };
const errorStyle: CSSProperties = { color: "var(--accent)", fontWeight: 700 };
const noticeStyle: CSSProperties = { color: PALETTE.cream, border: "1px solid var(--line)", background: "var(--surface-fill-strong)", borderRadius: 14, padding: "12px 14px", fontWeight: 700 };
const barHeaderStyle: CSSProperties = { display: "flex", justifyContent: "space-between", gap: 16, alignItems: "flex-start", marginBottom: 18 };
const filterActionsStyle: CSSProperties = { display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", justifyContent: "flex-end" };
const sectionHeaderStyle: CSSProperties = { display: "grid", gap: 8, marginBottom: 16 };
const eyebrowStyle: CSSProperties = { color: PALETTE.coral, fontSize: 12, textTransform: "uppercase", letterSpacing: 1.3, fontWeight: 900 };
const sectionTitleStyle: CSSProperties = { margin: 0, fontSize: 26, lineHeight: 1.08 };
const captionStyle: CSSProperties = { color: "var(--text-45)", fontSize: 11, textTransform: "uppercase", letterSpacing: 1.1, fontWeight: 800 };
const headerStatStyle: CSSProperties = { flex: "0 0 188px", width: "100%", maxWidth: 188, minHeight: 92, borderRadius: 18, padding: "14px 16px", border: "1px solid var(--line)", background: "rgba(20,18,16,1)", display: "flex", flexDirection: "column", justifyContent: "space-between" };
const headerStatLabelStyle: CSSProperties = { color: "inherit", opacity: 0.9, fontSize: 11, textTransform: "uppercase", letterSpacing: 1.1, fontWeight: 800 };
const headerStatValueStyle: CSSProperties = { marginTop: 6, fontSize: 28, fontWeight: 900, color: "inherit" };
const headerStatHelperStyle: CSSProperties = { marginTop: 4, opacity: 0.88, fontSize: 12, lineHeight: 1.45 };
const filterBarStyle: CSSProperties = { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 180px), 1fr))", gap: 16, alignItems: "end" };
const filterLabelStyle: CSSProperties = { display: "grid", gap: 8 };
const compactFilterLabelStyle: CSSProperties = { minWidth: 0 };
const selectWrapStyle: CSSProperties = { position: "relative" };
const selectStyle: CSSProperties = { width: "100%", padding: "11px 52px 11px 12px", borderRadius: 12, border: "1px solid var(--line)", background: "var(--surface-fill)", color: PALETTE.cream, appearance: "none", WebkitAppearance: "none", MozAppearance: "none" };
const memberFilterWrapStyle: CSSProperties = { maxWidth: 360, marginBottom: 18 };
const topGridStyle: CSSProperties = { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 420px), 1fr))", gap: 28, alignItems: "start" };
const insightGridStyle: CSSProperties = { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 240px), 1fr))", gap: 16 };
const insightCardStyle: CSSProperties = { padding: 18, borderRadius: 18, background: "var(--surface-fill)", border: "1px solid var(--line)" };
const insightFocusStyle: CSSProperties = { marginTop: 8, fontSize: 24, fontWeight: 900, color: PALETTE.cream, lineHeight: 1.12 };
const insightCopyStyle: CSSProperties = { marginTop: 8, color: "var(--text-65)", lineHeight: 1.6 };
const tableStackStyle: CSSProperties = { display: "grid", gap: 18 };
const scrollTableStackStyle: CSSProperties = { ...tableStackStyle, maxHeight: 560, overflowY: "auto", paddingRight: 6 };
const breakdownRowStyle: CSSProperties = { display: "grid", gridTemplateColumns: "minmax(0, 180px) minmax(0, 1fr)", gap: 18, alignItems: "center", paddingTop: 14, borderTop: "1px solid var(--line-soft)" };
const rowStyle: CSSProperties = { display: "flex", justifyContent: "space-between", gap: 14, alignItems: "center", padding: 16, borderRadius: 18, background: "var(--surface-fill)", border: "1px solid var(--line)" };
const rowActionsStyle: CSSProperties = { display: "flex", gap: 10, alignItems: "center", justifyContent: "flex-end", flexWrap: "wrap" };
const rowTitleStyle: CSSProperties = { fontWeight: 800, fontSize: 15, color: PALETTE.cream };
const rowMetaStyle: CSSProperties = { color: "var(--text-45)", fontSize: 13, marginTop: 4, lineHeight: 1.5 };
const rowHelperStyle: CSSProperties = { color: "var(--text-65)", fontSize: 13, lineHeight: 1.55, marginTop: 4 };
const railColumnStyle: CSSProperties = { display: "grid", gap: 10 };
const railWrapStyle: CSSProperties = { display: "grid", gap: 6 };
const railHeaderStyle: CSSProperties = { display: "flex", justifyContent: "space-between", fontSize: 12, color: "var(--text-45)", fontWeight: 800 };
const railTrackStyle: CSSProperties = { height: 10, borderRadius: 999, background: "rgba(240,235,224,0.12)", overflow: "hidden" };
const railFillStyle: CSSProperties = { height: "100%", borderRadius: 999 };
const ghostButtonStyle: CSSProperties = { padding: "10px 14px", borderRadius: 14, border: "1px solid var(--line)", background: "var(--surface-fill-strong)", color: PALETTE.cream, fontWeight: 700 };
const primaryButtonStyle: CSSProperties = { padding: "10px 14px", borderRadius: 14, border: `1px solid ${PALETTE.coral}`, background: PALETTE.coral, color: PALETTE.cream, fontWeight: 800 };
const iconButtonStyle: CSSProperties = { width: 42, height: 42, borderRadius: 14, border: "1px solid var(--line)", background: "var(--surface-fill-strong)", color: PALETTE.cream, fontWeight: 900, fontSize: 20, lineHeight: 1, display: "inline-flex", alignItems: "center", justifyContent: "center" };
const activeIconButtonStyle: CSSProperties = { borderColor: PALETTE.coral, color: PALETTE.coral };
const secondaryLinkStyle: CSSProperties = { padding: "10px 14px", borderRadius: 14, border: "1px solid var(--line)", color: PALETTE.cream, textDecoration: "none", fontWeight: 700, background: "var(--surface-fill-strong)", whiteSpace: "nowrap" };
const emptyStateStyle: CSSProperties = { color: "var(--text-65)", padding: "8px 0 4px", lineHeight: 1.6 };

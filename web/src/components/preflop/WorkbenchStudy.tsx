import React, { useState } from "react";

import type { MatrixAction } from "../../lib/preflop/types";
import { make13x13Grid } from "../../lib/preflop/handGrid";
import { HandMatrix } from "./HandMatrix";

type StudyCategoryKey = "RFI" | "ISO" | "3BET" | "SQUEEZE" | "3BET_DEFEND" | "BB_DEFEND";

type ChartDef = {
  id: string;
  label: string;
  raise_tokens: string[];
  call_tokens?: string[];
};

type DeviationGroup = {
  title: string;
  bullets: string[];
};

const ALL_HAND_TOKENS: string[] = make13x13Grid().map((c) => c.token);

function buildDefaultActions(chart: ChartDef): Record<string, MatrixAction> {
  const out: Record<string, MatrixAction> = {};
  for (const t of ALL_HAND_TOKENS) out[t] = "FOLD";

  for (const t of chart.call_tokens ?? []) out[t] = "CALL";
  for (const t of chart.raise_tokens) out[t] = "RAISE";

  return out;
}

function shortStudyScenarioTitle(chart: ChartDef): string {
  const label = chart.label ?? chart.id ?? "";
  const parts = label.split("—").map((s) => s.trim());
  const scenario = parts[0] ?? label;
  const rest = parts[1]?.trim() ?? "";

  const allowed = new Set([
    "EP",
    "MP",
    "LP",
    "UTG",
    "UTG+1",
    "UTG+2",
    "LJ",
    "HJ",
    "CO",
    "BTN",
    "SB",
    "BB",
  ]);

  const restNoParen = rest.split("(")[0].trim();

  const vsMatch = restNoParen.match(/^([A-Za-z0-9+\/]+)\s+vs\s+([A-Za-z0-9+\/]+)/i);
  if (vsMatch) {
    const hero = vsMatch[1].toUpperCase();
    const vil = vsMatch[2].toUpperCase();

    if (allowed.has(hero) && allowed.has(vil)) {
      return `${scenario} ${hero} vs ${vil}`;
    }
  }

  const paren = rest.match(/\(([^)]+)\)/)?.[1] ?? "";
  const parenVs = paren.match(/([A-Za-z0-9+\/]+)\s+vs\s+([A-Za-z0-9+\/]+)/i);
  if (parenVs) {
    const hero = parenVs[1].toUpperCase();
    const vil = parenVs[2].toUpperCase();

    if (allowed.has(hero) && allowed.has(vil)) {
      return `${scenario} ${hero} vs ${vil}`;
    }
  }

  const firstWord = restNoParen.match(/^([A-Za-z0-9+\/]+)/)?.[1]?.toUpperCase() ?? "";
  if (firstWord && allowed.has(firstWord)) {
    return `${scenario} ${firstWord}`;
  }

  return scenario;
}

const STUDY_CHARTS: Record<string, ChartDef> = {
  // RFI
  rfi_ep: {
    id: "rfi_ep",
    label: "RFI — EP (UTG/UTG+1/UTG+2)",
    raise_tokens: [
      "AA", "KK", "QQ", "JJ", "AKs", "TT", "AKo", "AQs", "99", "AJs", "AQo",
      "88", "ATs", "KQs", "77", "KJs", "QJs", "KTs", "QTs", "JTs",
    ],
  },
  rfi_mp: {
    id: "rfi_mp",
    label: "RFI — MP (LJ/HJ)",
    raise_tokens: [
      "AA", "KK", "QQ", "JJ", "AKs", "TT", "AKo", "AQs", "99", "AJs", "AQo",
      "88", "ATs", "KQs", "AJo", "77", "KJs", "QJs", "KTs", "KQo", "A9s",
      "66", "A8s", "QTs", "JTs", "KJo", "A7s", "A5s", "K9s", "A4s",
      "A6s", "55", "Q9s", "A3s", "J9s", "T9s",
      "A2s", "44",
    ],
  },
  rfi_lp: {
    id: "rfi_lp",
    label: "RFI — LP (CO/BTN)",
    raise_tokens: [
      "AA", "KK", "QQ", "JJ", "AKs", "TT", "AKo", "AQs", "99", "AJs", "AQo",
      "88", "ATs", "KQs", "AJo", "77", "KJs", "QJs", "KTs", "KQo", "A9s",
      "ATo", "66", "A8s", "QTs", "JTs", "KJo", "A7s", "A5s", "K9s", "A4s",
      "A6s", "55", "Q9s", "A3s", "J9s", "KTo", "QJo", "A9o", "T9s", "K8s",
      "A2s", "K7s", "44", "A8o", "QTo", "Q8s", "JTo", "J8s", "K6s", "98s",
      "T8s", "K5s", "A7o", "K4s", "K9o", "A5o", "33", "K3s", "A4o", "Q9o",
      "87s", "Q7s", "T7s", "Q6s", "K2s", "J7s", "A6o", "97s", "Q5s", "J9o",
      "T9o", "22", "Q4s", "76s", "86s", "96s", "J6s", "J5s", "Q3s", "Q2s",
      "T6s", "65s", "75s",
    ],
  },

  // ISO
  iso_mp_vs_ep_limps: {
    id: "iso_mp_vs_ep_limps",
    label: "ISO — MP vs EP Limp(s) (LJ/HJ vs UTG/UTG+1/UTG+2)",
    raise_tokens: [
      "AA", "KK", "QQ", "JJ", "AKs", "TT", "AKo", "AQs", "99", "AJs", "AQo",
      "88", "ATs", "KQs", "KJs", "QJs", "KTs",
    ],
  },
  iso_lp_vs_mp_limps: {
    id: "iso_lp_vs_mp_limps",
    label: "ISO — LP vs MP Limp(s) (CO/BTN vs LJ/HJ)",
    raise_tokens: [
      "AA", "KK", "QQ", "JJ", "AKs", "TT", "AKo", "AQs", "99", "AJs", "AQo",
      "88", "ATs", "KQs", "AJo", "77", "KJs", "QJs", "KTs", "KQo", "A9s",
      "66", "A8s", "QTs", "JTs", "A7s", "A5s", "K9s", "A4s", "Q9s", "J9s",
      "T9s",
    ],
  },
  iso_sb_vs_lp_limps: {
    id: "iso_sb_vs_lp_limps",
    label: "ISO — SB vs LP Limp(s) (SB vs CO/BTN)",
    raise_tokens: [
      "AA", "KK", "QQ", "JJ", "AKs", "TT", "AKo", "AQs", "99", "AJs", "AQo",
      "88", "ATs", "KQs", "AJo", "77", "KJs", "QJs", "KTs", "KQo", "A9s",
      "66", "A8s", "QTs", "JTs", "A7s", "A5s", "K9s", "A4s", "Q9s", "J9s",
      "T9s",
    ],
    call_tokens: ["22", "33", "44", "55", "A2s", "A3s"],
  },

  // 3Bet
  "3bet_mp_vs_ep": {
    id: "3bet_mp_vs_ep",
    label: "3Bet — MP vs EP Open (LJ/HJ vs UTG/UTG+1/UTG+2)",
    raise_tokens: [
      "AA", "KK", "QQ", "JJ", "AKs", "TT", "AKo", "AQs", "99", "AJs", "ATs",
      "KQs", "KJs", "KTs",
    ],
  },
  "3bet_lp_vs_mp": {
    id: "3bet_lp_vs_mp",
    label: "3Bet — LP vs MP Open (CO/BTN vs LJ/HJ)",
    raise_tokens: [
      "AA", "KK", "QQ", "JJ", "AKs", "TT", "AKo", "AQs", "99", "AJs", "AQo",
      "88", "ATs", "KQs", "KJs", "QJs", "KTs", "A9s", "A8s", "QTs", "JTs",
    ],
  },
  "3bet_sb_vs_lp": {
    id: "3bet_sb_vs_lp",
    label: "3Bet — SB vs LP Open (SB vs CO/BTN)",
    raise_tokens: [
      "AA", "KK", "QQ", "JJ", "AKs", "TT", "AKo", "AQs", "99", "AJs", "AQo",
      "88", "ATs", "KQs", "AJo", "77", "KJs", "QJs", "KTs", "KQo", "A9s",
      "66", "A8s", "QTs", "JTs", "A7s", "A5s", "K9s", "A4s",
    ],
  },

  // Squeeze
  squeeze_lp_vs_ep_open_mp_call: {
    id: "squeeze_lp_vs_ep_open_mp_call",
    label: "Squeeze — LP vs EP Open + MP Call (CO/BTN squeeze)",
    raise_tokens: [
      "AA", "KK", "QQ", "JJ", "AKs", "TT", "AKo", "AQs", "AJs", "ATs",
      "KQs", "KJs", "KTs",
    ],
    call_tokens: ["22", "33", "44", "55", "66", "77", "88", "99"],
  },
  squeeze_sb_vs_ep_open_mp_call_lp_call: {
    id: "squeeze_sb_vs_ep_open_mp_call_lp_call",
    label: "Squeeze — SB vs EP Open + MP Call + LP Call",
    raise_tokens: ["AA", "KK", "QQ", "JJ", "AKs", "TT", "AKo", "AQs", "AJs", "KQs"],
  },

  // 3Bet Defend
  defend_mp_vs_lp_3bet: {
    id: "defend_mp_vs_lp_3bet",
    label: "3Bet Defend — OOP (MP vs LP 3Bet)",
    raise_tokens: ["AA", "KK", "QQ", "AKs", "AKo", "AQs"],
    call_tokens: ["88", "99", "TT", "JJ", "KQs", "KJs", "AJs"],
  },
  defend_mp_vs_sb_3bet: {
    id: "defend_mp_vs_sb_3bet",
    label: "3Bet Defend — IP (MP vs SB 3Bet)",
    raise_tokens: ["AA", "KK", "AKs"],
    call_tokens: [
      "55", "66", "77", "88", "99", "TT", "JJ",
      "KQs", "KJs", "AJs", "QJs",
      "AKo", "AQs", "QQ", "KTs", "ATs",
    ],
  },

  // BB Defend
  bb_defend_hu: {
    id: "bb_defend_hu",
    label: "BB Defend HU — vs single RFI",
    raise_tokens: ["AA", "KK", "QQ", "JJ", "AKs", "AKo", "AQs"],
    call_tokens: [
      "22", "33", "44", "55", "66", "77", "88", "99",
      "AJs", "ATs", "KQs", "KJs", "KTs", "AQo", "QJs", "QTs", "JTs",
      "A9s", "K9s", "Q9s", "J9s", "T9s",
      "87s", "76s", "65s", "54s", "43s",
      "75s", "74s", "64s", "53s",
      "A5s", "A4s",
    ],
  },
  bb_defend_mw: {
    id: "bb_defend_mw",
    label: "BB Defend MW — vs EP/MP RFI + callers",
    raise_tokens: [
      "AA", "KK", "QQ", "JJ", "AKs", "AKo", "AQs",
      "AJs", "TT", "ATs", "KTs", "KJs", "KQs",
    ],
    call_tokens: [
      "22", "33", "44", "55", "66", "77", "88", "99",
      "54s", "43s", "64s", "53s",
      "A5s", "A4s", "A3s",
    ],
  },
};

const DEFAULT_ACTIONS_BY_CHART_ID: Record<string, Record<string, MatrixAction>> = Object.fromEntries(
  Object.values(STUDY_CHARTS).map((c) => [c.id, buildDefaultActions(c)])
) as Record<string, Record<string, MatrixAction>>;

const STUDY_CATEGORY_GROUPS: Array<{
  key: StudyCategoryKey;
  label: string;
  chartIds: string[];
}> = [
  { key: "RFI", label: "RFI", chartIds: ["rfi_ep", "rfi_mp", "rfi_lp"] },
  { key: "ISO", label: "ISO", chartIds: ["iso_mp_vs_ep_limps", "iso_lp_vs_mp_limps", "iso_sb_vs_lp_limps"] },
  { key: "3BET", label: "3Bet", chartIds: ["3bet_mp_vs_ep", "3bet_lp_vs_mp", "3bet_sb_vs_lp"] },
  { key: "SQUEEZE", label: "Squeeze", chartIds: ["squeeze_lp_vs_ep_open_mp_call", "squeeze_sb_vs_ep_open_mp_call_lp_call"] },
  { key: "3BET_DEFEND", label: "3Bet Defend", chartIds: ["defend_mp_vs_sb_3bet", "defend_mp_vs_lp_3bet"] },
  { key: "BB_DEFEND", label: "BB Defend", chartIds: ["bb_defend_hu", "bb_defend_mw"] },
];

const DEV_RFI: DeviationGroup[] = [
  {
    title: "When to open wider",
    bullets: ["With fish in blinds", "Passive table", "More fold equity", "Deep stack depth"],
  },
  {
    title: "When to open tighter",
    bullets: ["Regs in the blinds", "Aggressive table", "Shallow stack depth", "Less fold equity"],
  },
];

const DEV_ISO: DeviationGroup[] = [
  {
    title: "When to raise wider",
    bullets: ["Larger edge post-flop vs villain(s)", "Weaker opponent range(s)", "More fold equity", "Deep stack depth"],
  },
  {
    title: "When to raise tighter",
    bullets: ["Smaller post-flop edge vs villain(s)", "Stronger opponent range(s)", "Less fold equity", "Shallow stack depth"],
  },
  {
    title: "When to limp behind",
    bullets: ["Passive players/fish in the blinds", "Low pocket pairs", "Opponents have stronger limping ranges", "Deep stack depth"],
  },
];

const DEV_3BET: DeviationGroup[] = [
  {
    title: "When to raise wider",
    bullets: ["Larger edge post-flop vs villain", "Weaker opponent range", "More fold equity", "Deep stack depth"],
  },
  {
    title: "When to raise tighter",
    bullets: ["Smaller post-flop edge vs villain", "Stronger opponent range", "Less fold equity", "Shallow stack depth"],
  },
];

const DEV_SQUEEZE: DeviationGroup[] = [
  {
    title: "When to squeeze wider",
    bullets: ["Larger edge post-flop vs villains", "Weaker opponent ranges", "More fold equity", "Deep stack depth"],
  },
  {
    title: "When to squeeze tighter",
    bullets: ["Smaller post-flop edge vs villains", "Stronger opponent ranges", "Less fold equity", "Shallow stack depth"],
  },
  {
    title: "When to call behind",
    bullets: ["Passive players/fish in the blinds", "Low-mid pocket pairs", "Opponents have stronger raising/calling ranges", "Deep stack depth"],
  },
];

const DEV_3BET_DEFEND_IP: DeviationGroup[] = [
  {
    title: "When to raise wider",
    bullets: ["Balanced/Polar opponent range", "More fold equity"],
  },
  {
    title: "When to call wider",
    bullets: ["Larger post-flop edge vs villain", "Deep stack depth"],
  },
  {
    title: "When to fold more",
    bullets: ["Smaller post-flop edge vs villain", "Stronger opponent range", "Shallow stack depth"],
  },
];

const DEV_3BET_DEFEND_OOP: DeviationGroup[] = [
  {
    title: "When to raise wider",
    bullets: ["Balanced/Polar opponent range", "More fold equity"],
  },
  {
    title: "When to call wider",
    bullets: ["Larger post-flop edge vs villain", "Deep stack depth"],
  },
  {
    title: "When to fold more",
    bullets: ["Smaller post-flop edge vs villain", "Stronger opponent range", "Shallow stack depth"],
  },
];

const DEV_BB_DEFEND_HU: DeviationGroup[] = [
  {
    title: "When to raise wider",
    bullets: ["Weaker opponent range", "More fold equity"],
  },
  {
    title: "When to call wider",
    bullets: ["Larger post-flop edge vs villain", "Deep stack depth", "Better implied odds"],
  },
  {
    title: "When to fold more",
    bullets: ["Smaller post-flop edge vs villain", "Stronger opponent range", "Shallow stack depth", "Facing a larger RFI"],
  },
];

const DEV_BB_DEFEND_MW: DeviationGroup[] = [
  {
    title: "When to raise wider",
    bullets: ["Weaker opponent ranges", "More fold equity"],
  },
  {
    title: "When to call wider",
    bullets: ["Larger post-flop edge vs villains", "Deep stack depth", "Better implied odds"],
  },
  {
    title: "When to fold more",
    bullets: ["Smaller post-flop edge vs villains", "Stronger opponent ranges", "Shallow stack depth", "Facing a larger RFI"],
  },
];

const DEVIATIONS_BY_CHART_ID: Record<string, DeviationGroup[]> = {
  rfi_ep: DEV_RFI,
  rfi_mp: DEV_RFI,
  rfi_lp: DEV_RFI,

  iso_mp_vs_ep_limps: DEV_ISO,
  iso_lp_vs_mp_limps: DEV_ISO,
  iso_sb_vs_lp_limps: DEV_ISO,

  "3bet_mp_vs_ep": DEV_3BET,
  "3bet_lp_vs_mp": DEV_3BET,
  "3bet_sb_vs_lp": DEV_3BET,

  squeeze_lp_vs_ep_open_mp_call: DEV_SQUEEZE,
  squeeze_sb_vs_ep_open_mp_call_lp_call: DEV_SQUEEZE,

  defend_mp_vs_sb_3bet: DEV_3BET_DEFEND_IP,
  defend_mp_vs_lp_3bet: DEV_3BET_DEFEND_OOP,

  bb_defend_hu: DEV_BB_DEFEND_HU,
  bb_defend_mw: DEV_BB_DEFEND_MW,
};

function ChevronLeftIcon(props: { style?: React.CSSProperties }) {
  return (
    <svg style={props.style} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M14.8 6.7L9.6 12l5.2 5.3"
        stroke="rgba(240,235,224,0.92)"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function ChevronRightIcon(props: { style?: React.CSSProperties }) {
  return (
    <svg style={props.style} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M9.2 6.7L14.4 12l-5.2 5.3"
        stroke="rgba(240,235,224,0.92)"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function StudyHome(props: { onOpenCategory: (key: StudyCategoryKey) => void }) {
  const { onOpenCategory } = props;

  const cardStyle: React.CSSProperties = {
    borderRadius: 18,
    border: "1px solid rgba(240,235,224,0.10)",
    background: "rgba(240,235,224,0.06)",
    boxShadow: "0 14px 38px rgba(20,18,16,0.42)",
    padding: 22,
    minHeight: 175, // UPDATED: taller cards (closer to square)
    cursor: "pointer",
    transition: "transform 120ms ease, background 120ms ease, border 120ms ease",
    userSelect: "none",
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div
        style={{
          fontSize: 15.5,
          fontWeight: 900,
          color: "rgba(240,235,224,0.92)",
          letterSpacing: 0.25,
        }}
      >
        Choose a scenario category to review default charts and deviations.
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(3, minmax(0, 1fr))",
          gap: 12,
        }}
      >
        {STUDY_CATEGORY_GROUPS.map((g) => (
          <div
            key={g.key}
            style={cardStyle}
            onClick={() => onOpenCategory(g.key)}
            onMouseEnter={(e) => {
              const el = e.currentTarget as HTMLDivElement;
              el.style.transform = "translateY(-2px)";
              el.style.background = "rgba(240,235,224,0.06)";
              el.style.border = "1px solid rgba(231,111,81,0.22)";
            }}
            onMouseLeave={(e) => {
              const el = e.currentTarget as HTMLDivElement;
              el.style.transform = "translateY(0px)";
              el.style.background = cardStyle.background as string;
              el.style.border = cardStyle.border as string;
            }}
            title={`Open ${g.label} study charts`}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 10 }}>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <div style={{ fontSize: 22, fontWeight: 980, color: "rgba(240,235,224,0.96)" }}>{g.label}</div>
                <div style={{ fontSize: 14.5, fontWeight: 800, color: "rgba(240,235,224,0.88)" }}>
                  {g.chartIds.length} chart{g.chartIds.length === 1 ? "" : "s"}
                </div>
              </div>

              <div
                style={{
                  fontSize: 14,
                  fontWeight: 950,
                  padding: "8px 14px",
                  borderRadius: 999,
                  border: "1px solid var(--accent)",
                  background: "var(--accent)",
                  color: "var(--text)",
                  letterSpacing: 0.25,
                }}
              >
                View
              </div>
            </div>
            <div style={{ marginTop: 14, fontSize: 14.5, color: "rgba(240,235,224,0.92)", fontWeight: 750 }}>
              Default charts + Deviations
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function StudyModal(props: {
  categoryKey: StudyCategoryKey;
  chartIndex: number;
  onPrev: () => void;
  onNext: () => void;
  onClose: () => void;
}) {
  const { categoryKey, chartIndex, onPrev, onNext, onClose } = props;

  const group = STUDY_CATEGORY_GROUPS.find((g) => g.key === categoryKey);
  if (!group) return null;

  const chartId = group.chartIds[chartIndex] ?? group.chartIds[0];
  const chart = STUDY_CHARTS[chartId];
  const defaultActions = DEFAULT_ACTIONS_BY_CHART_ID[chartId];
  const devs = DEVIATIONS_BY_CHART_ID[chartId] ?? [];

  const overlayStyle: React.CSSProperties = {
    position: "fixed",
    inset: 0,
    background: "rgba(20,18,16,0.60)",
    backdropFilter: "blur(6px)",
    zIndex: 200,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    padding: 10, // UPDATED: more space for modal content
  };

  const panelStyle: React.CSSProperties = {
    width: "min(1320px, 98vw)", // UPDATED: slightly bigger modal
    maxHeight: "96vh", // UPDATED: slightly taller modal
    overflow: "hidden",
    borderRadius: 20,
    border: "1px solid rgba(240,235,224,0.10)",
    background: "rgba(20,18,16,0.98)",
    boxShadow: "0 24px 70px rgba(20,18,16,0.65)",
    display: "flex",
    flexDirection: "column",
  };

  const headerStyle: React.CSSProperties = {
    padding: 14,
    borderBottom: "1px solid rgba(240,235,224,0.08)",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
  };

  const iconBtn: React.CSSProperties = {
    width: 40,
    height: 40,
    borderRadius: 14,
    border: "1px solid rgba(240,235,224,0.10)",
    background: "rgba(240,235,224,0.06)",
    boxShadow: "0 10px 26px rgba(20,18,16,0.25)",
    cursor: "pointer",
    display: "grid",
    placeItems: "center",
    color: "rgba(240,235,224,0.95)",
  };

  const contentStyle: React.CSSProperties = {
    display: "grid",
    gridTemplateColumns: "minmax(560px, 1fr) 420px",
    gap: 12,
    padding: 12, // UPDATED: slightly tighter padding
    alignItems: "start",
    overflow: "auto",
  };

  const rightCardStyle: React.CSSProperties = {
    borderRadius: 18,
    border: "1px solid rgba(240,235,224,0.08)",
    background: "rgba(240,235,224,0.06)",
    boxShadow: "0 14px 38px rgba(20,18,16,0.42)",
    padding: 12,
  };

  const title = shortStudyScenarioTitle(chart);

  return (
    <div style={overlayStyle} onClick={onClose}>
      <div style={panelStyle} onClick={(e) => e.stopPropagation()}>
        <div style={headerStyle}>
          <div style={{ display: "flex", flexDirection: "column", gap: 4, minWidth: 0 }}>
            <div
              style={{
                fontSize: 28, // UPDATED: bigger title
                fontWeight: 990,
                color: "rgba(240,235,224,0.97)",
                letterSpacing: 0.2,
                lineHeight: 1.02,
                minWidth: 0,
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
              title={title}
            >
              {title}
            </div>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <button style={iconBtn} onClick={onPrev} title="Previous chart">
              <ChevronLeftIcon style={{ width: 18, height: 18 }} />
            </button>

            <div style={{ fontSize: 12.5, fontWeight: 950, color: "rgba(240,235,224,0.90)" }}>
              {chartIndex + 1}/{group.chartIds.length}
            </div>

            <button style={iconBtn} onClick={onNext} title="Next chart">
              <ChevronRightIcon style={{ width: 18, height: 18 }} />
            </button>

            <button
              style={{
                ...iconBtn,
                width: 44,
                fontSize: 16,
                fontWeight: 950,
              }}
              onClick={onClose}
              title="Close"
            >
              ✕
            </button>
          </div>
        </div>

        <div style={contentStyle}>
          {/* Left: Default chart */}
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {/* Read-only matrix (same visuals as Train) */}
            <div style={{ pointerEvents: "none" }}>
              <HandMatrix
                allowedActions={["FOLD", "CALL", "RAISE"]}
                defaultActions={defaultActions}
                currentActions={defaultActions}
                showDefaultOverlay={false}
                title="Default Chart"
                titleFontSize={18}
                titleColor="rgba(240,235,224,0.97)"
                maxWidth={700}
                onChange={() => {}}
              />
            </div>
          </div>

          {/* Right: deviations */}
          <div style={rightCardStyle}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
              <div style={{ fontSize: 18, fontWeight: 990, color: "rgba(240,235,224,0.97)" }}>Deviations</div>
              <div style={{ fontSize: 13.5, color: "rgba(240,235,224,0.92)", fontWeight: 850 }}></div>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {devs.map((g) => (
                <div
                  key={g.title}
                  style={{
                    borderRadius: 18,
                    border: "1px solid rgba(240,235,224,0.08)",
                    background: "rgba(240,235,224,0.04)",
                    padding: 16,
                  }}
                >
                  <div style={{ fontSize: 16, fontWeight: 980, color: "rgba(240,235,224,0.95)" }}>
                    {g.title}
                  </div>

                  <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 6 }}>
                    {g.bullets.map((b) => (
                      <div
                        key={b}
                        style={{
                          display: "flex",
                          gap: 10,
                          alignItems: "center",
                          color: "rgba(240,235,224,0.95)",
                          fontSize: 14.2,
                          lineHeight: 1.45,
                          fontWeight: 750,
                        }}
                      >
                        <div
                          style={{
                            width: 10,
                            height: 10,
                            borderRadius: 999,
                            background: "rgba(231,111,81,0.65)",
                            flex: "0 0 auto",
                          }}
                        />
                        <div style={{ flex: 1 }}>{b}</div>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}



export default function WorkbenchStudy() {
  const [studyCategory, setStudyCategory] = useState<StudyCategoryKey | null>(null);
  const [studyChartIndex, setStudyChartIndex] = useState(0);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <StudyHome
        onOpenCategory={(key) => {
          setStudyCategory(key);
          setStudyChartIndex(0);
        }}
      />

      {studyCategory && (
        <StudyModal
          categoryKey={studyCategory}
          chartIndex={studyChartIndex}
          onPrev={() => {
            const group = STUDY_CATEGORY_GROUPS.find((g) => g.key === studyCategory);
            if (!group) return;
            setStudyChartIndex((idx) => (idx - 1 + group.chartIds.length) % group.chartIds.length);
          }}
          onNext={() => {
            const group = STUDY_CATEGORY_GROUPS.find((g) => g.key === studyCategory);
            if (!group) return;
            setStudyChartIndex((idx) => (idx + 1) % group.chartIds.length);
          }}
          onClose={() => setStudyCategory(null)}
        />
      )}
    </div>
  );
}

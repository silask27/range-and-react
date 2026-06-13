"use client";

import type { CSSProperties } from "react";
import AppShell from "../../components/app/AppShell";
import { useRequireAuth } from "../../lib/hooks/useRequireAuth";

const GUIDE_SECTIONS = [
  {
    title: "Range score",
    copy: "Range score measures how well a member kept the real hand, bucket, and hand family alive while narrowing villain down. A high score means the member did not cut the truth too early and still removed enough unlikely hands to make the range useful.",
    example: "Example: villain actually has a set. If the member keeps sets in the range on flop and turn, they get credit. If they remove every set after a small bet, the score drops because the real answer was no longer possible.",
  },
  {
    title: "Action score",
    copy: "Action score measures how well the member predicted how villain's current range would respond to hero's available action. It is about the reaction, not whether hero personally liked the line.",
    example: "Example: hero bets small and a calling-station villain continues with a flush draw. If the member marked that draw bucket as call, they get credit. If they marked fold, the action score drops.",
  },
  {
    title: "Overall score",
    copy: "Overall score is the simple average of range score and action score. Keeping them separate is important because a player can range villains well but still miss how a specific villain type reacts.",
    example: "Example: range 82 and action 64 gives an overall of 73. The coach should not just see 73; they should see that action prediction needs the next drill.",
  },
  {
    title: "Villain types",
    copy: "Villain types are one of the main signals in the product. The same board and line can mean different things from a nit, calling station, loose reg, or maniac. Coaches should use villain-specific misses to assign better reps.",
    example: "Example: if a member underestimates how often a maniac raises draws, assign maniac response drills instead of generic flop work.",
  },
  {
    title: "Coach command center",
    copy: "The coach view rolls member work into cohort completion, struggling members, weakest scenarios, weakest villains, and overdue assignments. It is built to answer what a coach should do next.",
    example: "Example: if Deep Stack Study Group is only 42% through its sprint and the weakest villain is Steve, the next action is a cohort nudge plus a maniac-focused drill.",
  },
  {
    title: "Member CSV",
    copy: "Coaches and admins can download one row per member with current range score, action score, overall score, reps done, and assignment counts. That makes external reporting easy for a coaching business.",
    example: "Example: HungryHorsePoker can export the roster before a review call and sort by overdue assignments or lowest action score.",
  },
];

export default function GuidePage() {
  const { isAuthLoading, authError } = useRequireAuth();

  return (
    <AppShell title="Guide" subtitle="Plain-English scoring and workflow notes for coaches, members, and demo walkthroughs.">
      {isAuthLoading ? <div style={mutedStyle}>Loading guide…</div> : null}
      {authError ? <div style={errorStyle}>{authError}</div> : null}
      <section style={introStyle}>
        <div style={eyebrowStyle}>Quick read</div>
        <h2 style={titleStyle}>The product trains two linked skills: narrowing villain correctly, then predicting how that villain reacts.</h2>
        <p style={copyStyle}>
          Range & React is designed for live-poker coaching. The point is not to memorize one perfect answer. The point is to build a repeatable decision process that respects villain type, scenario, action history, and range interaction.
        </p>
      </section>
      <section style={gridStyle}>
        {GUIDE_SECTIONS.map((section) => (
          <article key={section.title} style={panelStyle}>
            <div style={eyebrowStyle}>{section.title}</div>
            <p style={copyStyle}>{section.copy}</p>
            <div style={exampleStyle}>{section.example}</div>
          </article>
        ))}
      </section>
      <section style={introStyle}>
        <div style={eyebrowStyle}>How to use this in a pitch</div>
        <h2 style={titleStyle}>Show owner value, coach control, then member growth.</h2>
        <p style={copyStyle}>
          Start with the demo walkthrough, open the coach command center, download the member CSV, then switch to a member and show their growth view. That sequence makes the business value and the training value easy to understand in under ten minutes.
        </p>
      </section>
    </AppShell>
  );
}

const introStyle: CSSProperties = { borderTop: "1px solid var(--line-soft)", paddingTop: 18, display: "grid", gap: 12 };
const gridStyle: CSSProperties = { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 320px), 1fr))", gap: 18 };
const panelStyle: CSSProperties = { border: "1px solid var(--line)", borderRadius: 18, padding: 18, background: "var(--surface-fill)", display: "grid", gap: 10 };
const eyebrowStyle: CSSProperties = { color: "var(--accent)", fontSize: 12, textTransform: "uppercase", letterSpacing: 1.2, fontWeight: 900 };
const titleStyle: CSSProperties = { margin: 0, fontSize: 28, lineHeight: 1.14 };
const copyStyle: CSSProperties = { margin: 0, color: "var(--text-65)", lineHeight: 1.75 };
const exampleStyle: CSSProperties = { borderTop: "1px solid var(--line-soft)", paddingTop: 10, color: "var(--text)", lineHeight: 1.65, fontSize: 14 };
const mutedStyle: CSSProperties = { color: "var(--text-65)" };
const errorStyle: CSSProperties = { color: "var(--accent)", fontWeight: 800 };

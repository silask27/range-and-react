"use client";

import type { CSSProperties } from "react";

export type WorkflowStepState = "upcoming" | "active" | "complete";
export type WorkflowStep = { key: string; label: string; state: WorkflowStepState };

type WorkflowBarProps = { steps: WorkflowStep[]; helperText?: string; timerLabel?: string; showTimer?: boolean; showHelper?: boolean };

function stepStyle(state: WorkflowStepState): CSSProperties {
  if (state === "active") return { border: "1px solid var(--accent)", background: "var(--accent)", color: "var(--text)" };
  if (state === "complete") return { border: "1px solid var(--success)", background: "var(--success)", color: "var(--bg)" };
  return { border: "1px solid var(--line)", background: "transparent", color: "var(--text-45)" };
}

export default function WorkflowBar({ steps, helperText = "", timerLabel = "No timer", showTimer = true, showHelper = true }: WorkflowBarProps) {
  return (
    <section style={wrapStyle} aria-label="Training workflow">
      <div style={{ display: "grid", gap: 12, minWidth: 0, flex: 1 }}>
        <div style={rowStyle}>
          {steps.map((step) => <div key={step.key} style={{ ...pillStyle, ...stepStyle(step.state) }}>{step.label}</div>)}
        </div>
        {showHelper && helperText ? <p style={helperStyle}>{helperText}</p> : null}
      </div>
      {showTimer ? <span className="badge badge-muted">Timer · {timerLabel}</span> : null}
    </section>
  );
}

const wrapStyle: CSSProperties = { display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 18, width: "100%", paddingBottom: 12 };
const rowStyle: CSSProperties = { display: "flex", gap: 10, flexWrap: "wrap" };
const pillStyle: CSSProperties = { minHeight: 44, padding: "0 16px", borderRadius: 999, display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: 14, fontWeight: 760, letterSpacing: ".01em" };
const helperStyle: CSSProperties = { margin: 0, color: "var(--text-65)", lineHeight: 1.55, fontSize: 14 };

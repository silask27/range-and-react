import type { CSSProperties } from "react";
import type { TrainStudyMode } from "../../lib/preflop/types";

type Props = { mode: TrainStudyMode; onChange: (next: TrainStudyMode) => void };

const WRAP_STYLE: CSSProperties = {
  display: "inline-flex",
  alignItems: "stretch",
  borderRadius: 999,
  border: "1px solid var(--line)",
  background: "transparent",
  overflow: "hidden",
  minHeight: 38,
};

const BUTTON_STYLE: CSSProperties = {
  minWidth: 78,
  padding: "0 18px",
  border: "none",
  background: "transparent",
  color: "var(--text)",
  fontSize: 13.5,
  fontWeight: 900,
  lineHeight: 1,
};

export default function ModeSplitToggle({ mode, onChange }: Props) {
  return (
    <div style={WRAP_STYLE} aria-label="Mode toggle">
      {(["train", "study"] as const).map((item, index) => {
        const active = mode === item;
        return (
          <button
            key={item.charAt(0).toUpperCase() + item.slice(1)}
            type="button"
            onClick={() => onChange(item)}
            style={{
              ...BUTTON_STYLE,
              background: active ? "var(--accent)" : "transparent",
              color: active ? "var(--text)" : "var(--text)",
              borderLeft: index === 0 ? "none" : "1px solid var(--line)",
            }}
          >
            {item.charAt(0).toUpperCase() + item.slice(1)}
          </button>
        );
      })}
    </div>
  );
}

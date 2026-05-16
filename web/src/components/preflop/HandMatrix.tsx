// web/src/components/preflop/HandMatrix.tsx
import React, { useMemo, useState } from "react";

import type { MatrixAction } from "../../lib/preflop/types";
import { make13x13Grid } from "../../lib/preflop/handGrid";

type DeltaKind = "none" | "added" | "removed" | "changed";

type Props = {
  allowedActions: MatrixAction[]; // e.g. ["FOLD","RAISE"] or ["FOLD","CALL","RAISE"]
  defaultActions: Record<string, MatrixAction>;
  currentActions: Record<string, MatrixAction>;

  showDefaultOverlay: boolean;
  forceShowChangesOnly?: boolean;
  highlightShowChanges?: boolean;
  readOnly?: boolean;
  maxWidth?: number;

  title?: string;
  titleFontSize?: number;
  titleColor?: string;

  onChange: (next: Record<string, MatrixAction>) => void;
};

function cycleAction(current: MatrixAction, allowed: MatrixAction[]): MatrixAction {
  const idx = allowed.indexOf(current);
  if (idx === -1) return allowed[0];
  return allowed[(idx + 1) % allowed.length];
}

function getDeltaKind(def: MatrixAction, cur: MatrixAction): DeltaKind {
  if (def === cur) return "none";

  const defIsFold = def === "FOLD";
  const curIsFold = cur === "FOLD";

  if (defIsFold && !curIsFold) return "added";
  if (!defIsFold && curIsFold) return "removed";
  return "changed";
}

function bgForAction(action: MatrixAction): string {
  if (action === "RAISE") return "#E76F51";
  if (action === "CALL") return "#6A9E72";
  return "rgba(240,235,224,0.45)";
}

function borderForAction(action: MatrixAction): string {
  if (action === "RAISE") return "rgba(231,111,81,0.90)";
  if (action === "CALL") return "rgba(106,158,114, 0.90)";
  return "rgba(240,235,224,0.10)";
}

function textForAction(action: MatrixAction): string {
  if (action === "FOLD") return "rgba(240,235,224,0.78)";
  return "rgba(240,235,224, 0.92)";
}

export function HandMatrix(props: Props) {
  const {
    allowedActions,
    defaultActions,
    currentActions,
    showDefaultOverlay,
    forceShowChangesOnly,
    highlightShowChanges,
    readOnly,
    onChange,
  } = props;

  const cells = useMemo(() => make13x13Grid(), []);
  const [hoverToken, setHoverToken] = useState<string | null>(null);
  const [showChangesOnly, setShowChangesOnly] = useState<boolean>(false);
  const effectiveShowChangesOnly = forceShowChangesOnly ?? showChangesOnly;

  function handleClick(token: string) {
    if (readOnly) return;
    const cur = currentActions[token] ?? "FOLD";
    const nextAction = cycleAction(cur, allowedActions);

    const nextMap: Record<string, MatrixAction> = {
      ...currentActions,
      [token]: nextAction,
    };

    onChange(nextMap);
  }

  function handleReset() {
    if (readOnly) return;
    onChange({ ...defaultActions });
  }

  const containerStyle: React.CSSProperties = {
    width: "100%",
    background: "transparent",
    borderTop: "1px solid var(--border)",
    paddingTop: 12,
  };

  const headerRowStyle: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 10,
    marginBottom: 10,
  };

  const headerRightStyle: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: 10,
  };

  const smallBtnStyle: React.CSSProperties = {
    padding: "8px 12px",
    borderRadius: 999,
    border: "1px solid var(--border)",
    background: "transparent",
    color: "var(--text)",
    fontWeight: 900,
    fontSize: 12,
    cursor: "pointer",
    userSelect: "none",
  };

  const toggleBtnStyle = (on: boolean): React.CSSProperties => ({
    ...smallBtnStyle,
    background: on ? "#6A9E72" : "transparent",
    border: on ? "1px solid #6A9E72" : "1px solid var(--border)",
    color: on ? "var(--bg)" : "var(--text)",
    boxShadow: highlightShowChanges
      ? "0 0 0 3px rgba(106,158,114,0.24)"
      : undefined,
  });

  const squareWrapStyle: React.CSSProperties = {
    width: "100%",
    maxWidth: props.maxWidth ?? 740,
    aspectRatio: "1 / 1",
    margin: "0 auto",
  };

  const gridStyle: React.CSSProperties = {
    width: "100%",
    height: "100%",
    display: "grid",
    gridTemplateColumns: "repeat(13, minmax(0, 1fr))",
    gridTemplateRows: "repeat(13, minmax(0, 1fr))",
    gap: 6,
  };

  return (
    <div style={containerStyle}>
      <div style={headerRowStyle}>
        <div
          style={{
            fontSize: props.titleFontSize ?? 14.5,
            fontWeight: 900,
            color: props.titleColor ?? "rgba(240,235,224,0.92)",
          }}
        >
          {props.title ?? "Range Matrix"}
        </div>

        <div style={headerRightStyle}>
          <button
            style={toggleBtnStyle(effectiveShowChangesOnly)}
            onClick={() => {
              if (!forceShowChangesOnly) setShowChangesOnly((v) => !v);
            }}
            title="Dim unchanged tiles so only deviations pop"
            type="button"
            disabled={Boolean(forceShowChangesOnly)}
          >
            Show Changes
          </button>

          {!readOnly ? (
            <button
              style={smallBtnStyle}
              onClick={handleReset}
              title="Revert matrix back to default"
              type="button"
            >
              Reset
            </button>
          ) : null}
        </div>
      </div>

      <div style={squareWrapStyle}>
        <div style={gridStyle}>
          {cells.map((cell) => {
            const token = cell.token;
            const cur = currentActions[token] ?? "FOLD";
            const def = defaultActions[token] ?? "FOLD";
            const deltaKind = getDeltaKind(def, cur);

            const isHover = hoverToken === token;
            const isChanged = def !== cur;
            const dimTile = effectiveShowChangesOnly && !isChanged;
            const cornerSize = 20;

            const tileStyle: React.CSSProperties = {
              position: "relative",
              borderRadius: 10,
              border: `1px solid ${borderForAction(cur)}`,
              background: bgForAction(cur),
              cursor: readOnly ? "default" : "pointer",
              userSelect: "none",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontFamily: "ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial",
              fontSize: 12.25,
              letterSpacing: 0.2,
              color: textForAction(cur),
              fontWeight: 800,
              transition: "transform 90ms ease, box-shadow 120ms ease, filter 120ms ease, opacity 120ms ease",
              transform: isHover ? "translateY(-1px)" : "translateY(0)",
              filter: isHover ? "brightness(1.05)" : "brightness(1)",
              opacity: dimTile ? 0.28 : 1,
              boxShadow: isHover ? "0 14px 26px rgba(20,18,16,0.42)" : "0 10px 18px rgba(20,18,16,0.28)",
              overflow: "hidden",
            };

            const showRaiseGhost = showDefaultOverlay && !isChanged && def === "RAISE";
            const showCallGhost = showDefaultOverlay && !isChanged && def === "CALL";
            const tooltip = def === cur ? token : `${token}  •  Default: ${def} → Now: ${cur}`;

            const defaultCornerStyle: React.CSSProperties = {
              position: "absolute",
              top: 0,
              left: 0,
              width: cornerSize,
              height: cornerSize,
              background: bgForAction(def),
              clipPath: "polygon(0 0, 100% 0, 0 100%)",
              pointerEvents: "none",
              opacity: 1,
            };

            const defaultCornerOutline: React.CSSProperties = {
              position: "absolute",
              top: 0,
              left: 0,
              width: cornerSize,
              height: cornerSize,
              clipPath: "polygon(0 0, 100% 0, 0 100%)",
              boxShadow: "inset 0 0 0 1px rgba(240,235,224,0.22)",
              pointerEvents: "none",
              opacity: 0.55,
            };

            const deltaIcon =
              deltaKind === "added" ? "+" : deltaKind === "removed" ? "−" : deltaKind === "changed" ? "→" : null;

            return (
              <div
                key={`${cell.row}-${cell.col}`}
                style={tileStyle}
                title={tooltip}
                onClick={() => handleClick(token)}
                onMouseDown={(e) => e.preventDefault()}
                onMouseEnter={() => setHoverToken(token)}
                onMouseLeave={() => setHoverToken(null)}
              >
                {isChanged && (
                  <>
                    <div style={defaultCornerStyle} />
                    <div style={defaultCornerOutline} />
                  </>
                )}

                {showRaiseGhost && (
                  <div
                    style={{
                      position: "absolute",
                      inset: 6,
                      borderRadius: 8,
                      border: "1px solid rgba(231,111,81,0.75)",
                      boxShadow: "inset 0 0 0 1px rgba(231,111,81,0.25)",
                      pointerEvents: "none",
                      opacity: 0.55,
                    }}
                  />
                )}

                {showCallGhost && (
                  <div
                    style={{
                      position: "absolute",
                      inset: 6,
                      borderRadius: 8,
                      border: "1px solid rgba(106,158,114, 0.75)",
                      boxShadow: "inset 0 0 0 1px rgba(106,158,114, 0.22)",
                      pointerEvents: "none",
                      opacity: 0.55,
                    }}
                  />
                )}

                {deltaIcon && (
                  <div
                    style={{
                      position: "absolute",
                      top: 2,
                      right: 7,
                      fontSize: 13,
                      lineHeight: "12px",
                      color: "rgba(240,235,224, 0.95)",
                      fontWeight: 950,
                      textShadow: "0 1px 10px rgba(20,18,16,0.65)",
                      pointerEvents: "none",
                    }}
                  >
                    {deltaIcon}
                  </div>
                )}

                <span style={{ position: "relative" }}>{token}</span>
              </div>
            );
          })}
        </div>
      </div>

      <div
        style={{
          marginTop: 12,
          display: "flex",
          gap: 10,
          alignItems: "center",
          justifyContent: "space-between",
          color: "rgba(240,235,224,0.92)",
          fontSize: 12,
        }}
      >
        <div style={{ display: "flex", gap: 14, alignItems: "center" }}>
          <LegendDot label="Fold" color="rgba(240,235,224,0.08)" />
          <LegendDot label="Call/Limp" color="#6A9E72" />
          <LegendDot label="Raise" color="#E76F51" />
        </div>

        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <LegendIcon label="Added" icon="+" />
          <LegendIcon label="Removed" icon="−" />
          <LegendIcon label="Changed" icon="→" />
        </div>
      </div>
    </div>
  );
}

function LegendDot(props: { label: string; color: string }) {
  return (
    <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
      <div
        style={{
          width: 10,
          height: 10,
          borderRadius: 999,
          background: props.color,
          boxShadow: "0 0 0 2px rgba(20,18,16,0.20)",
        }}
      />
      <span>{props.label}</span>
    </div>
  );
}

function LegendIcon(props: { label: string; icon: string }) {
  return (
    <div style={{ display: "flex", gap: 7, alignItems: "center" }}>
      <div
        style={{
          width: 16,
          height: 16,
          borderRadius: 6,
          border: "1px solid rgba(240,235,224,0.14)",
          background: "rgba(20,18,16,0.18)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "var(--text)",
          fontWeight: 950,
          fontSize: 12,
          lineHeight: "12px",
          boxShadow: "0 0 0 2px rgba(20,18,16,0.16)",
        }}
      >
        {props.icon}
      </div>
      <span>{props.label}</span>
    </div>
  );
}

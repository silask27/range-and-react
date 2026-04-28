"use client";

import type { CSSProperties } from "react";

type Point = {
  label: string;
  ranging: number | null;
  response: number | null;
};

const COLORS = {
  range: "#E76F51",
  response: "#6A9E72",
  panel: "rgba(240,235,224,0.02)",
  border: "rgba(240,235,224,0.08)",
  text: "#F0EBE0",
  muted: "rgba(240,235,224,0.45)",
};

function buildPath(values: Array<number | null>, width: number, height: number, padding: number) {
  const valid = values
    .map((value, index) => ({ value, index }))
    .filter((item): item is { value: number; index: number } => item.value != null);
  if (!valid.length) return "";
  const innerWidth = width - padding * 2;
  const innerHeight = height - padding * 2;
  return valid
    .map((item, pointIndex) => {
      const x = padding + (values.length === 1 ? innerWidth / 2 : (item.index / Math.max(1, values.length - 1)) * innerWidth);
      const y = padding + innerHeight - (Math.max(0, Math.min(100, item.value)) / 100) * innerHeight;
      return `${pointIndex === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}

function pointCoords(values: Array<number | null>, width: number, height: number, padding: number) {
  const innerWidth = width - padding * 2;
  const innerHeight = height - padding * 2;
  return values.map((value, index) => {
    if (value == null) return null;
    return {
      x: padding + (values.length === 1 ? innerWidth / 2 : (index / Math.max(1, values.length - 1)) * innerWidth),
      y: padding + innerHeight - (Math.max(0, Math.min(100, value)) / 100) * innerHeight,
      value,
      index,
    };
  });
}

function buildXAxisTicks(labels: string[], maxTicks = 5) {
  if (!labels.length) return [];
  const tickCount = Math.min(maxTicks, labels.length);
  if (tickCount <= 1) return [{ index: 0, label: labels[0] }];

  const used = new Set<number>();
  const ticks: Array<{ index: number; label: string }> = [];
  for (let i = 0; i < tickCount; i += 1) {
    const index = Math.round((i * (labels.length - 1)) / (tickCount - 1));
    if (used.has(index)) continue;
    used.add(index);
    ticks.push({ index, label: labels[index] });
  }
  return ticks;
}

export default function TrendChart({
  points,
  height = 220,
  showLegend = true,
}: {
  points: Point[];
  height?: number;
  showLegend?: boolean;
}) {
  const width = 720;
  const padding = 34;
  const rangingValues = points.map((point) => point.ranging);
  const responseValues = points.map((point) => point.response);
  const rangingPath = buildPath(rangingValues, width, height, padding);
  const responsePath = buildPath(responseValues, width, height, padding);
  const rangingDots = pointCoords(rangingValues, width, height, padding);
  const responseDots = pointCoords(responseValues, width, height, padding);
  const displayLabels = buildXAxisTicks(points.map((point) => point.label));
  const ticks = [0, 25, 50, 75, 100];

  return (
    <div style={chartWrapStyle}>
      {showLegend ? (
        <div style={legendStyle}>
          <div style={legendItemStyle}><span style={{ ...legendSwatchStyle, background: COLORS.range }} />Villain ranging</div>
          <div style={legendItemStyle}><span style={{ ...legendSwatchStyle, background: COLORS.response }} />Action prediction</div>
        </div>
      ) : null}
      <div style={chartGridStyle}>
        <div style={axisStyle}>
          {ticks.slice().reverse().map((tick) => <span key={tick} style={axisLabelStyle}>{tick}</span>)}
        </div>
        <div>
          <div style={svgWrapStyle}>
            <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" style={svgStyle}>
              {ticks.filter((tick) => tick > 0 && tick < 100).map((tick) => {
                const y = padding + (height - padding * 2) - (tick / 100) * (height - padding * 2);
                return <line key={tick} x1={padding} x2={width - padding} y1={y} y2={y} stroke="rgba(240,235,224,0.08)" strokeDasharray="5 7" />;
              })}
              <line x1={padding} x2={width - padding} y1={height - padding} y2={height - padding} stroke="rgba(240,235,224,0.12)" />
              {rangingPath ? <path d={rangingPath} fill="none" stroke={COLORS.range} strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" /> : null}
              {responsePath ? <path d={responsePath} fill="none" stroke={COLORS.response} strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" /> : null}
              {rangingDots.map((point, index) => point ? <circle key={`r-${index}`} cx={point.x} cy={point.y} r="4.5" fill={COLORS.range} stroke="#141210" strokeWidth="2" /> : null)}
              {responseDots.map((point, index) => point ? <circle key={`a-${index}`} cx={point.x} cy={point.y} r="4.5" fill={COLORS.response} stroke="#141210" strokeWidth="2" /> : null)}
            </svg>
          </div>
          <div style={{ ...labelsStyle, gridTemplateColumns: `repeat(${Math.max(displayLabels.length, 1)}, minmax(0, 1fr))` }}>
            {displayLabels.map((tick) => (
              <span key={`${tick.index}-${tick.label}`} style={labelStyle}>{tick.label}</span>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

const chartWrapStyle: CSSProperties = { display: "grid", gap: 12 };
const legendStyle: CSSProperties = { display: "flex", gap: 14, flexWrap: "wrap" };
const legendItemStyle: CSSProperties = { display: "inline-flex", alignItems: "center", gap: 8, color: COLORS.text, fontSize: 13, fontWeight: 700 };
const legendSwatchStyle: CSSProperties = { width: 10, height: 10, borderRadius: 999 };
const chartGridStyle: CSSProperties = { display: "grid", gridTemplateColumns: "36px minmax(0, 1fr)", gap: 10, alignItems: "stretch" };
const axisStyle: CSSProperties = { display: "grid", gridTemplateRows: "repeat(5, 1fr)", justifyItems: "end", padding: "10px 0 24px" };
const axisLabelStyle: CSSProperties = { color: COLORS.muted, fontSize: 11, lineHeight: 1 };
const svgWrapStyle: CSSProperties = { borderRadius: 18, overflow: "hidden", border: `1px solid ${COLORS.border}`, background: "var(--surface-fill)", padding: 8 };
const svgStyle: CSSProperties = { width: "100%", height: "100%", minHeight: 220, display: "block" };
const labelsStyle: CSSProperties = { display: "grid", gap: 8, paddingLeft: 2 };
const labelStyle: CSSProperties = { color: COLORS.muted, fontSize: 11, textAlign: "center", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" };

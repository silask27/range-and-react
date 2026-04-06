"use client";

import type { CSSProperties } from "react";

type TimeoutOverlayProps = {
  open: boolean;
  subtitle: string;
};

const BACKDROP_STYLE: CSSProperties = {
  position: "fixed",
  inset: 0,
  zIndex: 2000,
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  padding: "24px",
  background: "rgba(20,18,16,0.62)",
  backdropFilter: "blur(4px)",
};

const MODAL_STYLE: CSSProperties = {
  width: "min(460px, 100%)",
  borderRadius: "20px",
  border: "1px solid rgba(240,235,224,0.08)",
  background:
    "var(--bg)",
  boxShadow: "0 24px 64px rgba(20,18,16,0.38)",
  padding: "28px 24px",
  textAlign: "center",
};

const ICON_WRAP_STYLE: CSSProperties = {
  width: "52px",
  height: "52px",
  margin: "0 auto 16px auto",
  borderRadius: "999px",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  background: "rgba(231,111,81,0.16)",
  border: "1px solid rgba(231,111,81,0.28)",
  color: "rgba(240,235,224,0.98)",
  fontSize: "24px",
};

const TITLE_STYLE: CSSProperties = {
  margin: 0,
  fontSize: "22px",
  lineHeight: 1.2,
  fontWeight: 800,
  letterSpacing: "-0.02em",
  color: "rgba(240,235,224,0.98)",
};

const SUBTITLE_STYLE: CSSProperties = {
  margin: "10px 0 0 0",
  fontSize: "14px",
  lineHeight: 1.5,
  fontWeight: 500,
  color: "rgba(240,235,224,0.65)",
};

export default function TimeoutOverlay({
  open,
  subtitle,
}: TimeoutOverlayProps) {
  if (!open) return null;

  return (
    <div style={BACKDROP_STYLE} role="dialog" aria-modal="true" aria-live="assertive">
      <div style={MODAL_STYLE}>
        <div style={ICON_WRAP_STYLE} aria-hidden="true">
          ⏱
        </div>
        <h2 style={TITLE_STYLE}>Time has expired.</h2>
        <p style={SUBTITLE_STYLE}>{subtitle}</p>
      </div>
    </div>
  );
}
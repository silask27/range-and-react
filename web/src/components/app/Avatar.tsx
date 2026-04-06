"use client";

import { useMemo, useState, type CSSProperties } from "react";

type Props = {
  name?: string | null;
  imageSrc?: string | null;
  size?: number;
  borderColor?: string;
  background?: string;
  textColor?: string;
  fontSize?: number;
  title?: string;
};

export default function Avatar({
  name,
  imageSrc,
  size = 48,
  borderColor = "rgba(240,235,224,0.12)",
  background = "rgba(240,235,224,0.08)",
  textColor = "#F0EBE0",
  fontSize,
  title,
}: Props) {
  const [didError, setDidError] = useState(false);
  const initials = useMemo(() => {
    const raw = (name ?? "?").trim();
    if (!raw) return "?";
    const parts = raw.split(/\s+/).filter(Boolean);
    return parts.slice(0, 2).map((part) => part[0]?.toUpperCase() ?? "").join("") || raw.slice(0, 2).toUpperCase();
  }, [name]);

  const frameStyle: CSSProperties = {
    width: size,
    height: size,
    borderRadius: 999,
    overflow: "hidden",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    border: `1px solid ${borderColor}`,
    background,
    flex: "0 0 auto",
  };

  if (imageSrc && !didError) {
    return (
      <div style={frameStyle} title={title ?? name ?? undefined}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={imageSrc}
          alt={name ?? "Avatar"}
          style={{ width: "100%", height: "100%", objectFit: "cover" }}
          onError={() => setDidError(true)}
        />
      </div>
    );
  }

  return (
    <div style={frameStyle} title={title ?? name ?? undefined}>
      <span style={{ color: textColor, fontWeight: 900, fontSize: fontSize ?? Math.max(14, Math.round(size * 0.34)), letterSpacing: 0.6 }}>
        {initials}
      </span>
    </div>
  );
}

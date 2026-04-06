import React from "react";

import Avatar from "../app/Avatar";
import type { CastSeatState, Seat9Max } from "../../lib/preflop/types";

const SEAT_ORDER: Seat9Max[] = ["UTG", "UTG+1", "UTG+2", "LJ", "HJ", "CO", "BTN", "SB", "BB"];

type HoverMeta = {
  title: string;
  subtitle?: string;
  description?: string;
  iconText?: string;
  avatarSrc?: string;
};

export type PreflopCastSeat = CastSeatState & {
  description?: string;
  iconText?: string;
};

type Props = {
  seats: PreflopCastSeat[];
};

type BadgeTone = "neutral" | "green" | "red" | "active";

function badgeStyle(tone: BadgeTone, filled: boolean): React.CSSProperties {
  const tones = {
    neutral: {
      bg: filled ? "rgba(20,18,16,1)" : "transparent",
      bd: "rgba(240,235,224,0.16)",
      fg: "rgba(240,235,224,0.92)",
    },
    green: {
      bg: filled ? "#6A9E72" : "transparent",
      bd: "#6A9E72",
      fg: "rgba(240,235,224,0.96)",
    },
    red: {
      bg: filled ? "#E76F51" : "transparent",
      bd: "#E76F51",
      fg: "rgba(240,235,224,0.96)",
    },
    active: {
      bg: filled ? "#E76F51" : "transparent",
      bd: "#E76F51",
      fg: "rgba(240,235,224,0.96)",
    },
  }[tone];

  return {
    fontSize: 11.5,
    fontWeight: 950,
    letterSpacing: 0.35,
    padding: "6px 10px",
    borderRadius: 999,
    background: tones.bg,
    border: `1px solid ${tones.bd}`,
    color: tones.fg,
    textTransform: "uppercase",
    whiteSpace: "nowrap",
  };
}

function inferActionTone(actionBubble?: string | null, isSelectedActor?: boolean): BadgeTone {
  if (isSelectedActor && !actionBubble) return "active";

  const raw = (actionBubble ?? "").trim().toUpperCase();
  if (!raw) return "neutral";

  if (raw.includes("CALL") || raw.includes("LIMP")) return "green";
  if (
    raw.includes("OPEN") ||
    raw.includes("RAISE") ||
    raw.includes("3BET") ||
    raw.includes("4BET") ||
    raw.includes("SQUEEZE") ||
    raw.includes("ISO")
  ) {
    return "red";
  }
  if (raw.includes("TO ACT")) return "active";
  return "neutral";
}

function HoverCard(props: { meta: HoverMeta; children: React.ReactNode }) {
  const { meta, children } = props;

  return (
    <div style={{ position: "relative" }}>
      {children}
      <div
        style={{
          position: "absolute",
          left: -8,
          top: -100,
          transform: "translateX(-100%)",
          width: 320,
          zIndex: 50,
          opacity: 0,
          pointerEvents: "none",
          transition: "opacity 120ms ease, transform 120ms ease",
          filter: "drop-shadow(0 14px 32px rgba(20,18,16,0.45))",
        }}
        className="pw-hovercard"
      >
        <div
          style={{
            background: "rgba(20,18,16,1)",
            border: "1px solid var(--text)",
            borderRadius: 16,
            padding: 14,
            boxShadow: "0 12px 40px rgba(20,18,16,0.55)",
          }}
        >
          <div style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
            <div
              style={{
                width: 52,
                height: 52,
                borderRadius: 999,
                background: "var(--surface-tint)",
                border: "1px solid var(--border)",
                overflow: "hidden",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
              title={meta.title}
            >
              <Avatar
                name={meta.title}
                imageSrc={meta.avatarSrc}
                size={52}
                title={meta.title}
                fontSize={18}
                textColor="rgba(240,235,224,0.95)"
              />
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
              <div style={{ fontSize: 15.5, fontWeight: 950, color: "var(--text)" }}>
                {meta.title}
              </div>
              {meta.subtitle ? (
                <div style={{ fontSize: 12.5, color: "var(--text-65)", fontWeight: 700 }}>
                  {meta.subtitle}
                </div>
              ) : null}
            </div>
          </div>

          {meta.description ? (
            <div style={{ marginTop: 10, fontSize: 13, lineHeight: 1.45, color: "var(--text-65)" }}>
              {meta.description}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

export default function PreflopTableCast({ seats }: Props) {
  const bySeat = new Map<Seat9Max, PreflopCastSeat>();
  for (const seat of seats) {
    bySeat.set(seat.seat, seat);
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {SEAT_ORDER.map((seat) => {
        const row = bySeat.get(seat) ?? {
          seat,
          label: seat,
          playerName: "—",
          playerSubtitle: "",
          stackText: null,
          actionBubble: null,
          isDimmed: true,
          isFolded: true,
          iconText: "•",
        };

        const isHero = !!row.isHero;
        const isSelectedActor = !!row.isSelectedActor;
        const isEmpty = row.playerName === "—";
        const isFolded = !!row.isFolded;
        const faded = !!row.isDimmed || isFolded || isEmpty;

        const rowFill = isSelectedActor
          ? "rgba(20,18,16,1)"
          : "transparent";

        const baseCard: React.CSSProperties = {
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 10,
          padding: "12px 0",
          borderRadius: 0,
          borderTop: isSelectedActor ? "1px solid #E76F51" : "1px solid var(--border)",
          background: rowFill,
          boxShadow: "none",
          opacity: faded ? 0.45 : 1,
          transform: "translateZ(0)",
          position: "relative",
        };

        const selectedGlow: React.CSSProperties = isSelectedActor
          ? {
              boxShadow: "none",
            }
          : {};

        const avatarStyle: React.CSSProperties = {
          width: 52,
          height: 52,
          borderRadius: 999,
          background: "rgba(20,18,16,1)",
          border: isSelectedActor ? "2px solid #E76F51" : "1px solid var(--border)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 20,
          flex: "0 0 auto",
          overflow: "hidden",
        };

        const tone = inferActionTone(row.actionBubble, isSelectedActor);
        const hoverMeta: HoverMeta = {
          title: seat,
          subtitle: isHero ? "Hero" : row.playerSubtitle,
          description: row.description,
          avatarSrc: row.avatarSrc,
          iconText: row.iconText ?? (isHero ? "⭐" : row.playerName?.slice(0, 1)?.toUpperCase() || "•"),
        };

        return (
          <div
            key={seat}
            style={{ position: "relative" }}
            onMouseEnter={(e) => {
              const root = e.currentTarget.querySelector(".pw-hovercard") as HTMLDivElement | null;
              if (root) {
                root.style.opacity = "1";
                root.style.transform = "translateX(-100%) translateY(-2px)";
              }
            }}
            onMouseLeave={(e) => {
              const root = e.currentTarget.querySelector(".pw-hovercard") as HTMLDivElement | null;
              if (root) {
                root.style.opacity = "0";
                root.style.transform = "translateX(-100%)";
              }
            }}
          >
            <HoverCard meta={hoverMeta}>
              <div style={{ ...baseCard, ...selectedGlow }}>
                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  <div style={avatarStyle} title={hoverMeta.title}>
                    {isHero ? (
                      "⭐"
                    ) : (
                      <Avatar
                        name={row.playerName ?? seat}
                        imageSrc={row.avatarSrc}
                        size={52}
                        title={hoverMeta.title}
                        fontSize={18}
                      />
                    )}
                  </div>

                  <div style={{ display: "flex", flexDirection: "column", lineHeight: 1.12 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <div style={{ fontSize: 14.5, fontWeight: 950, color: "rgba(240,235,224,0.96)" }}>{seat}</div>
                      {isSelectedActor ? (
                        <div
                          style={{
                            fontSize: 11,
                            fontWeight: 950,
                            padding: "4px 8px",
                            borderRadius: 999,
                            border: "1px solid rgba(231,111,81,0.36)",
                            background: "rgba(231,111,81,0.10)",
                            color: "rgba(240,235,224,0.95)",
                            letterSpacing: 0.35,
                            textTransform: "uppercase",
                          }}
                        >
                          Action on you
                        </div>
                      ) : null}
                    </div>

                    <div style={{ fontSize: 12.5, color: "rgba(240,235,224, 0.95)", fontWeight: 750 }}>
                      {isHero ? "Hero" : row.playerName ?? "—"}
                      {!isHero && row.playerSubtitle ? ` • ${row.playerSubtitle}` : ""}
                    </div>
                  </div>
                </div>

                <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 7 }}>
                  <div style={{ fontSize: 12.5, color: "rgba(240,235,224, 0.92)", fontWeight: 800 }}>
                    {row.stackText ?? ""}
                  </div>

                  {row.actionBubble ? <div style={badgeStyle(tone, true)}>{row.actionBubble}</div> : null}
                </div>
              </div>
            </HoverCard>
          </div>
        );
      })}
    </div>
  );
}

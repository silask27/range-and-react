export const APP_NAME = "Range & React";
export const APP_SHORT_NAME = "LRL";
export const APP_TAGLINE = "Narrow the range. Anticipate its reactions.";

export const THEME = {
  bg: "#141210",
  text: "#F0EBE0",
  primary: "#E76F51",
  success: "#6A9E72",
  line: "rgba(240,235,224,0.16)",
  lineSoft: "rgba(240,235,224,0.10)",
  border: "rgba(240,235,224,0.16)",
  borderSoft: "rgba(240,235,224,0.10)",
  text65: "rgba(240,235,224,0.65)",
  text45: "rgba(240,235,224,0.45)",
  text25: "rgba(240,235,224,0.25)",
  textSoft: "rgba(240,235,224,0.45)",
  textMuted: "rgba(240,235,224,0.65)",
  surface: "rgba(20,18,16,0.96)",
  surfaceStrong: "rgba(20,18,16,1)",
  dangerText: "#F0EBE0",
};

export type Tone = "primary" | "success" | "neutral";

export function toneStyles(tone: Tone) {
  if (tone === "primary") {
    return {
      borderColor: THEME.primary,
      background: THEME.primary,
      color: THEME.text,
    };
  }
  if (tone === "success") {
    return {
      borderColor: THEME.success,
      background: THEME.success,
      color: THEME.bg,
    };
  }
  return {
    borderColor: THEME.line,
    background: THEME.surfaceStrong,
    color: THEME.text,
  };
}

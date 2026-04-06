// web/src/lib/preflop/handGrid.ts

export const RANKS = ["A", "K", "Q", "J", "T", "9", "8", "7", "6", "5", "4", "3", "2"] as const;
export type Rank = (typeof RANKS)[number];

export type Suitedness = "PAIR" | "SUITED" | "OFFSUIT";

export type HandCell = {
  row: number;
  col: number;
  rowRank: Rank;
  colRank: Rank;
  suitedness: Suitedness;
  token: string; // canonical: "AA", "AKs", "AKo"
};

export function isPairToken(token: string): boolean {
  return token.length === 2 && token[0] === token[1];
}

export function isSuitedToken(token: string): boolean {
  return token.endsWith("s");
}

export function isOffsuitToken(token: string): boolean {
  return token.endsWith("o");
}

function rankIndex(r: Rank): number {
  return RANKS.indexOf(r);
}

/**
 * Canonical token builder:
 * Always places the higher rank first (AK not KA).
 * Suitedness is determined by matrix position
 * (above diagonal = suited, below = offsuit).
 */
export function tokenForCell(rowRank: Rank, colRank: Rank, suitedness: Suitedness): string {
  if (suitedness === "PAIR") return `${rowRank}${colRank}`;

  const ri = rankIndex(rowRank);
  const ci = rankIndex(colRank);

  // lower index = higher rank (A=0 strongest)
  const high = ri < ci ? rowRank : colRank;
  const low = ri < ci ? colRank : rowRank;

  if (suitedness === "SUITED") return `${high}${low}s`;
  return `${high}${low}o`;
}

export function suitednessForCell(row: number, col: number): Suitedness {
  if (row === col) return "PAIR";
  if (row < col) return "SUITED";
  return "OFFSUIT";
}

/**
 * Builds the 13×13 hand matrix cells in row-major order.
 */
export function make13x13Grid(): HandCell[] {
  const cells: HandCell[] = [];

  for (let r = 0; r < RANKS.length; r++) {
    for (let c = 0; c < RANKS.length; c++) {
      const rowRank = RANKS[r];
      const colRank = RANKS[c];
      const suitedness = suitednessForCell(r, c);
      const token = tokenForCell(rowRank, colRank, suitedness);

      cells.push({
        row: r,
        col: c,
        rowRank,
        colRank,
        suitedness,
        token,
      });
    }
  }

  return cells;
}

export function prettyToken(token: string): string {
  return token;
}
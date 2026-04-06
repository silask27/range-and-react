// web/src/lib/preflop/types.ts

export type TrainStudyMode = "train" | "study";

export type MatrixAction = "FOLD" | "CALL" | "RAISE";

export type MatrixState = Record<string, MatrixAction>;

export type MatrixDisplayMode = "hero" | "villain";

export type RangeEditorActor = "hero" | "villain";

export type RangeEditorPhase = "first" | "second";

export type Seat9Max =
  | "UTG"
  | "UTG+1"
  | "UTG+2"
  | "LJ"
  | "HJ"
  | "CO"
  | "BTN"
  | "SB"
  | "BB";

export type CastSeatState = {
  seat: Seat9Max;
  label: string;
  playerName?: string;
  playerSubtitle?: string;
  avatarSrc?: string;
  isHero?: boolean;
  isVillain?: boolean;
  isSelectedActor?: boolean;
  isDimmed?: boolean;
  isFolded?: boolean;
  actionBubble?: string | null;
  stackText?: string | null;
};

export type ScenarioOption = {
  id: string;
  display_name: string;
  hero_position: string;
  villain_position: string;
  hero_is_ip: boolean;
  hero_scenario_name: string;
  villain_scenario_name: string;
  hero_action_bubble: string;
  villain_action_bubble: string;
  players_not_folded_hero_action: string[];
  players_not_folded_villain_action: string[];
};

export type VillainOption = {
  id: string;
  name: string;
  archetype?: string;
  description?: string;
  avatar_url?: string | null;
};

export type SessionResponse = {
  session_id: string;
  villain_profile_id: string;
  scenario_id: string | null;
  pot: number | null;
  hero_stack: number | null;
  villain_stack: number | null;
  hero_range_matrix_saved: Record<string, boolean> | null;
  hero_tokens_saved: string[];
  villain_range_matrix_saved: Record<string, boolean> | null;
  villain_tokens_saved: string[];
  hero_range_confirmed: boolean;
  villain_range_confirmed: boolean;
};

export type StudyMatrixAction = "fold" | "call" | "raise";

export type StudyChartFamily =
  | "RFI"
  | "ISO"
  | "3BET"
  | "SQUEEZE"
  | "3BET_DEFEND"
  | "BB_DEFEND";

export type StudyRepLike = {
  id: string;
  title: string;
  subtitle?: string;
  matrix: Record<string, StudyMatrixAction>;
};
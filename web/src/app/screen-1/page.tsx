"use client";

import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
} from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { apiFetch } from "../../lib/api";
import Avatar from "../../components/app/Avatar";
import TrainingHeader from "../../components/app/TrainingHeader";
import { getStoredAuthToken } from "../../lib/auth";
import { THEME } from "../../lib/theme";

import { HandMatrix } from "../../components/preflop/HandMatrix";
import ModeSplitToggle from "../../components/preflop/ModeSplitToggle";
import PreflopTableCast, {
  type PreflopCastSeat,
} from "../../components/preflop/PreflopTableCast";
import WorkbenchStudy from "../../components/preflop/WorkbenchStudy";
import TimeoutOverlay from "../../components/training/TimeoutOverlay";
import WorkflowBar, {
  type WorkflowStep,
} from "../../components/training/WorkflowBar";
import { make13x13Grid } from "../../lib/preflop/handGrid";
import type { MatrixAction, TrainStudyMode } from "../../lib/preflop/types";

type VillainProfile = {
  id: string;
  display_name: string;
  type_label: string;
  description: string;
  image_name: string;
};

type Scenario = {
  id: string;
  display_name: string;
  description: string;
  hero_position: string;
  villain_position: string;
  hero_is_ip: boolean;
  preflop_aggressor: "hero" | "villain";
  default_pot: number;
  hero_range_tokens: string[];
  villain_range_tokens: string[];
  hero_scenario_name: string;
  villain_scenario_name: string;
  hero_action_bubble: string;
  villain_action_bubble: string;
  non_aggressor_previous_action: string | null;
  players_not_folded_hero_action: string[];
  players_not_folded_villain_action: string[];
};

type SessionState = {
  session_id: string;
  villain_profile_id: string;
  train_timer_seconds: number | null;
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

type RangeEditorActor = "hero" | "villain";
type MatrixBoolState = Record<string, boolean>;
type TrainTimerSeconds = 0 | 10 | 30 | 60;
type TimeoutOverlayState = {
  open: boolean;
  subtitle: string;
};

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

const ALL_HAND_TOKENS = make13x13Grid().map((cell) => cell.token);
const DISPLAY_SEATS = [
  "UTG",
  "UTG+1",
  "UTG+2",
  "LJ",
  "HJ",
  "CO",
  "BTN",
  "SB",
  "BB",
] as const;
const TIMER_OPTIONS: TrainTimerSeconds[] = [0, 10, 30, 60];

type DisplaySeat = (typeof DISPLAY_SEATS)[number];

function emptyBoolMatrix(): MatrixBoolState {
  const out: MatrixBoolState = {};
  for (const token of ALL_HAND_TOKENS) out[token] = false;
  return out;
}

function boolMatrixFromTokens(tokens: string[]): MatrixBoolState {
  const out = emptyBoolMatrix();
  for (const token of tokens) {
    if (token in out) out[token] = true;
  }
  return out;
}

function boolMatrixToActionMatrix(
  matrix: MatrixBoolState | null,
  includedAction: Extract<MatrixAction, "CALL" | "RAISE">,
): Record<string, MatrixAction> {
  const out: Record<string, MatrixAction> = {};
  const source = matrix ?? emptyBoolMatrix();
  for (const token of ALL_HAND_TOKENS) {
    out[token] = source[token] ? includedAction : "FOLD";
  }
  return out;
}

function actionMatrixToBoolMatrix(
  actions: Record<string, MatrixAction>,
): MatrixBoolState {
  const out: MatrixBoolState = {};
  for (const token of ALL_HAND_TOKENS) {
    out[token] = actions[token] !== "FOLD";
  }
  return out;
}

function formatStack(value: number | null): string {
  if (value == null) return "";
  return `${Number(value).toFixed(1)} bb`;
}

async function safeReadError(res: Response): Promise<string | null> {
  try {
    const data = (await res.json()) as { detail?: string };
    return typeof data.detail === "string" ? data.detail : null;
  } catch {
    return null;
  }
}

function actorOrder(
  scenario: Scenario | null,
): [RangeEditorActor, RangeEditorActor] {
  if (!scenario) return ["hero", "villain"];
  return scenario.preflop_aggressor === "hero"
    ? ["hero", "villain"]
    : ["villain", "hero"];
}

function includedActionForActor(
  scenario: Scenario | null,
  actor: RangeEditorActor,
): Extract<MatrixAction, "CALL" | "RAISE"> {
  if (!scenario) return "RAISE";
  return scenario.preflop_aggressor === actor ? "RAISE" : "CALL";
}

function titleForActor(
  actor: RangeEditorActor,
  scenario: Scenario | null,
  villain: VillainProfile | null,
): string {
  if (!scenario) return "Range Matrix";
  if (actor === "hero") {
    return `Editing Hero's ${scenario.hero_scenario_name} Range`;
  }
  return `Editing ${villain?.display_name ?? "Villain"}'s ${scenario.villain_scenario_name} Range`;
}

function normalizeSeatList(
  list: string[] | undefined,
  heroSeat: string,
  villainSeat: string,
): DisplaySeat[] {
  const seatSet = new Set<DisplaySeat>();
  const lower = (list ?? []).map((item) => item.trim().toUpperCase());
  const hero = heroSeat.toUpperCase();
  const villain = villainSeat.toUpperCase();

  if (lower.includes("ALL")) {
    for (const seat of DISPLAY_SEATS) {
      if (seat.toUpperCase() !== hero && seat.toUpperCase() !== villain) {
        seatSet.add(seat);
      }
    }
  }

  for (const raw of lower) {
    if (raw === "ALL" || raw === "NONE") continue;
    const found = DISPLAY_SEATS.find((seat) => seat.toUpperCase() === raw);
    if (
      found &&
      found.toUpperCase() !== hero &&
      found.toUpperCase() !== villain
    ) {
      seatSet.add(found);
    }
  }

  return DISPLAY_SEATS.filter((seat) => seatSet.has(seat));
}

function stableIndexFromSeed(seed: string, mod: number): number {
  if (mod <= 0) return 0;
  let hash = 0;
  for (let i = 0; i < seed.length; i += 1) {
    hash = (hash * 31 + seed.charCodeAt(i)) >>> 0;
  }
  return hash % mod;
}

function extraSeatStackText(
  seat: string,
  scenarioId: string | undefined,
  villainId: string | undefined,
): string {
  const seed = `${seat}|${scenarioId ?? ""}|${villainId ?? ""}|stack`;
  const idx = stableIndexFromSeed(seed, 91);
  const bb = 60 + idx;
  return `${bb.toFixed(1)} bb`;
}

function actionBubbleForActor(
  scenario: Scenario | null,
  session: SessionState | null,
  currentActor: RangeEditorActor | null,
  actor: RangeEditorActor,
): string | null {
  if (!scenario || !currentActor) return null;

  const [firstActor] = actorOrder(scenario);
  const firstConfirmed =
    firstActor === "hero"
      ? !!session?.hero_range_confirmed
      : !!session?.villain_range_confirmed;

  const actorConfirmed =
    actor === "hero"
      ? !!session?.hero_range_confirmed
      : !!session?.villain_range_confirmed;

  const isStepOne = currentActor === firstActor && !firstConfirmed;

  if (isStepOne && actor !== firstActor) {
    return scenario.non_aggressor_previous_action ?? null;
  }

  if (!actorConfirmed) return null;

  return actor === "hero"
    ? scenario.hero_action_bubble
    : scenario.villain_action_bubble;
}

function buildCastSeats(args: {
  scenario: Scenario | null;
  villain: VillainProfile | null;
  villains: VillainProfile[];
  session: SessionState | null;
  currentActor: RangeEditorActor | null;
}): PreflopCastSeat[] {
  const { scenario, villain, villains, session, currentActor } = args;

  const heroSeat = (scenario?.hero_position ?? "BTN") as DisplaySeat;
  const villainSeat = (scenario?.villain_position ?? "BB") as DisplaySeat;

  const extraLiveSeats =
    currentActor === "hero"
      ? normalizeSeatList(
          scenario?.players_not_folded_hero_action,
          heroSeat,
          villainSeat,
        )
      : normalizeSeatList(
          scenario?.players_not_folded_villain_action,
          heroSeat,
          villainSeat,
        );

  const extraSeatSet = new Set(extraLiveSeats);
  const extraVillainPool =
    villains.filter((item) => item.id !== villain?.id).length > 0
      ? villains.filter((item) => item.id !== villain?.id)
      : villains;

  return DISPLAY_SEATS.map((seat) => {
    if (seat === heroSeat) {
      return {
        seat,
        label: seat,
        isHero: true,
        isSelectedActor: currentActor === "hero",
        isDimmed: false,
        isFolded: false,
        playerName: "Hero",
        playerSubtitle: scenario?.hero_scenario_name,
        description: scenario
          ? `${scenario.hero_scenario_name} • ${scenario.hero_is_ip ? "IP" : "OOP"}`
          : "Hero",
        stackText: formatStack(session?.hero_stack ?? null),
        actionBubble: actionBubbleForActor(
          scenario,
          session,
          currentActor,
          "hero",
        ),
        iconText: "⭐",
      };
    }

    if (seat === villainSeat) {
      return {
        seat,
        label: seat,
        isVillain: true,
        isSelectedActor: currentActor === "villain",
        isDimmed: false,
        isFolded: false,
        playerName: villain?.display_name ?? "Villain",
        playerSubtitle: villain?.type_label,
        description: villain?.description,
        avatarSrc: villain ? `/villains/${villain.image_name}` : undefined,
        stackText: formatStack(session?.villain_stack ?? null),
        actionBubble: actionBubbleForActor(
          scenario,
          session,
          currentActor,
          "villain",
        ),
        iconText: villain?.display_name?.slice(0, 1)?.toUpperCase() ?? "V",
      };
    }

    const activeExtra = extraSeatSet.has(seat);

    const extraVillainIndex = stableIndexFromSeed(
      `${seat}|${scenario?.id ?? ""}|${villain?.id ?? ""}`,
      Math.max(extraVillainPool.length, 1),
    );

    const extraVillain =
      extraVillainPool.length > 0 ? extraVillainPool[extraVillainIndex] : null;

    return {
      seat,
      label: seat,
      playerName: extraVillain?.display_name ?? "Player",
      playerSubtitle:
        extraVillain?.type_label ?? (activeExtra ? "In hand" : "Out of hand"),
      description:
        extraVillain?.description ??
        (activeExtra
          ? "Displayed for table realism only."
          : "Not involved in the hand."),
      avatarSrc: extraVillain
        ? `/villains/${extraVillain.image_name}`
        : undefined,
      isSelectedActor: false,
      isDimmed: !activeExtra,
      isFolded: !activeExtra,
      stackText: extraSeatStackText(seat, scenario?.id, villain?.id),
      actionBubble: activeExtra ? null : "Fold",
      iconText: extraVillain?.display_name?.slice(0, 1)?.toUpperCase() ?? "•",
    };
  });
}

function initialCurrentActor(
  session: SessionState | null,
  scenario: Scenario | null,
): RangeEditorActor | null {
  if (!scenario) return null;
  const [firstActor, secondActor] = actorOrder(scenario);

  if (!session) return firstActor;

  const firstConfirmed =
    firstActor === "hero"
      ? session.hero_range_confirmed
      : session.villain_range_confirmed;
  const secondConfirmed =
    secondActor === "hero"
      ? session.hero_range_confirmed
      : session.villain_range_confirmed;

  if (!firstConfirmed) return firstActor;
  if (!secondConfirmed) return secondActor;
  return secondActor;
}

function currentButtonLabel(
  session: SessionState | null,
  scenario: Scenario | null,
  actor: RangeEditorActor | null,
): string {
  if (!scenario || !actor) return "Save";
  const [firstActor, secondActor] = actorOrder(scenario);
  return actor === firstActor &&
    !(secondActor === "hero"
      ? session?.hero_range_confirmed
      : session?.villain_range_confirmed)
    ? "Save & Next"
    : "Save & Move to Postflop";
}

function timerDisplayLabel(
  timerSeconds: TrainTimerSeconds,
  timeRemaining: number | null,
): string {
  if (timerSeconds === 0) return "Off";
  if (timeRemaining != null) return `${timeRemaining}s`;
  return `${timerSeconds}s`;
}

function setupHelperText(hasOpponent: boolean, hasScenario: boolean): string {
  if (!hasOpponent) return "Choose an opponent to unlock scenario selection.";
  if (!hasScenario) return "Choose a scenario to begin training.";
  return "Choose a scenario to begin training.";
}

function stepHelperText(
  scenario: Scenario | null,
  currentActor: RangeEditorActor | null,
): string {
  if (!scenario || !currentActor) {
    return "Choose an opponent and scenario to begin training.";
  }

  const [firstActor] = actorOrder(scenario);
  return currentActor === firstActor
    ? "Edit the aggressor range, then save to continue."
    : "Edit the non-aggressor range, then save to move to postflop.";
}

function buildWorkflowSteps(
  scenario: Scenario | null,
  session: SessionState | null,
  currentActor: RangeEditorActor | null,
): WorkflowStep[] {
  if (!scenario) {
    return [
      { key: "setup", label: "Setup", state: "active" },
      {
        key: "step-1",
        label: "Step 1 · Edit Aggressor Range",
        state: "upcoming",
      },
      {
        key: "step-2",
        label: "Step 2 · Edit Non-Aggressor Range",
        state: "upcoming",
      },
    ];
  }

  const [firstActor, secondActor] = actorOrder(scenario);
  const firstConfirmed =
    firstActor === "hero"
      ? !!session?.hero_range_confirmed
      : !!session?.villain_range_confirmed;
  const secondConfirmed =
    secondActor === "hero"
      ? !!session?.hero_range_confirmed
      : !!session?.villain_range_confirmed;

  const stepOneState: WorkflowStep["state"] = firstConfirmed
    ? "complete"
    : currentActor === firstActor
      ? "active"
      : "upcoming";

  const stepTwoState: WorkflowStep["state"] = secondConfirmed
    ? "complete"
    : currentActor === secondActor
      ? "active"
      : "upcoming";

  return [
    { key: "setup", label: "Setup", state: "complete" },
    {
      key: "step-1",
      label: "Step 1 · Edit Aggressor Range",
      state: stepOneState,
    },
    {
      key: "step-2",
      label: "Step 2 · Edit Non-Aggressor Range",
      state: stepTwoState,
    },
  ];
}

function getActiveSetupControl(
  hasOpponent: boolean,
  hasScenario: boolean,
): "opponent" | "scenario" | null {
  if (hasScenario) return null;
  if (!hasOpponent) return "opponent";
  return "scenario";
}

function buttonStyle(
  enabled: boolean,
  isActive: boolean = false,
): CSSProperties {
  return {
    border: isActive
      ? `1px solid ${THEME.primary}`
      : `1px solid ${THEME.border}`,
    background: isActive
      ? THEME.primary
      : "transparent",
    color: enabled ? THEME.text : THEME.textSoft,
    borderRadius: 999,
    padding: "10px 16px",
    fontSize: 14,
    fontWeight: 900,
    cursor: enabled ? "pointer" : "default",
    boxShadow: "none",
    opacity: enabled ? 1 : 0.68,
  };
}

export default function Screen1Page() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const sessionIdFromUrl = searchParams.get("session_id");
  const scenarioIdPrefill = searchParams.get("scenario_id");
  const villainIdPrefill = searchParams.get("villain_profile_id");

  const [mode, setMode] = useState<TrainStudyMode>("train");
  const [villains, setVillains] = useState<VillainProfile[]>([]);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [selectedVillainId, setSelectedVillainId] = useState<string>("");
  const [selectedScenarioId, setSelectedScenarioId] = useState<string>("");
  const [selectedTimerSeconds, setSelectedTimerSeconds] =
    useState<TrainTimerSeconds>(0);
  const [opponentChosenExplicitly, setOpponentChosenExplicitly] =
    useState(false);
  const [session, setSession] = useState<SessionState | null>(null);

  const [heroDefaultBool, setHeroDefaultBool] =
    useState<MatrixBoolState | null>(null);
  const [villainDefaultBool, setVillainDefaultBool] =
    useState<MatrixBoolState | null>(null);
  const [heroCurrentBool, setHeroCurrentBool] =
    useState<MatrixBoolState | null>(null);
  const [villainCurrentBool, setVillainCurrentBool] =
    useState<MatrixBoolState | null>(null);
  const [currentActor, setCurrentActor] = useState<RangeEditorActor | null>(
    null,
  );

  const [isLoading, setIsLoading] = useState(true);
  const [isBusy, setIsBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [scenarioOpen, setScenarioOpen] = useState(false);
  const [opponentOpen, setOpponentOpen] = useState(false);
  const [timerOpen, setTimerOpen] = useState(false);
  const [timeRemaining, setTimeRemaining] = useState<number | null>(null);
  const [timeoutOverlay, setTimeoutOverlay] = useState<TimeoutOverlayState>({
    open: false,
    subtitle: "",
  });

  const overlayTimeoutRef = useRef<number | null>(null);
  const handledTimeoutStepRef = useRef<string | null>(null);
  const autoStartedQuickDrillRef = useRef(false);

  useEffect(() => {
    if (!getStoredAuthToken()) {
      router.replace("/login");
    }
  }, [router]);

  const selectedVillain = useMemo(
    () => villains.find((villain) => villain.id === selectedVillainId) ?? null,
    [villains, selectedVillainId],
  );

  const selectedScenario = useMemo(
    () =>
      scenarios.find((scenario) => scenario.id === selectedScenarioId) ?? null,
    [scenarios, selectedScenarioId],
  );

  const castSeats = useMemo(
    () =>
      buildCastSeats({
        scenario: selectedScenario,
        villain: selectedVillain,
        villains,
        session,
        currentActor,
      }),
    [selectedScenario, selectedVillain, villains, session, currentActor],
  );

  const activeIncludedAction = includedActionForActor(
    selectedScenario,
    currentActor ?? "hero",
  );
  const allowedActions: MatrixAction[] =
    activeIncludedAction === "RAISE" ? ["FOLD", "RAISE"] : ["FOLD", "CALL"];

  const defaultActions = useMemo(() => {
    if (!currentActor) return {} as Record<string, MatrixAction>;
    const source =
      currentActor === "hero" ? heroDefaultBool : villainDefaultBool;
    return boolMatrixToActionMatrix(source, activeIncludedAction);
  }, [currentActor, heroDefaultBool, villainDefaultBool, activeIncludedAction]);

  const currentActions = useMemo(() => {
    if (!currentActor) return {} as Record<string, MatrixAction>;
    const source =
      currentActor === "hero" ? heroCurrentBool : villainCurrentBool;
    return boolMatrixToActionMatrix(source, activeIncludedAction);
  }, [currentActor, heroCurrentBool, villainCurrentBool, activeIncludedAction]);

  const workflowSteps = useMemo(
    () => buildWorkflowSteps(selectedScenario, session, currentActor),
    [selectedScenario, session, currentActor],
  );

  const workflowHelperText = useMemo(() => {
    if (mode !== "train") return "";
    if (!selectedScenario) {
      return setupHelperText(opponentChosenExplicitly, !!selectedScenario);
    }
    return stepHelperText(selectedScenario, currentActor);
  }, [mode, opponentChosenExplicitly, selectedScenario, currentActor]);

  const activeSetupControl = useMemo(
    () =>
      mode === "train"
        ? getActiveSetupControl(opponentChosenExplicitly, !!selectedScenario)
        : null,
    [mode, opponentChosenExplicitly, selectedScenario],
  );

  const isRangePanelActive =
    mode === "train" && !!selectedScenario && !!currentActor;

  const currentStepSignature = useMemo(() => {
    if (mode !== "train") return null;
    if (!selectedScenario || !currentActor || !session) return null;
    return [
      session.session_id,
      selectedScenario.id,
      currentActor,
      session.hero_range_confirmed ? "1" : "0",
      session.villain_range_confirmed ? "1" : "0",
    ].join(":");
  }, [
    mode,
    selectedScenario,
    currentActor,
    session?.session_id,
    session?.hero_range_confirmed,
    session?.villain_range_confirmed,
  ]);

  const timerLabel = useMemo(
    () => timerDisplayLabel(selectedTimerSeconds, timeRemaining),
    [selectedTimerSeconds, timeRemaining],
  );

  async function createSessionForVillain(
    villainId: string,
    trainTimerSeconds: TrainTimerSeconds,
  ): Promise<SessionState> {
    const res = await apiFetch(`${API_BASE}/sessions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        villain_profile_id: villainId,
        train_timer_seconds: trainTimerSeconds,
      }),
    });

    if (!res.ok) {
      const detail = await safeReadError(res);
      throw new Error(detail || `Failed to create session (${res.status})`);
    }

    return (await res.json()) as SessionState;
  }

  async function applyScenarioToSession(
    sessionId: string,
    scenarioId: string,
    trainTimerSeconds: TrainTimerSeconds,
  ): Promise<SessionState> {
    const res = await apiFetch(`${API_BASE}/sessions/${sessionId}/scenario`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        scenario_id: scenarioId,
        seed: 1,
        train_timer_seconds: trainTimerSeconds,
      }),
    });

    if (!res.ok) {
      const detail = await safeReadError(res);
      throw new Error(detail || `Failed to set scenario (${res.status})`);
    }

    return (await res.json()) as SessionState;
  }

  function hydrateRangeEditors(
    nextSession: SessionState,
    scenario: Scenario | null,
  ) {
    if (!scenario) {
      setHeroDefaultBool(null);
      setVillainDefaultBool(null);
      setHeroCurrentBool(null);
      setVillainCurrentBool(null);
      setCurrentActor(null);
      return;
    }

    const nextHeroDefault = boolMatrixFromTokens(scenario.hero_range_tokens);
    const nextVillainDefault = boolMatrixFromTokens(
      scenario.villain_range_tokens,
    );

    setHeroDefaultBool(nextHeroDefault);
    setVillainDefaultBool(nextVillainDefault);
    setHeroCurrentBool(nextSession.hero_range_matrix_saved ?? nextHeroDefault);
    setVillainCurrentBool(
      nextSession.villain_range_matrix_saved ?? nextVillainDefault,
    );
    setCurrentActor(initialCurrentActor(nextSession, scenario));
  }

  async function startOrResetTrainSession(args: {
    villainId: string;
    timerSeconds: TrainTimerSeconds;
    scenarioId?: string;
  }) {
    const { villainId, timerSeconds, scenarioId } = args;
    const nextSession = await createSessionForVillain(villainId, timerSeconds);
    let activeSession = nextSession;

    if (scenarioId) {
      activeSession = await applyScenarioToSession(
        nextSession.session_id,
        scenarioId,
        timerSeconds,
      );
    }

    setSession(activeSession);
    router.replace(
      `/screen-1?session_id=${encodeURIComponent(activeSession.session_id)}`,
    );

    const scenario = scenarioId
      ? (scenarios.find((item) => item.id === scenarioId) ?? null)
      : null;
    hydrateRangeEditors(activeSession, scenario);
  }

  useEffect(() => {
    let isMounted = true;

    async function load() {
      setIsLoading(true);
      setError(null);

      try {
        const [villainsRes, scenariosRes] = await Promise.all([
          apiFetch(`${API_BASE}/villains`, { cache: "no-store" }),
          apiFetch(`${API_BASE}/scenarios`, { cache: "no-store" }),
        ]);

        if (!villainsRes.ok)
          throw new Error(`Failed to load villains (${villainsRes.status})`);
        if (!scenariosRes.ok)
          throw new Error(`Failed to load scenarios (${scenariosRes.status})`);

        const villainsData = (await villainsRes.json()) as VillainProfile[];
        const scenariosData = (await scenariosRes.json()) as Scenario[];

        if (!isMounted) return;

        setVillains(villainsData);
        setScenarios(scenariosData);

        if (!sessionIdFromUrl && isMounted) {
          if (villainIdPrefill) {
            setSelectedVillainId(villainIdPrefill);
            setOpponentChosenExplicitly(true);
          }
          if (scenarioIdPrefill) {
            setSelectedScenarioId(scenarioIdPrefill);
          }
        }

        if (sessionIdFromUrl) {
          const sessionRes = await apiFetch(
            `${API_BASE}/sessions/${sessionIdFromUrl}`,
            {
              cache: "no-store",
            },
          );

          if (sessionRes.ok) {
            const sessionData = (await sessionRes.json()) as SessionState;
            if (!isMounted) return;

            setSession(sessionData);
            setSelectedVillainId(sessionData.villain_profile_id);
            setOpponentChosenExplicitly(!!sessionData.villain_profile_id);
            setSelectedScenarioId(sessionData.scenario_id ?? "");
            setSelectedTimerSeconds(
              (sessionData.train_timer_seconds ?? 0) as TrainTimerSeconds,
            );
            const scenario =
              scenariosData.find(
                (item) => item.id === sessionData.scenario_id,
              ) ?? null;
            hydrateRangeEditors(sessionData, scenario);
          } else if (sessionRes.status === 404) {
            setSession(null);
            setSelectedVillainId("");
            setOpponentChosenExplicitly(false);
            setSelectedScenarioId("");
            setSelectedTimerSeconds(0);
            hydrateRangeEditors(
              {
                session_id: "",
                villain_profile_id: "",
                train_timer_seconds: 0,
                scenario_id: null,
                pot: null,
                hero_stack: null,
                villain_stack: null,
                hero_range_matrix_saved: null,
                hero_tokens_saved: [],
                villain_range_matrix_saved: null,
                villain_tokens_saved: [],
                hero_range_confirmed: false,
                villain_range_confirmed: false,
              },
              null,
            );
          } else {
            throw new Error(`Failed to load session (${sessionRes.status})`);
          }
        }
      } catch (err) {
        if (!isMounted) return;
        setError(
          err instanceof Error ? err.message : "Failed to load preflop setup.",
        );
      } finally {
        if (isMounted) setIsLoading(false);
      }
    }

    void load();

    return () => {
      isMounted = false;
    };
  }, [router, sessionIdFromUrl, scenarioIdPrefill, villainIdPrefill]);

  useEffect(() => {
    if (sessionIdFromUrl || autoStartedQuickDrillRef.current) return;
    if (!villainIdPrefill || !scenarioIdPrefill) return;
    if (!villains.length || !scenarios.length) return;
    autoStartedQuickDrillRef.current = true;
    void startOrResetTrainSession({
      villainId: villainIdPrefill,
      scenarioId: scenarioIdPrefill,
      timerSeconds: selectedTimerSeconds,
    }).catch(() => {
      autoStartedQuickDrillRef.current = false;
    });
  }, [sessionIdFromUrl, villainIdPrefill, scenarioIdPrefill, villains.length, scenarios.length, selectedTimerSeconds]);

  useEffect(() => {
    return () => {
      if (overlayTimeoutRef.current !== null) {
        window.clearTimeout(overlayTimeoutRef.current);
      }
    };
  }, []);

  useEffect(() => {
    if (
      mode !== "train" ||
      !selectedScenario ||
      !currentActor ||
      !session ||
      selectedTimerSeconds <= 0
    ) {
      setTimeRemaining(null);
      handledTimeoutStepRef.current = null;
      return;
    }

    setTimeRemaining(selectedTimerSeconds);
    handledTimeoutStepRef.current = null;
  }, [
    mode,
    selectedScenario?.id,
    currentActor,
    session?.session_id,
    session?.hero_range_confirmed,
    session?.villain_range_confirmed,
    selectedTimerSeconds,
  ]);

  useEffect(() => {
    if (
      mode !== "train" ||
      selectedTimerSeconds <= 0 ||
      !selectedScenario ||
      !currentActor ||
      !session ||
      !currentStepSignature ||
      isBusy ||
      timeoutOverlay.open
    ) {
      return;
    }

    if (timeRemaining == null) return;

    if (timeRemaining <= 0) {
      if (handledTimeoutStepRef.current === currentStepSignature) return;
      handledTimeoutStepRef.current = currentStepSignature;
      void handleTimedSave(currentActor);
      return;
    }

    const timeoutId = window.setTimeout(() => {
      setTimeRemaining((prev) => (prev == null ? prev : prev - 1));
    }, 1000);

    return () => window.clearTimeout(timeoutId);
  }, [
    mode,
    selectedTimerSeconds,
    selectedScenario,
    currentActor,
    session,
    currentStepSignature,
    isBusy,
    timeoutOverlay.open,
    timeRemaining,
  ]);

  async function handleVillainSelect(villainId: string) {
    if (mode !== "train") return;

    setSelectedVillainId(villainId);
    setOpponentChosenExplicitly(true);
    setOpponentOpen(false);
    setScenarioOpen(false);
    setTimerOpen(false);
    setError(null);
    setIsBusy(true);

    try {
      await startOrResetTrainSession({
        villainId,
        timerSeconds: selectedTimerSeconds,
        scenarioId: selectedScenarioId || undefined,
      });
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to switch opponent.",
      );
    } finally {
      setIsBusy(false);
    }
  }

  async function handleTimerSelect(nextTimerSeconds: TrainTimerSeconds) {
    if (mode !== "train") return;

    setSelectedTimerSeconds(nextTimerSeconds);
    setTimerOpen(false);
    setOpponentOpen(false);
    setScenarioOpen(false);
    setError(null);

    if (!selectedVillainId) return;

    setIsBusy(true);
    try {
      await startOrResetTrainSession({
        villainId: selectedVillainId,
        timerSeconds: nextTimerSeconds,
        scenarioId: selectedScenarioId || undefined,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update timer.");
    } finally {
      setIsBusy(false);
    }
  }

  async function handleScenarioSelect(scenarioId: string) {
    if (!selectedVillainId || mode !== "train") return;

    setSelectedScenarioId(scenarioId);
    setScenarioOpen(false);
    setOpponentOpen(false);
    setTimerOpen(false);
    setError(null);
    setIsBusy(true);

    try {
      await startOrResetTrainSession({
        villainId: selectedVillainId,
        timerSeconds: selectedTimerSeconds,
        scenarioId,
      });
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to apply scenario.",
      );
    } finally {
      setIsBusy(false);
    }
  }

  function handleMatrixChange(nextActions: Record<string, MatrixAction>) {
    const nextBool = actionMatrixToBoolMatrix(nextActions);
    if (currentActor === "hero") {
      setHeroCurrentBool(nextBool);
    } else if (currentActor === "villain") {
      setVillainCurrentBool(nextBool);
    }
  }

  function finalizeAfterSave(
    actorSaved: RangeEditorActor,
    updatedSession: SessionState,
    subtitle?: string,
  ) {
    if (!selectedScenario) {
      setIsBusy(false);
      return;
    }

    const [firstActor, secondActor] = actorOrder(selectedScenario);
    const secondConfirmed =
      secondActor === "hero"
        ? updatedSession.hero_range_confirmed
        : updatedSession.villain_range_confirmed;

    const advance = () => {
      if (actorSaved === firstActor && !secondConfirmed) {
        setCurrentActor(secondActor);
        setIsBusy(false);
        return;
      }

      setIsBusy(false);
      router.push(
        `/screen-3?session_id=${encodeURIComponent(updatedSession.session_id)}`,
      );
    };

    if (!subtitle) {
      advance();
      return;
    }

    setTimeoutOverlay({ open: true, subtitle });
    if (overlayTimeoutRef.current !== null) {
      window.clearTimeout(overlayTimeoutRef.current);
    }
    overlayTimeoutRef.current = window.setTimeout(() => {
      setTimeoutOverlay({ open: false, subtitle: "" });
      advance();
    }, 2000);
  }

  async function saveCurrentRange(options?: { timeoutSubtitle?: string }) {
    if (!session || !selectedScenario || !currentActor) return;

    const actorToSave = currentActor;
    const currentBool =
      actorToSave === "hero" ? heroCurrentBool : villainCurrentBool;
    if (!currentBool) return;

    setIsBusy(true);
    setError(null);

    try {
      const res = await apiFetch(
        `${API_BASE}/sessions/${session.session_id}/starting-range`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            actor: actorToSave,
            matrix_state: currentBool,
          }),
        },
      );

      if (!res.ok) {
        const detail = await safeReadError(res);
        throw new Error(detail || `Failed to save range (${res.status})`);
      }

      const updatedSession = (await res.json()) as SessionState;
      setSession(updatedSession);
      finalizeAfterSave(actorToSave, updatedSession, options?.timeoutSubtitle);
    } catch (err) {
      setIsBusy(false);
      setError(err instanceof Error ? err.message : "Failed to save range.");
    }
  }

  async function handleTimedSave(actorToTimeout: RangeEditorActor) {
    if (currentActor !== actorToTimeout) return;
    await saveCurrentRange({
      timeoutSubtitle: "Saving current range and advancing...",
    });
  }

  const saveButtonLabel = currentButtonLabel(
    session,
    selectedScenario,
    currentActor,
  );
  const timerSelectable = mode === "train" && !isLoading && !isBusy;
  const opponentSelectable = mode === "train" && !isLoading && !isBusy;
  const scenarioSelectable =
    mode === "train" &&
    opponentChosenExplicitly &&
    !!selectedVillainId &&
    !isLoading &&
    !isBusy;


  const preflopHeaderControls = (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "flex-end",
        gap: 12,
        flexWrap: "wrap",
      }}
    >
      <ModeSplitToggle mode={mode} onChange={setMode} />

      {mode === "train" ? (
        <div style={{ position: "relative" }}>
          <button
            type="button"
            onClick={() => {
              if (!timerSelectable) return;
              setTimerOpen((open) => !open);
              setOpponentOpen(false);
              setScenarioOpen(false);
            }}
            disabled={!timerSelectable}
            style={buttonStyle(timerSelectable)}
          >
            {`Timer • ${timerDisplayLabel(selectedTimerSeconds, null)}`}
          </button>

          {timerOpen ? (
            <div style={dropdownPanelStyle}>
              {TIMER_OPTIONS.map((option) => (
                <button
                  key={option}
                  type="button"
                  onClick={() => void handleTimerSelect(option)}
                  style={dropdownRowButtonStyle}
                >
                  <div
                    style={{
                      display: "flex",
                      flexDirection: "column",
                      alignItems: "flex-start",
                      gap: 4,
                    }}
                  >
                    <div
                      style={{
                        fontSize: 13.5,
                        fontWeight: 900,
                        color: THEME.text,
                      }}
                    >
                      {option === 0 ? "Off" : `${option} seconds`}
                    </div>
                    <div
                      style={{
                        fontSize: 12.5,
                        color: "var(--text-65)",
                      }}
                    >
                      {option === 0
                        ? "No timer is applied in Train mode."
                        : `Each train step auto-advances after ${option} seconds.`}
                    </div>
                  </div>
                </button>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}

      {mode === "train" ? (
        <div style={{ position: "relative" }}>
          <button
            type="button"
            onClick={() => {
              if (!opponentSelectable) return;
              setOpponentOpen((open) => !open);
              setScenarioOpen(false);
              setTimerOpen(false);
            }}
            disabled={!opponentSelectable}
            style={buttonStyle(opponentSelectable, activeSetupControl === "opponent")}
          >
            {selectedVillain
              ? `Select Opponent • ${selectedVillain.display_name}`
              : "Select Opponent"}
          </button>

          {opponentOpen ? (
            <div style={{ ...dropdownPanelStyle, width: 420 }}>
              {villains.map((villain) => (
                <button
                  key={villain.id}
                  type="button"
                  onClick={() => void handleVillainSelect(villain.id)}
                  style={{ ...dropdownRowButtonStyle, padding: 12 }}
                >
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 12,
                      width: "100%",
                    }}
                  >
                    <Avatar
                      name={villain.display_name}
                      imageSrc={`/villains/${villain.image_name}`}
                      size={42}
                      title={villain.display_name}
                    />
                    <div
                      style={{
                        display: "flex",
                        flexDirection: "column",
                        alignItems: "flex-start",
                        gap: 3,
                        minWidth: 0,
                      }}
                    >
                      <div
                        style={{
                          fontSize: 13.5,
                          fontWeight: 900,
                          color: THEME.text,
                        }}
                      >
                        {villain.display_name} • {villain.type_label}
                      </div>
                      <div
                        style={{
                          fontSize: 12.5,
                          color: "var(--text-65)",
                          lineHeight: 1.35,
                          textAlign: "left",
                        }}
                      >
                        {villain.description}
                      </div>
                    </div>
                  </div>
                </button>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}

      {mode === "train" ? (
        <div style={{ position: "relative" }}>
          <button
            type="button"
            onClick={() => {
              if (!scenarioSelectable) return;
              setScenarioOpen((open) => !open);
              setOpponentOpen(false);
              setTimerOpen(false);
            }}
            disabled={!scenarioSelectable}
            style={buttonStyle(scenarioSelectable, activeSetupControl === "scenario")}
          >
            {selectedScenario
              ? `Select Scenario • ${selectedScenario.display_name}`
              : opponentChosenExplicitly
                ? "Select Scenario"
                : "Select Scenario (choose opponent first)"}
          </button>

          {scenarioOpen ? (
            <div style={dropdownPanelStyle}>
              {scenarios.map((scenario) => (
                <button
                  key={scenario.id}
                  type="button"
                  onClick={() => void handleScenarioSelect(scenario.id)}
                  style={dropdownRowButtonStyle}
                >
                  <div
                    style={{
                      display: "flex",
                      flexDirection: "column",
                      alignItems: "flex-start",
                      gap: 4,
                    }}
                  >
                    <div
                      style={{
                        fontSize: 13.5,
                        fontWeight: 900,
                        color: THEME.text,
                      }}
                    >
                      {scenario.display_name}
                    </div>
                    <div
                      style={{
                        fontSize: 12.5,
                        color: "var(--text-65)",
                      }}
                    >
                      {scenario.hero_scenario_name} vs {scenario.villain_scenario_name}
                    </div>
                  </div>
                </button>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );

  return (
    <main
      style={{
        minHeight: "100vh",
        background:
          `var(--bg)`,
        color: THEME.text,
        padding: "22px 32px 42px",
      }}
    >
      <TimeoutOverlay
        open={timeoutOverlay.open}
        subtitle={timeoutOverlay.subtitle}
      />

      <div style={{ maxWidth: 1500, margin: "0 auto", display: "grid", gap: 18 }}>
        <TrainingHeader
          stepLabel="Step 1 of 2"
          title="Preflop Setup"
          subtitle="Set the scenario, choose the opponent, and shape the starting ranges."
          stage={mode === "train" ? "Train mode" : "Study mode"}
          headerContent={preflopHeaderControls}
        />

        {error ? (
          <div
            style={{
              marginBottom: 16,
              padding: "12px 14px",
              borderRadius: 14,
              border: "1px solid rgba(231,111,81,0.34)",
              background: "rgba(231,111,81,0.10)",
              color: "var(--text)",
              fontSize: 13.5,
              fontWeight: 700,
            }}
          >
            {error}
          </div>
        ) : null}

        {isLoading ? (
          <div style={loadingPanelStyle}>Loading preflop setup…</div>
        ) : mode === "study" ? (
          <WorkbenchStudy />
        ) : (
          <>
            <WorkflowBar
              steps={workflowSteps}
              helperText={workflowHelperText}
              timerLabel={timerLabel}
              showTimer
              showHelper={false}
            />

            <div
              style={{
                display: "grid",
                gridTemplateColumns: "minmax(0, 1.65fr) minmax(360px, 0.95fr)",
                gap: 18,
                alignItems: "start",
              }}
            >
              <div>
                {selectedScenario &&
                currentActor &&
                heroCurrentBool &&
                villainCurrentBool ? (
                  <>
                    <HandMatrix
                      allowedActions={allowedActions}
                      defaultActions={defaultActions}
                      currentActions={currentActions}
                      showDefaultOverlay
                      maxWidth={820}
                      title={titleForActor(
                        currentActor,
                        selectedScenario,
                        selectedVillain,
                      )}
                      onChange={handleMatrixChange}
                    />

                    <div
                      style={{
                        display: "flex",
                        justifyContent: "flex-end",
                        marginTop: 14,
                      }}
                    >
                      <button
                        type="button"
                        onClick={() => void saveCurrentRange()}
                        disabled={isBusy || timeoutOverlay.open}
                        style={{
                          border: `1px solid ${THEME.primary}`,
                          borderRadius: 999,
                          padding: "12px 18px",
                          background: THEME.primary,
                          color: THEME.text,
                          fontSize: 13.5,
                          fontWeight: 950,
                          cursor:
                            isBusy || timeoutOverlay.open
                              ? "default"
                              : "pointer",
                          boxShadow: "none",
                          opacity: isBusy || timeoutOverlay.open ? 0.7 : 1,
                        }}
                      >
                        {isBusy ? "Saving…" : saveButtonLabel}
                      </button>
                    </div>
                  </>
                ) : (
                  <div style={emptyPanelStyle}>
                    {opponentChosenExplicitly
                      ? "Select a scenario to load the default hero and villain ranges."
                      : "Choose an opponent first, then select a scenario to begin training."}
                  </div>
                )}
              </div>

              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: 14,
                }}
              >
                <PreflopTableCast seats={castSeats} />

                <div
                  style={{
                    borderTop: `1px solid ${THEME.border}`,
                    paddingTop: 14,
                    display: "grid",
                    gridTemplateColumns: "1fr 1fr",
                    gap: 12,
                  }}
                >
                  <InfoTile
                    label="Pot Size"
                    value={session?.pot != null ? `${session.pot} bb` : "—"}
                  />
                  <InfoTile
                    label="Position"
                    value={
                      selectedScenario
                        ? selectedScenario.hero_is_ip
                          ? "Hero IP"
                          : "Hero OOP"
                        : "—"
                    }
                  />
                  <InfoTile
                    label="Hero"
                    value={selectedScenario?.hero_scenario_name ?? "—"}
                  />
                  <InfoTile
                    label="Villain"
                    value={selectedScenario?.villain_scenario_name ?? "—"}
                  />
                </div>
              </div>
            </div>
          </>
        )}
      </div>
    </main>
  );
}

function InfoTile({ label, value }: { label: string; value: string }) {
  return (
    <div
      style={{
        minHeight: 76,
        borderTop: `1px solid ${THEME.border}`,
        paddingTop: 12,
        display: "flex",
        flexDirection: "column",
        justifyContent: "space-between",
      }}
    >
      <div
        style={{
          fontSize: 11.5,
          fontWeight: 900,
          letterSpacing: 0.8,
          textTransform: "uppercase",
          color: THEME.textSoft,
        }}
      >
        {label}
      </div>
      <div
        style={{
          fontSize: 15,
          fontWeight: 900,
          color: THEME.text,
        }}
      >
        {value}
      </div>
    </div>
  );
}

const dropdownPanelStyle: CSSProperties = {
  position: "absolute",
  top: "calc(100% + 8px)",
  right: 0,
  zIndex: 30,
  width: 340,
  maxHeight: 420,
  overflowY: "auto",
  borderRadius: 18,
  padding: 10,
  background: "rgba(20,18,16,1)",
  border: `1px solid ${THEME.text}`,
  boxShadow: "0 14px 34px rgba(20,18,16,0.6)",
  display: "flex",
  flexDirection: "column",
  gap: 8,
};

const dropdownRowButtonStyle: CSSProperties = {
  width: "100%",
  border: `1px solid ${THEME.text}`,
  background: "rgba(20,18,16,1)",
  color: "inherit",
  borderRadius: 14,
  padding: 12,
  cursor: "pointer",
  textAlign: "left",
};

const loadingPanelStyle: CSSProperties = {
  minHeight: 320,
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  fontSize: 15,
  fontWeight: 800,
  color: THEME.textMuted,
};

const emptyPanelStyle: CSSProperties = {
  minHeight: 420,
  background: "transparent",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  color: THEME.textMuted,
  fontSize: 14.5,
  fontWeight: 700,
  textAlign: "center",
  padding: 24,
};

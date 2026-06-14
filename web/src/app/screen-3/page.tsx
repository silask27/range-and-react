"use client";

import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { apiFetch } from "../../lib/api";
import Avatar from "../../components/app/Avatar";
import TrainingHeader from "../../components/app/TrainingHeader";
import { getStoredAuthToken, getStoredAuthUser, type AuthUser } from "../../lib/auth";
import { THEME } from "../../lib/theme";
import TimeoutOverlay from "../../components/training/TimeoutOverlay";
import WorkflowBar, { type WorkflowStep } from "../../components/training/WorkflowBar";

type SessionState = {
  session_id: string;
  villain_profile_id: string;
  train_timer_seconds: number | null;
  scenario_id: string | null;
  pot: number | null;
  hero_stack: number | null;
  villain_stack: number | null;
  villain_range_matrix_saved: Record<string, boolean> | null;
  villain_tokens_saved: string[];
};

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
  preflop_aggressor: string;
  default_pot: number;
  hero_range_tokens: string[];
  villain_range_tokens: string[];
  oop_player: "hero" | "villain";
  ip_player: "hero" | "villain";
  first_to_act_postflop: "hero" | "villain";
};

type BettingRoundState = {
  current_bet: number;
  hero_contrib: number;
  villain_contrib: number;
  last_raise_size: number;
  folded: boolean;
};

type ActionEvent = {
  street: "preflop" | "flop" | "turn" | "river";
  actor: "hero" | "villain";
  action: "check" | "bet" | "call" | "raise" | "fold";
  amount: number;
  note: string;
  forced: boolean;
};

type BucketSubgroup = {
  subgroup_name: string;
  combo_count: number;
  holdings_count?: number;
};

type BucketRow = {
  bucket_name: string;
  bucket_percent: number;
  combo_count: number;
  holdings_count: number;
  hands?: Array<{
    label: string;
    subgroup_name?: string;
    live_combos: number;
    max_combos: number;
    combo_cards?: string[][];
  }>;
  subgroups: BucketSubgroup[];
};

type BucketMatrixView = {
  total_live_combos: number;
  hero_range_source: string;
  row_order: string[];
  rows: BucketRow[];
};

type PruneUiRow = {
  bucket_name: string;
  subgroups: BucketSubgroup[];
};

type HandState = {
  hand_id: string;
  session_id: string;
  scenario_id: string;
  villain_profile_id: string;
  pot: number;
  hero_stack: number;
  villain_stack: number;
  hero_hand: [string, string];
  board: string[];
  street: "flop" | "turn" | "river";
  betting_round: BettingRoundState;
  history: {
    events: ActionEvent[];
  };
  villain_range_matrix_saved: Record<string, unknown> | null;
  villain_range_combos_live: Record<string, string[][]>;
  current_actor: "hero" | "villain";
  current_aggressor: "hero" | "villain" | null;
  ui_gate:
    | "hero_to_act"
    | "must_prune_range"
    | "must_fill_response_matrix"
    | "hand_over";
  hand_over: boolean;
  bucket_seed?: number;
  response_matrix_columns: string[];
  response_matrix_saved:
    | {
        street: string;
        columns: string[];
        row_order: string[];
        selections: Record<string, Record<string, string>>;
      }
    | Record<string, never>;
  prune_row_order: string[];
  prune_row_index: number;
  villain_hand_revealed?: boolean;
  bucket_matrix_view: BucketMatrixView;
  current_prune_bucket?: string | null;
  current_prune_row_saved_version?: PruneUiRow | null;
  current_prune_row_original?: PruneUiRow | null;
};

type DebriefPreview = {
  summary: {
    ranging_score: number | null;
    response_score: number | null;
    overall_score: number | null;
  };
  recommendations: string[];
};

type RevealPayload = {
  hand_id: string;
  session_id: string;
  street: string;
  hero_hand: string[];
  villain_hand: string[];
  board: string[];
  pot: number;
  hero_stack: number;
  villain_stack: number;
  hand_over: boolean;
  history: Array<{
    street: string;
    actor: string;
    action: string;
    amount: number;
    note: string;
    forced: boolean;
  }>;
};

type ReplayStep = {
  kind: string;
  street: "preflop" | "flop" | "turn" | "river";
  title: string;
  summary: string;
  board: string[];
  details: Record<string, unknown> | null;
};

type ReplayPayload = {
  hand_id: string;
  session_id: string;
  owner_user_id: string;
  scenario_id: string;
  scenario_display_name: string | null;
  villain_profile_id: string;
  villain_display_name: string | null;
  hero_hand: string[];
  villain_hand: string[];
  final_board: string[];
  pot: number;
  hero_stack: number;
  villain_stack: number;
  review?: ReviewState;
  steps: ReplayStep[];
};

type ReviewState = {
  flagged: boolean;
  sent_to_coaches: boolean;
  status: string;
  member_note?: string | null;
  coach_note?: string | null;
  reviewed_at?: string | null;
};

type PhaseKey = "prune" | "matrix" | "action" | "done" | null;
type ActionTone = "neutral" | "positive" | "negative";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

const HERO_NAME = "Hero";

// Keep interaction requests quick. Final debrief/scoring can still use richer
// result metadata, but Train-mode clicks should not wait on heavy bucket
// recomputes. Railway is noticeably slower than local here, so Screen 3 uses a
// deliberately light Monte Carlo pass for responsive training clicks.
const SCREEN3_ITERS = 8;
const TIMEOUT_OVERLAY_MS = 2000;
const VILLAIN_ACTION_REVEAL_MS = 3000;

const BUCKET_CLASS: Record<string, string> = {
  "Nutted Value": "nutted",
  Value: "value",
  SDV: "sdv",
  Draw: "draw",
  Air: "air",
};

const COLUMN_LABELS: Record<string, string> = {
  check: "If I Check",
  bet_small: "If I Bet Small",
  bet_big: "If I Bet Big",
  call: "If I Call",
  raise: "If I Raise",
};

const RESPONSE_OPTIONS: Record<
  string,
  Array<{ value: string; label: string; semantic: string }>
> = {
  check: [
    { value: "B", label: "B", semantic: "bet" },
    { value: "X", label: "X", semantic: "check" },
  ],
  bet_small: [
    { value: "F", label: "F", semantic: "fold" },
    { value: "C", label: "C", semantic: "call" },
    { value: "R", label: "R", semantic: "raise" },
  ],
  bet_big: [
    { value: "F", label: "F", semantic: "fold" },
    { value: "C", label: "C", semantic: "call" },
    { value: "R", label: "R", semantic: "raise" },
  ],
  raise: [
    { value: "F", label: "F", semantic: "fold" },
    { value: "C", label: "C", semantic: "call" },
    { value: "R", label: "R", semantic: "raise" },
  ],
  call: [
    { value: "P", label: "P", semantic: "passive" },
    { value: "A", label: "A", semantic: "aggressive" },
  ],
};

const RIVER_CHECKBACK_SHOWDOWN_OPTIONS: Array<{
  value: string;
  label: string;
  semantic: string;
}> = [
  { value: "P", label: "W", semantic: "win" },
  { value: "A", label: "L", semantic: "lose" },
];

function Screen3PageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const sessionId = searchParams.get("session_id");
  const handIdFromUrl = searchParams.get("hand_id");
  const isReplayMode = searchParams.get("replay") === "1";
  const replayStepFromUrl = Number(searchParams.get("replay_step") ?? "0");

  const [session, setSession] = useState<SessionState | null>(null);
  const [villain, setVillain] = useState<VillainProfile | null>(null);
  const [scenario, setScenario] = useState<Scenario | null>(null);
  const [hand, setHand] = useState<HandState | null>(null);
  const [reveal, setReveal] = useState<RevealPayload | null>(null);
  const [debriefPreview, setDebriefPreview] = useState<DebriefPreview | null>(null);
  const [replayPayload, setReplayPayload] = useState<ReplayPayload | null>(null);
  const [replayStepIndex, setReplayStepIndex] = useState(0);
  const [reviewDraft, setReviewDraft] = useState({ member_note: "", coach_note: "" });
  const [reviewMessage, setReviewMessage] = useState<string | null>(null);
  const [isSavingReview, setIsSavingReview] = useState(false);
  const [storedUser, setStoredUser] = useState<AuthUser | null>(null);

  const [responseSelections, setResponseSelections] = useState<
    Record<string, Record<string, string>>
  >({});
  const [responseFillSequence, setResponseFillSequence] = useState<
    Array<{ bucket: string; column: string; value: string; elapsed_ms: number }>
  >([]);
  const [stableResponseColumns, setStableResponseColumns] = useState<string[]>([]);
  const [betInput, setBetInput] = useState("");
  const [raiseInput, setRaiseInput] = useState("");

  const [isLoading, setIsLoading] = useState(true);
  const [isSavingMatrix, setIsSavingMatrix] = useState(false);
  const [isSubmittingAction, setIsSubmittingAction] = useState(false);
  const [isPruneBusy, setIsPruneBusy] = useState(false);
  const [isRevealBusy, setIsRevealBusy] = useState(false);
  const [isVillainThinking, setIsVillainThinking] = useState(false);
  const [isTimeoutOverlayOpen, setIsTimeoutOverlayOpen] = useState(false);
  const [timeoutSubtitle, setTimeoutSubtitle] = useState("");
  const [isTimeoutTransitioning, setIsTimeoutTransitioning] = useState(false);
  const [timeLeftSeconds, setTimeLeftSeconds] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const canCoachReview = storedUser?.role === "owner" || storedUser?.role === "admin" || storedUser?.role === "coach";

  const isMountedRef = useRef(true);
  const emptyPruneAutoAdvanceRef = useRef<string | null>(null);
  const handRef = useRef<HandState | null>(null);
  const timedStepSignatureRef = useRef<string | null>(null);
  const activeTimerTargetRef = useRef<number | null>(null);
  const timeoutHandledSignatureRef = useRef<string | null>(null);
  const responseSelectionsRef = useRef<Record<string, Record<string, string>>>({});
  const responseMatrixStartedAtRef = useRef<number | null>(null);
  const responseNodeSignatureRef = useRef<string>("");
  const pruneRowStartedAtRef = useRef<number | null>(null);

  useEffect(() => {
    if (!getStoredAuthToken()) {
      router.replace("/login");
    }
  }, [router]);

  const currentReplayStep = isReplayMode ? replayPayload?.steps[replayStepIndex] ?? null : null;
  const replayHand = useMemo(
    () => buildReplayHandView(hand, replayPayload, replayStepIndex),
    [hand, replayPayload, replayStepIndex],
  );
  const activeHand = replayHand ?? hand;
  const activeResponseSelections = useMemo(() => {
    if (isReplayMode && replayPayload) {
      return getReplayVisibleResponseSelections(replayPayload, replayStepIndex);
    }

    if (
      activeHand?.ui_gate === "must_fill_response_matrix" ||
      activeHand?.ui_gate === "must_prune_range" ||
      activeHand?.ui_gate === "hero_to_act"
    ) {
      if (hasAnySelection(responseSelections)) return responseSelections;
      return savedResponseSelectionsFromHand(activeHand);
    }

    return {};
  }, [activeHand, isReplayMode, replayPayload, replayStepIndex, responseSelections]);
  const activeStableColumns = currentReplayStep ? [] : stableResponseColumns;

  const responseColumns = useMemo(
    () => resolveResponseColumns(activeHand, activeStableColumns),
    [activeHand, activeStableColumns],
  );
  const displayResponseColumns = useMemo(
    () => resolveDisplayResponseColumns(activeHand, responseColumns, activeResponseSelections),
    [activeHand, responseColumns, activeResponseSelections],
  );

  const displayedBucketRows = useMemo(() => {
    if (!activeHand) return [];
    return getDisplayedBucketRows(activeHand, isReplayMode);
  }, [activeHand, isReplayMode]);

  const currentPruneBucket = useMemo(() => {
    if (!activeHand) return null;
    if (activeHand.current_prune_bucket !== undefined) {
      return activeHand.current_prune_bucket ?? null;
    }
    return activeHand.prune_row_order[activeHand.prune_row_index] ?? null;
  }, [activeHand]);

  const currentPruneRow = useMemo(() => {
    if (!activeHand || !currentPruneBucket) return null;
    return (
      displayedBucketRows.find((row) => row.bucket_name === currentPruneBucket) ??
      null
    );
  }, [displayedBucketRows, currentPruneBucket, activeHand]);

  const currentPruneSubgroups = useMemo(() => {
    if (!activeHand || !currentPruneRow) return [];
    return getDisplayedPruneSubgroups(currentPruneRow, activeHand);
  }, [currentPruneRow, activeHand]);

  const activeHighlightActor: "hero" | "villain" | null = activeHand?.hand_over
    ? null
    : isVillainThinking
      ? "villain"
      : activeHand?.current_actor ?? null;

  const heroToCall = activeHand ? getToCallForHero(activeHand) : 0;
  const canSaveMatrix =
    !isReplayMode &&
    activeHand?.ui_gate === "must_fill_response_matrix" &&
    (displayedBucketRows.length === 0 ||
      areSelectionsComplete(
        displayedBucketRows,
        responseColumns,
        activeResponseSelections,
      ));

  const currentStep = getCurrentStepKey(activeHand?.ui_gate, activeHand?.hand_over, isVillainThinking);
  const gateLabel = isVillainThinking
    ? "Villain Thinking"
    : activeHand
      ? formatGateLabel(activeHand.ui_gate)
      : "";
  const headerSubtitle = getScreenSubtitle(activeHand, isVillainThinking);
  const timedStepSignature = useMemo(
    () => isReplayMode ? null : getTimedStepSignature(activeHand, isVillainThinking, isTimeoutTransitioning),
    [activeHand, isVillainThinking, isTimeoutTransitioning, isReplayMode],
  );
  const workflowSteps = useMemo(
    () => buildWorkflowSteps(currentStep, activeHand?.hand_over ?? false, scenario?.hero_is_ip === false),
    [currentStep, activeHand?.hand_over, scenario?.hero_is_ip],
  );
  const workflowHelperText = useMemo(
    () => getWorkflowHelperText(activeHand, isVillainThinking),
    [activeHand, isVillainThinking],
  );
  const configuredTimerSeconds = isReplayMode ? 0 : session?.train_timer_seconds ?? 0;
  const timerLabel = getWorkflowTimerLabel(
    configuredTimerSeconds,
    timeLeftSeconds,
    Boolean(timedStepSignature),
  );

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    handRef.current = hand;
  }, [hand]);

  useEffect(() => {
    responseSelectionsRef.current = responseSelections;
  }, [responseSelections]);

  useEffect(() => {
    setStoredUser(getStoredAuthUser());
  }, []);

  useEffect(() => {
    setReviewDraft({
      member_note: replayPayload?.review?.member_note ?? "",
      coach_note: replayPayload?.review?.coach_note ?? "",
    });
    setReviewMessage(null);
  }, [replayPayload?.hand_id, replayPayload?.review?.member_note, replayPayload?.review?.coach_note]);


  useEffect(() => {
    let isMounted = true;
    let loadingResolvedEarly = false;

    async function boot() {
      if (!sessionId && !isReplayMode) {
        router.replace("/screen-1");
        return;
      }
      if (isReplayMode && !handIdFromUrl) {
        setError("A hand id is required to replay a saved hand.");
        setIsLoading(false);
        return;
      }

      setIsLoading(true);
      setError(null);

      try {
        let replayData: ReplayPayload | null = null;
        let activeSessionId = sessionId;

        if (isReplayMode && handIdFromUrl) {
          const replayRes = await apiFetchWithRetry(`${API_BASE}/results/hand/${encodeURIComponent(handIdFromUrl)}/replay`, {
            cache: "no-store",
          });
          if (!replayRes.ok) {
            const detail = await safeReadError(replayRes);
            throw new Error(detail || `Failed to load replay (${replayRes.status})`);
          }
          replayData = expandReplayPayloadSteps((await replayRes.json()) as ReplayPayload);
          activeSessionId = activeSessionId || replayData.session_id;
        }

        if (!activeSessionId) {
          throw new Error("Replay session was not found.");
        }

        const sessionRes = await apiFetchWithRetry(`${API_BASE}/sessions/${activeSessionId}`, {
          cache: "no-store",
        });

        if (!sessionRes.ok) {
          throw new Error(`Failed to load session (${sessionRes.status})`);
        }

        const sessionData = (await sessionRes.json()) as SessionState;

        const [villainRes, scenariosRes] = await Promise.all([
          apiFetchWithRetry(`${API_BASE}/villains/${sessionData.villain_profile_id}`, {
            cache: "no-store",
          }),
          apiFetchWithRetry(`${API_BASE}/scenarios`, { cache: "no-store" }),
        ]);

        if (!villainRes.ok) {
          throw new Error(`Failed to load villain (${villainRes.status})`);
        }
        if (!scenariosRes.ok) {
          throw new Error(`Failed to load scenarios (${scenariosRes.status})`);
        }

        const villainData = (await villainRes.json()) as VillainProfile;
        const scenarioList = (await scenariosRes.json()) as Scenario[];
        const scenarioData =
          scenarioList.find((item) => item.id === sessionData.scenario_id) ?? null;

        if (!scenarioData) {
          throw new Error("Scenario not found for Screen 3.");
        }

        const handRes = isReplayMode && handIdFromUrl
          ? await apiFetchWithRetry(`${API_BASE}/hands/${encodeURIComponent(handIdFromUrl)}?iters=${SCREEN3_ITERS}`, {
              cache: "no-store",
            })
          : await apiFetchWithRetry(`${API_BASE}/hands/start`, {
              method: "POST",
              headers: {
                "Content-Type": "application/json",
              },
              body: JSON.stringify({
                session_id: activeSessionId,
                hand_id: handIdFromUrl,
                iters: SCREEN3_ITERS,
              }),
            });

        if (!handRes.ok) {
          const detail = await safeReadError(handRes);
          throw new Error(detail || `Failed to start hand (${handRes.status})`);
        }

        let handData = (await handRes.json()) as HandState;

        if (
          handData.ui_gate === "must_prune_range" &&
          (!handData.prune_row_order || handData.prune_row_order.length === 0)
        ) {
          handData = await startPruneMode(handData.hand_id);
        }

        if (!isMounted) return;

        setSession(sessionData);
        setVillain(villainData);
        setScenario(scenarioData);
        if (replayData) {
          const boundedReplayStep = Math.max(
            0,
            Math.min(
              Number.isFinite(replayStepFromUrl) ? replayStepFromUrl : 0,
              Math.max(0, replayData.steps.length - 1),
            ),
          );
          if (replayData.steps[boundedReplayStep]?.street === "preflop") {
            router.replace(
              `/screen-1?session_id=${encodeURIComponent(replayData.session_id)}&hand_id=${encodeURIComponent(replayData.hand_id)}&replay=1&replay_step=${boundedReplayStep}`,
            );
            return;
          }
          setReplayPayload(replayData);
          setReplayStepIndex(boundedReplayStep);
          setReveal({
            hand_id: replayData.hand_id,
            session_id: replayData.session_id,
            street: "river",
            hero_hand: replayData.hero_hand,
            villain_hand: replayData.villain_hand,
            board: replayData.final_board,
            pot: replayData.pot,
            hero_stack: replayData.hero_stack,
            villain_stack: replayData.villain_stack,
            hand_over: true,
            history: [],
          });
          setHand(handData);
          return;
        }

        const initialPreviewHand = buildInitialVillainPausePreview(
          handData,
          sessionData,
          scenarioData,
        );

        if (initialPreviewHand) {
          setHand(initialPreviewHand);
          setIsVillainThinking(true);
          setIsLoading(false);
          loadingResolvedEarly = true;

          await sleep(VILLAIN_ACTION_REVEAL_MS);
          if (!isMountedRef.current || !isMounted) return;

          setIsVillainThinking(false);
          setHand(handData);
          return;
        }

        setHand(handData);
      } catch (err) {
        if (!isMounted) return;
        setError(trainingServerErrorMessage(err));
      } finally {
        if (isMounted && !loadingResolvedEarly) {
          setIsLoading(false);
        }
      }
    }

    void boot();

    return () => {
      isMounted = false;
    };
  }, [handIdFromUrl, router, sessionId, isReplayMode, replayStepFromUrl]);

  useEffect(() => {
    if (!hand) return;
    if (isReplayMode) return;

    if (
      hand.ui_gate === "must_prune_range" &&
      (!hand.prune_row_order || hand.prune_row_order.length === 0)
    ) {
      void ensurePruneStarted(hand.hand_id);
      return;
    }

    const resolvedColumns = resolveResponseColumns(hand, stableResponseColumns);
    if (
      resolvedColumns.length &&
      resolvedColumns.join("|") !== stableResponseColumns.join("|")
    ) {
      setStableResponseColumns(resolvedColumns);
    }

    const responseNodeSignature = getResponseNodeSignature(hand, resolvedColumns);
    const isNewResponseNode =
      hand.ui_gate === "must_fill_response_matrix" &&
      responseNodeSignature !== responseNodeSignatureRef.current;
    if (isNewResponseNode) {
      responseMatrixStartedAtRef.current = Date.now();
      setResponseFillSequence([]);
    }
    const nextSelections = initializeSelectionsFromHand(
      hand,
      resolvedColumns,
      isNewResponseNode ? undefined : responseSelectionsRef.current,
      hand.ui_gate !== "must_fill_response_matrix",
    );
    setResponseSelections(nextSelections);
    if (hand.ui_gate === "must_fill_response_matrix") {
      responseNodeSignatureRef.current = responseNodeSignature;
    }

    if (hand.betting_round.current_bet > 0) {
      const toCall = getToCallForHero(hand);
      setRaiseInput(
        toCall > 0 ? String(hand.betting_round.current_bet + toCall) : "",
      );
    } else {
      setRaiseInput("");
    }
  }, [hand, stableResponseColumns, isReplayMode]);


  useEffect(() => {
    if (isReplayMode) return;
    const durationSeconds = session?.train_timer_seconds ?? 0;

    if (durationSeconds <= 0 || !timedStepSignature) {
      setTimeLeftSeconds(null);
      timedStepSignatureRef.current = timedStepSignature;
      activeTimerTargetRef.current = null;
      return;
    }

    if (timedStepSignatureRef.current !== timedStepSignature) {
      timedStepSignatureRef.current = timedStepSignature;
      timeoutHandledSignatureRef.current = null;
      activeTimerTargetRef.current = Date.now() + durationSeconds * 1000;
      setTimeLeftSeconds(durationSeconds);
    }

    const tick = () => {
      const targetAt = activeTimerTargetRef.current;
      if (!targetAt) return;

      const remainingMs = targetAt - Date.now();
      const nextSeconds = Math.max(0, Math.ceil(remainingMs / 1000));
      setTimeLeftSeconds(nextSeconds);

      if (
        remainingMs <= 0 &&
        timeoutHandledSignatureRef.current !== timedStepSignature
      ) {
        timeoutHandledSignatureRef.current = timedStepSignature;
        void handleTimedStepExpiry();
      }
    };

    tick();
    const intervalId = window.setInterval(tick, 250);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [session?.train_timer_seconds, timedStepSignature, isReplayMode]);

  useEffect(() => {
    if (isReplayMode) return;
    if (!hand || hand.ui_gate !== "must_prune_range" || isPruneBusy || isTimeoutTransitioning) return;
    if (!currentPruneBucket) return;

    const shouldAutoAdvance = currentPruneSubgroups.length === 0;
    if (!shouldAutoAdvance) return;

    const key = `${hand.hand_id}:${hand.street}:${hand.prune_row_index}:${currentPruneBucket}`;
    if (emptyPruneAutoAdvanceRef.current === key) return;

    emptyPruneAutoAdvanceRef.current = key;
    void handlePruneSaveRow();
  }, [hand, currentPruneBucket, currentPruneSubgroups, isPruneBusy, isTimeoutTransitioning, isReplayMode]);

  useEffect(() => {
    pruneRowStartedAtRef.current = currentPruneBucket ? Date.now() : null;
  }, [currentPruneBucket]);

  async function applyHandUpdateWithVillainPause(
    previousHand: HandState | null,
    nextHand: HandState,
  ) {
    const shouldPause =
      previousHand !== null && hasNewVillainAction(previousHand, nextHand);

    if (!shouldPause) {
      if (!isMountedRef.current) return;
      setIsVillainThinking(false);
      setHand(nextHand);
      return;
    }

    if (!isMountedRef.current) return;

    const previewHand = buildVillainPausePreview(previousHand, nextHand);
    setHand(previewHand ?? nextHand);
    setIsVillainThinking(true);
    await sleep(VILLAIN_ACTION_REVEAL_MS);

    if (!isMountedRef.current) return;

    setIsVillainThinking(false);
    setHand(nextHand);
  }

  function goToReplayStep(nextIndex: number) {
    if (!replayPayload) return;
    const bounded = Math.max(0, Math.min(nextIndex, replayPayload.steps.length - 1));
    const targetStep = replayPayload.steps[bounded];
    if (targetStep?.street === "preflop") {
      router.push(
        `/screen-1?session_id=${encodeURIComponent(replayPayload.session_id)}&hand_id=${encodeURIComponent(replayPayload.hand_id)}&replay=1&replay_step=${bounded}`,
      );
      return;
    }
    setReplayStepIndex(bounded);
  }

  async function ensurePruneStarted(handId: string) {
    try {
      const updated = await startPruneMode(handId);
      setHand(updated);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to initialize prune mode.",
      );
    }
  }

  async function saveFullPruneStep(handId: string): Promise<HandState> {
    const res = await apiFetchWithRetry(`${API_BASE}/prune/save-step`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        hand_id: handId,
        iters: SCREEN3_ITERS,
        bucket_matrix_view: handRef.current?.bucket_matrix_view,
      }),
    });

    if (!res.ok) {
      const detail = await safeReadError(res);
      throw new Error(detail || `Failed to save prune step (${res.status})`);
    }

    return (await res.json()) as HandState;
  }

  async function saveResponseMatrixRequest(
    handId: string,
    selections: Record<string, Record<string, string>>,
    allowPartial = false,
  ): Promise<HandState> {
    const rowOrder = displayedBucketRows.map((row) => row.bucket_name);
    const normalizedSelections = filterSelectionsForRowsAndColumns(
      selections,
      rowOrder,
      responseColumns,
    );
    const visibleRows = new Set(rowOrder);
    const visibleColumns = new Set(responseColumns);
    const normalizedFillSequence = responseFillSequence.filter(
      (item) => visibleRows.has(item.bucket) && visibleColumns.has(item.column),
    );

    const res = await apiFetchWithRetry(`${API_BASE}/response-matrix/save`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        hand_id: handId,
        iters: SCREEN3_ITERS,
        selections: normalizedSelections,
        row_order: rowOrder,
        fill_sequence: normalizedFillSequence,
        bucket_matrix_view: handRef.current?.bucket_matrix_view,
        allow_partial: allowPartial,
        save_reason: allowPartial ? "timer_expired" : "manual",
      }),
    });

    if (!res.ok) {
      const detail = await safeReadError(res);
      throw new Error(detail || `Failed to save matrix (${res.status})`);
    }

    return (await res.json()) as HandState;
  }

  async function refreshCurrentHand(handId: string): Promise<HandState> {
    const res = await apiFetchWithRetry(
      `${API_BASE}/hands/${encodeURIComponent(handId)}?iters=${SCREEN3_ITERS}`,
      {
        cache: "no-store",
      },
    );

    if (!res.ok) {
      const detail = await safeReadError(res);
      throw new Error(detail || `Failed to refresh hand (${res.status})`);
    }

    return (await res.json()) as HandState;
  }

  async function submitHeroActionRequest(
    handId: string,
    action: string,
    amount?: number,
  ): Promise<HandState> {
    let res: Response;
    try {
      res = await apiFetchWithRetry(`${API_BASE}/actions/hero`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          hand_id: handId,
          action,
          amount,
          iters: SCREEN3_ITERS,
        }),
      });
    } catch (err) {
      throw new Error(err instanceof Error && err.message !== "Failed to fetch"
        ? err.message
        : "Could not reach the training server. Please retry the action; your hand state is still saved.");
    }

    if (!res.ok) {
      const detail = await safeReadError(res);
      throw new Error(detail || `Failed to apply action (${res.status})`);
    }

    return (await res.json()) as HandState;
  }

  async function normalizePostActionHand(updated: HandState): Promise<HandState> {
    if (
      updated.ui_gate === "must_prune_range" &&
      (!updated.prune_row_order || updated.prune_row_order.length === 0)
    ) {
      return startPruneMode(updated.hand_id);
    }

    return updated;
  }

  async function runTimeoutTransition(
    subtitle: string,
    request: () => Promise<HandState>,
    options?: {
      clearBetInput?: boolean;
      clearRaiseInput?: boolean;
    },
  ) {
    const previousHand = handRef.current;
    if (!previousHand) return;

    setIsTimeoutTransitioning(true);
    setTimeoutSubtitle(subtitle);
    setIsTimeoutOverlayOpen(true);
    setError(null);

    try {
      let [updated] = await Promise.all([request(), sleep(TIMEOUT_OVERLAY_MS)]);
      updated = await normalizePostActionHand(updated);

      if (!isMountedRef.current) return;

      setIsTimeoutOverlayOpen(false);
      setTimeoutSubtitle("");

      await applyHandUpdateWithVillainPause(previousHand, updated);
      setReveal(null);
      setDebriefPreview(null);

      if (options?.clearBetInput) {
        setBetInput("");
      }
      if (options?.clearRaiseInput) {
        setRaiseInput("");
      }
    } catch (err) {
      if (!isMountedRef.current) return;
      setIsTimeoutOverlayOpen(false);
      setTimeoutSubtitle("");
      setError(
        err instanceof Error ? err.message : "Failed to advance timed step.",
      );
    } finally {
      if (isMountedRef.current) {
        setIsTimeoutTransitioning(false);
      }
    }
  }

  async function handleTimedStepExpiry() {
    const currentHand = handRef.current;
    if (!currentHand || currentHand.hand_over || isVillainThinking) return;

    if (currentHand.ui_gate === "must_prune_range") {
      await runTimeoutTransition(
        "Saving current range and advancing...",
        () => saveFullPruneStep(currentHand.hand_id),
      );
      return;
    }

    if (currentHand.ui_gate === "must_fill_response_matrix") {
      await runTimeoutTransition(
        "Saving current matrix and advancing...",
        () =>
          saveResponseMatrixRequest(
            currentHand.hand_id,
            responseSelectionsRef.current,
            true,
          ),
      );
      return;
    }

    if (currentHand.ui_gate === "hero_to_act") {
      const toCall = getToCallForHero(currentHand);

      if (toCall > 0) {
        await runTimeoutTransition(
          "No action selected. Hero folds.",
          () => submitHeroActionRequest(currentHand.hand_id, "fold"),
        );
        return;
      }

      await runTimeoutTransition(
        "No action selected. Hero checks.",
        () => submitHeroActionRequest(currentHand.hand_id, "check"),
      );
    }
  }

  async function startPruneMode(handId: string): Promise<HandState> {
    const res = await apiFetchWithRetry(`${API_BASE}/prune/start`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ hand_id: handId, iters: SCREEN3_ITERS }),
    });

    if (!res.ok) {
      const detail = await safeReadError(res);
      throw new Error(detail || `Failed to start prune mode (${res.status})`);
    }

    return (await res.json()) as HandState;
  }

  function updateSelection(bucketName: string, column: string, value: string) {
    const startedAt = responseMatrixStartedAtRef.current ?? Date.now();
    responseMatrixStartedAtRef.current = startedAt;
    setResponseFillSequence((prev) => [
      ...prev,
      {
        bucket: bucketName,
        column,
        value,
        elapsed_ms: Math.max(0, Date.now() - startedAt),
      },
    ]);
    setResponseSelections((prev) => ({
      ...prev,
      [bucketName]: {
        ...(prev[bucketName] ?? {}),
        [column]: value,
      },
    }));
  }

  async function handleSaveResponseMatrix() {
    if (!hand) return;

    setIsSavingMatrix(true);
    setError(null);
    const previousHand = hand;

    try {
      const rowOrder = displayedBucketRows.map((row) => row.bucket_name);
      const normalizedSelections = filterSelectionsForRowsAndColumns(
        responseSelections,
        rowOrder,
        responseColumns,
      );
      const optimisticHand: HandState = {
        ...previousHand,
        ui_gate: "hero_to_act",
        response_matrix_saved: {
          street: previousHand.street,
          columns: responseColumns,
          row_order: rowOrder,
          selections: normalizedSelections,
        },
      };

      setHand(optimisticHand);

      const updated = await saveResponseMatrixRequest(
        hand.hand_id,
        normalizedSelections,
      );
      await applyHandUpdateWithVillainPause(previousHand, updated);
    } catch (err) {
      setHand(previousHand);
      setError(
        err instanceof Error ? err.message : "Failed to save response matrix.",
      );
    } finally {
      setIsSavingMatrix(false);
    }
  }

  async function handleHeroAction(action: string, amount?: number) {
    if (!hand) return;

    setIsSubmittingAction(true);
    setError(null);

    try {
      const previousHand = hand;
      const useImmediateVillainPause = shouldStartImmediateVillainPause(previousHand, action);
      const requestPromise = submitHeroActionRequest(hand.hand_id, action, amount)
        .then((updated) => normalizePostActionHand(updated));

      if (useImmediateVillainPause) {
        setHand(buildImmediateHeroActionPreview(previousHand, action, amount));
        setIsVillainThinking(true);
        const [updated] = await Promise.all([
          requestPromise,
          sleep(VILLAIN_ACTION_REVEAL_MS),
        ]);
        if (!isMountedRef.current) return;
        setIsVillainThinking(false);
        setHand(updated);
      } else {
        const updated = await requestPromise;
        await applyHandUpdateWithVillainPause(previousHand, updated);
      }
      setReveal(null);
      setDebriefPreview(null);

      if (action === "bet") {
        setBetInput("");
      }
      if (action === "raise") {
        setRaiseInput("");
      }
    } catch (err) {
      setIsVillainThinking(false);
      const message = err instanceof Error ? err.message : "Failed to apply action.";
      if (
        hand &&
        (message.includes("not in hero_to_act gate") ||
          message.includes("current gate="))
      ) {
        try {
          const latest = await refreshCurrentHand(hand.hand_id);
          setHand(await normalizePostActionHand(latest));
          setError(null);
        } catch {
          setError(message);
        }
      } else {
        setError(message);
      }
    } finally {
      setIsSubmittingAction(false);
    }
  }

  async function saveReplayReviewNote(markReviewed = false) {
    if (!replayPayload) return;
    setIsSavingReview(true);
    setReviewMessage(null);
    try {
      const body = canCoachReview
        ? { coach_note: reviewDraft.coach_note, mark_reviewed: markReviewed }
        : { member_note: reviewDraft.member_note };
      const res = await apiFetchWithRetry(`${API_BASE}/results/hand/${encodeURIComponent(replayPayload.hand_id)}/review`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Unable to save replay note.");
      setReplayPayload((current) => current ? { ...current, review: data.review as ReviewState } : current);
      setReviewMessage(markReviewed ? "Marked reviewed." : "Replay note saved.");
    } catch (err) {
      setReviewMessage(err instanceof Error ? err.message : "Unable to save replay note.");
    } finally {
      setIsSavingReview(false);
    }
  }

  async function handlePruneRemoveSubgroup(subgroupName: string) {
    if (!hand) return;

    setIsPruneBusy(true);
    setError(null);

    try {
      const res = await apiFetchWithRetry(`${API_BASE}/prune/remove-subgroup`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          hand_id: hand.hand_id,
          subgroup_name: subgroupName,
          bucket_matrix_view: hand.bucket_matrix_view,
          elapsed_ms: Math.max(
            0,
            Date.now() - (pruneRowStartedAtRef.current ?? Date.now()),
          ),
          iters: SCREEN3_ITERS,
        }),
      });

      if (!res.ok) {
        const detail = await safeReadError(res);
        throw new Error(detail || `Failed to remove subgroup (${res.status})`);
      }

      const updated = (await res.json()) as HandState;
      setHand(updated);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to remove subgroup.",
      );
    } finally {
      setIsPruneBusy(false);
    }
  }

  async function handlePruneRevert() {
    if (!hand) return;

    setIsPruneBusy(true);
    setError(null);

    try {
      const res = await apiFetchWithRetry(`${API_BASE}/prune/revert`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ hand_id: hand.hand_id, iters: SCREEN3_ITERS }),
      });

      if (!res.ok) {
        const detail = await safeReadError(res);
        throw new Error(detail || `Failed to revert row (${res.status})`);
      }

      const updated = (await res.json()) as HandState;
      setHand(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to revert row.");
    } finally {
      setIsPruneBusy(false);
    }
  }

  async function handlePruneSaveRow() {
    if (!hand) return;

    setIsPruneBusy(true);
    setError(null);

    try {
      const previousHand = hand;

      const res = await apiFetchWithRetry(`${API_BASE}/prune/save-row`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          hand_id: hand.hand_id,
          iters: SCREEN3_ITERS,
          bucket_matrix_view: hand.bucket_matrix_view,
        }),
      });

      if (!res.ok) {
        const detail = await safeReadError(res);
        throw new Error(detail || `Failed to save prune row (${res.status})`);
      }

      const updated = (await res.json()) as HandState;
      await applyHandUpdateWithVillainPause(previousHand, updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save prune row.");
    } finally {
      setIsPruneBusy(false);
    }
  }

  async function handlePruneNoChanges() {
    if (!hand) return;

    setIsPruneBusy(true);
    setError(null);

    try {
      const previousHand = hand;
      const updated = await saveFullPruneStep(hand.hand_id);
      await applyHandUpdateWithVillainPause(previousHand, updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save prune step.");
    } finally {
      setIsPruneBusy(false);
    }
  }

  async function handleReveal() {
    if (!hand) return;

    setIsRevealBusy(true);
    setError(null);

    try {
      const res = await apiFetchWithRetry(`${API_BASE}/reveal/${hand.hand_id}`, {
        cache: "no-store",
      });

      if (!res.ok) {
        const detail = await safeReadError(res);
        throw new Error(detail || `Failed to reveal hand (${res.status})`);
      }

      const data = (await res.json()) as RevealPayload;
      setReveal(data);

      try {
        const debriefRes = await apiFetchWithRetry(`${API_BASE}/results/hand/${hand.hand_id}`, { cache: "no-store" });
        if (debriefRes.ok) {
          const debriefData = (await debriefRes.json()) as { summary: DebriefPreview["summary"]; recommendations: string[] };
          setDebriefPreview({ summary: debriefData.summary, recommendations: debriefData.recommendations.slice(0, 3) });
        }
      } catch {
        setDebriefPreview(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to reveal hand.");
    } finally {
      setIsRevealBusy(false);
    }
  }

  const topActor = useMemo(() => {
    if (!scenario || !villain) return null;
    return scenario.oop_player === "hero"
      ? buildHeroActor(scenario, activeHand)
      : buildVillainActor(scenario, villain, activeHand);
  }, [scenario, villain, activeHand]);

  const bottomActor = useMemo(() => {
    if (!scenario || !villain) return null;
    return scenario.oop_player === "hero"
      ? buildVillainActor(scenario, villain, activeHand)
      : buildHeroActor(scenario, activeHand);
  }, [scenario, villain, activeHand]);

  return (
    <main className="screen3-shell">
      {isLoading ? (
        <div className="screen3-state screen3-deal-state">
          <div className="screen3-deal-animation" aria-hidden="true">
            <div className="screen3-deal-card screen3-deal-card-a">A</div>
            <div className="screen3-deal-card screen3-deal-card-b">K</div>
            <div className="screen3-deal-card screen3-deal-card-c">Q</div>
          </div>
          <p className="screen3-deal-title">Dealing Cards...</p>
        </div>
      ) : error && !activeHand ? (
        <div className="screen3-state">
          <div className="section-stack" style={{ alignItems: "center" }}>
            <p className="screen3-error-title">Could not load postflop</p>
            <p className="muted screen3-center-copy">{error}</p>
            <button
              className="btn btn-primary"
              type="button"
              onClick={() => window.location.reload()}
            >
              Reload
            </button>
          </div>
        </div>
      ) : !activeHand || !scenario || !villain || !session ? (
        <div className="screen3-state">
          <p className="muted">Missing hand data.</p>
        </div>
      ) : (
        <div className="screen3-wrap">
          <TrainingHeader
            stepLabel={isReplayMode ? `Replay ${Math.min(replayStepIndex + 1, replayPayload?.steps.length ?? 1)} of ${replayPayload?.steps.length ?? 1}` : "Step 2 of 2"}
            title="Postflop Training"
            subtitle={headerSubtitle}
            subtitleMinHeight="3.4em"
            stage={`${scenario.display_name} · ${activeHand.street.toUpperCase()}`}
          />

          {!isReplayMode ? (
            <WorkflowBar
              steps={workflowSteps}
              helperText={workflowHelperText}
              timerLabel={timerLabel}
              showTimer
              showHelper={false}
            />
          ) : null}

          {isReplayMode && replayPayload?.review ? (
            <section className="screen3-replay-note-panel">
              <div className="screen3-replay-note-copy">
                <div className="screen3-replay-kicker">Coach notes</div>
                <div className="screen3-replay-note-title">Replay discussion</div>
                <div className="screen3-replay-note-meta">
                  Status: {replayPayload.review.status || "flagged"}
                  {replayPayload.review.reviewed_at ? ` · Reviewed ${formatShortDate(replayPayload.review.reviewed_at)}` : ""}
                </div>
              </div>
              <div className="screen3-replay-note-grid">
                <label className="screen3-replay-note-field">
                  <span>Member note</span>
                  <textarea
                    value={reviewDraft.member_note}
                    onChange={(event) => setReviewDraft((current) => ({ ...current, member_note: event.target.value }))}
                    disabled={canCoachReview}
                    placeholder="No member note yet."
                  />
                </label>
                <label className="screen3-replay-note-field">
                  <span>Coach comment</span>
                  <textarea
                    value={reviewDraft.coach_note}
                    onChange={(event) => setReviewDraft((current) => ({ ...current, coach_note: event.target.value }))}
                    disabled={!canCoachReview}
                    placeholder={canCoachReview ? "Add the coaching point for this replay." : "No coach comment yet."}
                  />
                </label>
              </div>
              <div className="screen3-replay-note-actions">
                {reviewMessage ? <span className="screen3-replay-note-message">{reviewMessage}</span> : null}
                <button type="button" className="btn btn-ghost" onClick={() => void saveReplayReviewNote(false)} disabled={isSavingReview}>
                  {isSavingReview ? "Saving..." : "Save note"}
                </button>
                {canCoachReview ? (
                  <button type="button" className="btn btn-primary" onClick={() => void saveReplayReviewNote(true)} disabled={isSavingReview}>
                    Mark reviewed
                  </button>
                ) : null}
              </div>
            </section>
          ) : null}

          <div className="screen3-grid">
            <section className="screen3-left">
              <div
                className={[
                  "screen3-matrix-outline",
                  activeHand.ui_gate === "must_fill_response_matrix" && !isVillainThinking
                    ? "is-active"
                    : "",
                ]
                  .filter(Boolean)
                  .join(" ")}
              >
                {isReplayMode && currentReplayStep?.kind === "preflop_range" ? (
                  <ReplayPreflopPanel step={currentReplayStep} />
                ) : (
                  <>
                    <div
                      className={`bucket-row-header columns-${Math.max(
                        displayResponseColumns.length,
                        1,
                      )}`}
                    >
                      <div className="bucket-row-header-title">Bucket</div>
                      {displayResponseColumns.map((column) => (
                        <div key={column} className="bucket-row-header-cell">
                          {COLUMN_LABELS[column] ?? column}
                        </div>
                      ))}
                    </div>

                    <div className="bucket-matrix">
                  {displayedBucketRows.map((row) => {
                    const isCurrentPruneRow =
                      activeHand.ui_gate === "must_prune_range" &&
                      !isVillainThinking &&
                      currentPruneBucket === row.bucket_name;

                    const displayedSubgroups = isCurrentPruneRow
                      ? currentPruneSubgroups
                      : row.subgroups;

                    return (
                      <div
                        key={row.bucket_name}
                        className={[
                          "bucket-row",
                          isCurrentPruneRow ? "is-prune-active" : "",
                        ]
                          .filter(Boolean)
                          .join(" ")}
                      >
                        <div
                          className={`bucket-row-main ${
                            displayResponseColumns.length === 2 ? "two-actions" : ""
                          }`}
                        >
                          <div className="bucket-meta">
                            <div
                              className={`bucket-pill ${
                                BUCKET_CLASS[row.bucket_name] ?? "air"
                              }`}
                            >
                              {row.bucket_name}
                            </div>

                            <div className="bucket-stats">
                              <div className="bucket-percent">{row.bucket_percent}%</div>
                              <div className="bucket-holdings">
                                {row.combo_count} combos
                              </div>
                            </div>
                          </div>

                          {displayResponseColumns.map((column) => {
                            const selected =
                              activeResponseSelections[row.bucket_name]?.[column] ?? "";
                            const options = getResponseOptionsForDisplay(
                              column,
                              activeHand,
                              scenario,
                              activeResponseSelections,
                            );

                            return (
                              <div key={column} className="response-cell">
                                <div className="response-pill-group">
                                  {options.map((option) => {
                                    const isSelected = selected === option.value;
                                    const disabled =
                                      isReplayMode ||
                                      activeHand.ui_gate !==
                                        "must_fill_response_matrix" ||
                                      isSavingMatrix ||
                                      isSubmittingAction ||
                                      isPruneBusy ||
                                      activeHand.hand_over ||
                                      isVillainThinking ||
                                      isTimeoutTransitioning;
                                    const toneClass = `tone-${getResponseTone(
                                      option.value,
                                      option.semantic,
                                    )}`;

                                    return (
                                      <button
                                        key={option.value}
                                        type="button"
                                        className={[
                                          "response-pill",
                                          `kind-${option.value.toLowerCase()}`,
                                          toneClass,
                                          isSelected ? "is-selected" : "",
                                        ]
                                          .filter(Boolean)
                                          .join(" ")}
                                        disabled={disabled}
                                        onClick={() =>
                                          updateSelection(
                                            row.bucket_name,
                                            column,
                                            option.value,
                                          )
                                        }
                                      >
                                        {option.label}
                                      </button>
                                    );
                                  })}
                                </div>
                              </div>
                            );
                          })}
                        </div>

                        {isCurrentPruneRow ? (
                          <div className="bucket-row-expanded">
                            <div className="subgroup-strip">
                              {displayedSubgroups.map((subgroup) => (
                                <div
                                  key={subgroup.subgroup_name}
                                  className="subgroup-chip"
                                >
                                  <button
                                    type="button"
                                    className="subgroup-chip-remove"
                                    onClick={() =>
                                      void handlePruneRemoveSubgroup(
                                        subgroup.subgroup_name,
                                      )
                                    }
                                    disabled={isPruneBusy || isTimeoutTransitioning}
                                    title={`Remove ${subgroup.subgroup_name}`}
                                  >
                                    ×
                                  </button>
                                  <div className="subgroup-chip-name">
                                    {subgroup.subgroup_name}
                                  </div>
                                  <div className="subgroup-chip-count">
                                    {subgroup.combo_count} combos
                                  </div>
                                </div>
                              ))}
                            </div>

                            <div className="combo-row-footer">
                              <button
                                type="button"
                                className="btn btn-ghost"
                                onClick={() => void handlePruneRevert()}
                                disabled={isReplayMode || isPruneBusy || isTimeoutTransitioning}
                              >
                                Revert
                              </button>
                              <button
                                type="button"
                                className="btn btn-primary"
                                onClick={() => void handlePruneSaveRow()}
                                disabled={isReplayMode || isPruneBusy || isTimeoutTransitioning}
                              >
                                Save Row
                              </button>
                            </div>
                          </div>
                        ) : null}
                      </div>
                    );
                  })}
                    </div>
                  </>
                )}
              </div>

              <div className="screen3-bottom-actions">
                <div className="screen3-left-actions">
                  {activeHand.ui_gate === "must_fill_response_matrix" && !activeHand.hand_over && !isReplayMode ? (
                    <button
                      className="btn btn-primary"
                      type="button"
                      onClick={() => void handleSaveResponseMatrix()}
                      disabled={
                        !canSaveMatrix ||
                        isSavingMatrix ||
                        isVillainThinking ||
                        isTimeoutTransitioning
                      }
                    >
                      {isSavingMatrix ? "Saving..." : "Save Response Matrix"}
                    </button>
                  ) : null}

                  {activeHand.ui_gate === "must_prune_range" && !activeHand.hand_over && !isReplayMode ? (
                    <button
                      className="btn btn-ghost"
                      type="button"
                      onClick={() => void handlePruneNoChanges()}
                      disabled={isPruneBusy || isVillainThinking || isTimeoutTransitioning}
                    >
                      {isPruneBusy ? "Saving..." : "No Changes"}
                    </button>
                  ) : null}

                  {activeHand.hand_over && !isReplayMode ? (
                    <button
                      className="screen3-pill-btn is-active"
                      type="button"
                      onClick={() => void handleReveal()}
                      disabled={isRevealBusy || isTimeoutTransitioning}
                    >
                      {isRevealBusy ? "Revealing..." : "Reveal Villain Hand"}
                    </button>
                  ) : null}
                </div>

                <div className="screen3-status-text">
                  {isVillainThinking
                    ? "Villain thinking..."
                    : activeHand.ui_gate === "must_prune_range"
                      ? `Pruning: ${currentPruneBucket ?? "—"}`
                      : `${activeHand.bucket_matrix_view.total_live_combos} live combos`}
                </div>
              </div>
            </section>

            <aside className="screen3-right screen3-right-panel">
              <div className="actor-list">
                {topActor ? (
                  <ActorRow
                    actor={topActor}
                    hand={activeHand}
                    isCurrent={activeHighlightActor === topActor.id}
                    isDimmed={
                      activeHighlightActor !== null &&
                      activeHighlightActor !== topActor.id
                    }
                    isVillainThinking={isVillainThinking}
                  />
                ) : null}

                {bottomActor ? (
                  <ActorRow
                    actor={bottomActor}
                    hand={activeHand}
                    isCurrent={activeHighlightActor === bottomActor.id}
                    isDimmed={
                      activeHighlightActor !== null &&
                      activeHighlightActor !== bottomActor.id
                    }
                    isVillainThinking={isVillainThinking}
                  />
                ) : null}
              </div>

              <div className="section-stack screen3-right-sections">
                <div className="soft-block">
                  <p className="soft-block-title">Board</p>
                  <div className="card-row">
                    {activeHand.board.map((card) => (
                      <PlayingCard key={card} card={card} />
                    ))}
                  </div>
                </div>

                <div className="soft-block">
                  <div className="row-between">
                    <p className="soft-block-title tight">Pot</p>
                    <span className="screen3-stat-value">{formatBb(activeHand.pot)}</span>
                  </div>
                </div>

                <div className="soft-block">
                  <p className="soft-block-title">Hero Hand</p>
                  <div className="card-row">
                    {activeHand.hero_hand.map((card) => (
                      <PlayingCard key={card} card={card} />
                    ))}
                  </div>
                </div>

                <div
                  className={[
                    "soft-block",
                    "screen3-actions-block",
                    activeHand.ui_gate === "hero_to_act" && !isVillainThinking
                      ? "is-active"
                      : "",
                  ]
                    .filter(Boolean)
                    .join(" ")}
                >
                  <div className="row-between">
                    <p className="soft-block-title tight">Hero Actions</p>
                    <span className="screen3-step-tag">{gateLabel}</span>
                  </div>

                  {isReplayMode && replayPayload && currentReplayStep ? (
                    <ReplayControls
                      step={currentReplayStep}
                      stepIndex={replayStepIndex}
                      totalSteps={replayPayload.steps.length}
                      onPrevious={() => {
                        goToReplayStep(replayStepIndex - 1);
                      }}
                      onNext={() => {
                        goToReplayStep(replayStepIndex + 1);
                      }}
                    />
                  ) : isVillainThinking ? (
                    <div className="screen3-muted-block">
                      Villain is thinking. Hero actions will unlock after the pause
                      finishes and the current villain action is shown.
                    </div>
                  ) : activeHand.ui_gate !== "hero_to_act" ? (
                    <div className="screen3-muted-block">
                      {activeHand.ui_gate === "must_prune_range"
                        ? "Finish pruning the current bucket before hero can act."
                        : activeHand.ui_gate === "must_fill_response_matrix"
                          ? "Complete and save the response matrix before hero can act."
                          : activeHand.hand_over
                            ? "The hand is over."
                            : "Waiting for the next action state."}
                    </div>
                  ) : heroToCall <= 0 ? (
                    <div className="screen3-action-stack">
                      <div className="screen3-action-row">
                        <button
                          className="btn btn-ghost"
                          type="button"
                          onClick={() => void handleHeroAction("check")}
                          disabled={isSubmittingAction || isVillainThinking || isTimeoutTransitioning}
                        >
                          Check
                        </button>
                      </div>

                      <div className="screen3-bet-row">
                        <input
                          className="input"
                          value={betInput}
                          onChange={(e) => setBetInput(e.target.value)}
                          placeholder="Bet amount"
                          inputMode="decimal"
                        />
                        <button
                          className="btn btn-primary"
                          type="button"
                          disabled={
                            isSubmittingAction ||
                            isVillainThinking ||
                            isTimeoutTransitioning ||
                            Number.parseFloat(betInput) <= 0
                          }
                          onClick={() =>
                            void handleHeroAction(
                              "bet",
                              Number.parseFloat(betInput),
                            )
                          }
                        >
                          Bet
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="screen3-action-stack">
                      <div className="screen3-action-row">
                        <button
                          className="btn btn-ghost"
                          type="button"
                          onClick={() => void handleHeroAction("fold")}
                          disabled={isSubmittingAction || isVillainThinking || isTimeoutTransitioning}
                        >
                          Fold
                        </button>

                        <button
                          className="btn btn-primary"
                          type="button"
                          onClick={() => void handleHeroAction("call")}
                          disabled={isSubmittingAction || isVillainThinking || isTimeoutTransitioning}
                        >
                          Call {formatBb(heroToCall)}
                        </button>
                      </div>

                      <div className="screen3-bet-row">
                        <input
                          className="input"
                          value={raiseInput}
                          onChange={(e) => setRaiseInput(e.target.value)}
                          placeholder="Raise to"
                          inputMode="decimal"
                        />
                        <button
                          className="btn btn-primary"
                          type="button"
                          disabled={
                            isSubmittingAction ||
                            isVillainThinking ||
                            isTimeoutTransitioning ||
                            Number.parseFloat(raiseInput) <=
                              activeHand.betting_round.current_bet
                          }
                          onClick={() =>
                            void handleHeroAction(
                              "raise",
                              Number.parseFloat(raiseInput),
                            )
                          }
                        >
                          Raise
                        </button>
                      </div>
                    </div>
                  )}
                </div>

                {error ? (
                  <div className="soft-block screen3-error-block">
                    <p className="tight">{error}</p>
                  </div>
                ) : null}

                {reveal ? (
                  <div className="soft-block">
                    <p className="soft-block-title">Villain Hand</p>
                    <div className="card-row">
                      {reveal.villain_hand.map((card) => (
                        <PlayingCard key={card} card={card} />
                      ))}
                    </div>
                  </div>
                ) : null}

                {reveal && debriefPreview ? (
                  <div className="soft-block screen3-debrief-preview">
                    <div className="screen3-preview-head">
                      <div className="screen3-preview-head-copy">
                        <p className="soft-block-title tight">Result Preview</p>
                        <p className="screen3-preview-subtitle">
                          Final scores for this hand and the fastest next steps.
                        </p>
                      </div>
                      <span className="screen3-step-tag">Hand complete</span>
                    </div>
                    <div className="screen3-preview-grid">
                      <div className="screen3-preview-metric is-ranging">
                        <span className="screen3-preview-label">Range Score</span>
                        <strong>{formatRoundedScore(debriefPreview.summary.ranging_score)}</strong>
                      </div>
                      <div className="screen3-preview-metric is-action">
                        <span className="screen3-preview-label">Action Score</span>
                        <strong>{formatRoundedScore(debriefPreview.summary.response_score)}</strong>
                      </div>
                    </div>
                    {debriefPreview.recommendations.length ? (
                      <ul className="screen3-preview-list">
                        {debriefPreview.recommendations.map((item) => (
                          <li key={item}>{item}</li>
                        ))}
                      </ul>
                    ) : null}
                    <div className="screen3-preview-actions">
                      <Link href={`/results/hand/${encodeURIComponent(activeHand.hand_id)}`} className="btn btn-primary screen3-preview-primary">
                        Open Full Debrief
                      </Link>
                      <div className="screen3-preview-secondary-actions">
                        <Link href="/results" className="btn btn-ghost">
                          Results
                        </Link>
                        <Link href="/dashboard" className="btn btn-ghost">
                          Home
                        </Link>
                      </div>
                    </div>
                  </div>
                ) : null}
              </div>
            </aside>
          </div>
        </div>
      )}

      <TimeoutOverlay
        open={isTimeoutOverlayOpen}
        subtitle={timeoutSubtitle}
      />

      <style jsx global>{`

        .soft-block.screen3-debrief-preview {
          display: grid;
          border: 1px solid rgba(106,158,114,0.28);
          background: var(--surface-fill);
          border-radius: 18px;
          padding: 18px;
          gap: 16px;
        }

        .screen3-preview-head {
          display: flex;
          align-items: flex-start;
          justify-content: space-between;
          gap: 14px;
          flex-wrap: wrap;
        }

        .screen3-preview-head-copy {
          display: grid;
          gap: 6px;
          min-width: 0;
        }

        .screen3-preview-subtitle {
          margin: 0;
          color: var(--text-65);
          font-size: 14px;
          line-height: 1.6;
          max-width: 340px;
        }

        .screen3-preview-grid {
          display: grid;
          grid-template-columns: repeat(2, minmax(0, 1fr));
          gap: 12px;
        }

        .screen3-preview-metric {
          border-radius: 16px;
          border: 1px solid rgba(240,235,224,0.08);
          padding: 16px 16px 14px;
          display: grid;
          gap: 8px;
          min-height: 112px;
          align-content: space-between;
        }

        .screen3-preview-metric strong {
          font-size: clamp(30px, 3vw, 38px);
          line-height: 1;
          color: var(--text);
        }

        .screen3-preview-metric.is-ranging {
          background: var(--accent);
          border-color: var(--accent);
        }

        .screen3-preview-metric.is-action {
          background: var(--success);
          border-color: var(--success);
          color: var(--bg);
        }

        .screen3-preview-label {
          font-size: 11px;
          text-transform: uppercase;
          letter-spacing: 0.12em;
          color: rgba(20,18,16,0.78);
          font-weight: 900;
        }

        .screen3-preview-metric.is-ranging .screen3-preview-label {
          color: rgba(20,18,16,0.78);
        }

        .screen3-preview-metric.is-action .screen3-preview-label {
          color: rgba(20,18,16,0.78);
        }

        .screen3-preview-list {
          margin: 0;
          padding-left: 18px;
          color: var(--text-65);
          display: grid;
          gap: 8px;
          line-height: 1.55;
        }

        .screen3-preview-actions {
          display: grid;
          gap: 10px;
        }

        .screen3-preview-primary {
          width: 100%;
        }

        .screen3-preview-secondary-actions {
          display: flex;
          gap: 10px;
          flex-wrap: wrap;
        }

        .screen3-shell {
          min-height: 100dvh;
          padding: 22px 32px 42px;
          background:
var(--bg);
          color: var(--text);
        }

        .screen3-wrap {
          width: min(100%, 1560px);
          margin: 0 auto;
          display: flex;
          flex-direction: column;
          gap: 18px;
        }

        .screen3-topbar {
          display: flex;
          justify-content: flex-end;
        }

        .screen3-grid {
          display: grid;
          grid-template-columns: minmax(780px, 1.6fr) minmax(410px, 0.88fr);
          gap: 20px;
          align-items: start;
        }

        .screen3-left,
        .screen3-right {
          min-width: 0;
          display: flex;
          flex-direction: column;
        }

        .screen3-left {
          gap: 14px;
        }

        .screen3-right {
          gap: 18px;
          padding-top: 0;
          position: sticky;
          top: 18px;
        }

        .screen3-title-wrap {
          text-align: left;
          padding: 2px 2px 0;
        }

        .screen3-title {
          margin: 0;
          font-size: clamp(30px, 3vw, 40px);
          line-height: 1.04;
          font-weight: 760;
          letter-spacing: -0.035em;
        }

        .screen3-subtitle {
          margin: 8px 0 0;
          max-width: 780px;
          color: var(--text-muted);
          font-size: 15px;
          line-height: 1.6;
        }

        .screen3-stepbar {
          display: grid;
          grid-template-columns: repeat(3, minmax(0, 1fr));
          gap: 10px;
        }

        .screen3-step-pill {
          min-height: 48px;
          border-radius: 14px;
          border: 1px solid var(--border);
          background: transparent;
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 10px 12px;
          font-size: 13px;
          font-weight: 800;
          letter-spacing: 0.02em;
          color: var(--text-muted);
          transition:
            border-color 140ms ease,
            background 140ms ease,
            color 140ms ease,
            box-shadow 140ms ease;
        }

        .screen3-step-pill.is-active {
          background: var(--accent);
          border-color: var(--accent);
          color: var(--text);
          
        }

        .screen3-step-pill.is-complete {
          background: var(--surface-fill);
          border-color: var(--border);
          color: var(--text);
        }

        .screen3-matrix-head,
        .screen3-bottom-actions,
        .row-between {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 12px;
        }

        .screen3-gate-pill,
        .screen3-street-pill,
        .screen3-status-text,
        .screen3-pill-btn,
        .screen3-step-tag {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          min-height: 38px;
          padding: 8px 12px;
          border-radius: 999px;
          border: 1px solid var(--border);
          background: transparent;
          color: var(--text);
          font-size: 12px;
          font-weight: 800;
          letter-spacing: 0.04em;
          white-space: nowrap;
        }

        .screen3-gate-pill.is-thinking {
          background: var(--accent);
          border-color: var(--accent);
        }

        .screen3-pill-btn:hover {
          background: rgba(20,18,16,1);
        }

        .screen3-pill-btn.is-active {
          background: var(--accent);
          border-color: var(--accent);
          color: var(--text);
        }

        .screen3-matrix-outline {
          border-top: 1px solid var(--line-soft);
          background: transparent;
          padding-top: 14px;
          display: flex;
          flex-direction: column;
          gap: 10px;
          min-height: 560px;
          transition:
            border-color 140ms ease,
            box-shadow 140ms ease,
            background 140ms ease;
        }

        .screen3-matrix-outline.is-active {
          border-top-color: var(--accent);
          box-shadow: none;
          background: transparent;
        }

        .bucket-row-header {
          display: grid;
          gap: 10px;
          padding: 0 4px;
          align-items: center;
        }

        .bucket-row-header.columns-1 {
          grid-template-columns: minmax(220px, 1.15fr);
        }

        .bucket-row-header.columns-2 {
          grid-template-columns: minmax(220px, 1.15fr) repeat(2, minmax(120px, 1fr));
        }

        .bucket-row-header.columns-3 {
          grid-template-columns: minmax(220px, 1.15fr) repeat(3, minmax(120px, 1fr));
        }

        .bucket-row-header-title,
        .bucket-row-header-cell {
          color: rgba(240, 235, 224, 0.82);
          font-size: 14px;
          font-weight: 850;
          letter-spacing: 0.09em;
          text-transform: uppercase;
        }

        .bucket-row-header-cell {
          text-align: center;
        }

        .bucket-matrix {
          display: flex;
          flex-direction: column;
          gap: 10px;
          overflow: auto;
          padding-right: 2px;
          min-height: 468px;
        }

        .bucket-row-main {
          display: grid;
          grid-template-columns: minmax(220px, 1.15fr) repeat(3, minmax(120px, 1fr));
          gap: 10px;
          align-items: center;
          background: transparent;
          border-top: 1px solid var(--border);
          padding: 12px 0;
        }

        .bucket-row-main.two-actions {
          grid-template-columns: minmax(220px, 1.15fr) repeat(2, minmax(120px, 1fr));
        }

        .bucket-row.is-prune-active .bucket-row-main {
          border-top-color: var(--accent);
          background: transparent;
          box-shadow: none;
        }

        .bucket-meta {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 12px;
        }

        .bucket-pill {
          border-radius: 999px;
          padding: 8px 12px;
          font-weight: 800;
          font-size: 13px;
          border: 1px solid var(--line);
          color: var(--text);
        }

        .bucket-pill.nutted {
          background: rgba(231, 111, 81, 1);
          color: #F0EBE0;
        }

        .bucket-pill.value {
          background: rgba(231, 111, 81, 0.65);
          color: #F0EBE0;
        }

        .bucket-pill.sdv {
          background: rgba(240, 235, 224, 0.65);
          color: #141210;
        }

        .bucket-pill.draw {
          background: rgba(106, 158, 114, 1);
          color: #141210;
        }

        .bucket-pill.air {
          background: rgba(240, 235, 224, 0.35);
          color: #F0EBE0;
        }

        .bucket-stats {
          text-align: right;
        }

        .bucket-percent {
          font-size: 16px;
          font-weight: 800;
        }

        .bucket-holdings {
          font-size: 12px;
          color: var(--text-muted);
        }

        .response-cell {
          display: flex;
          justify-content: center;
        }

        .response-pill-group {
          display: flex;
          gap: 8px;
          flex-wrap: wrap;
          justify-content: center;
          min-height: 40px;
        }

        .response-pill {
          --pill-bg: rgba(240, 235, 224, 0.75);
          --pill-border: rgba(240, 235, 224, 0.28);
          --pill-text: #141210;
          min-width: 40px;
          min-height: 38px;
          border-radius: 10px;
          border: 1px solid var(--line);
          background: transparent;
          color: rgba(240, 235, 224, 0.88);
          font-weight: 900;
          cursor: pointer;
          transition:
            transform 120ms ease,
            background 120ms ease,
            border-color 120ms ease,
            color 120ms ease,
            box-shadow 120ms ease,
            opacity 120ms ease;
        }

        .response-pill.kind-r {
          --pill-bg: rgba(231, 111, 81, 1);
          --pill-border: rgba(231, 111, 81, 1);
          --pill-text: #F0EBE0;
        }

        .response-pill.kind-b,
        .response-pill.kind-a {
          --pill-bg: rgba(231, 111, 81, 0.75);
          --pill-border: rgba(231, 111, 81, 0.75);
          --pill-text: #F0EBE0;
        }

        .response-pill.kind-c {
          --pill-bg: rgba(106, 158, 114, 1);
          --pill-border: rgba(106, 158, 114, 1);
          --pill-text: #141210;
        }

        .response-pill.kind-p,
        .response-pill.kind-x {
          --pill-bg: rgba(240, 235, 224, 0.75);
          --pill-border: rgba(240, 235, 224, 0.75);
          --pill-text: #141210;
        }

        .response-pill.kind-f {
          --pill-bg: rgba(240, 235, 224, 0.35);
          --pill-border: rgba(240, 235, 224, 0.35);
          --pill-text: #F0EBE0;
        }

        .response-pill.tone-positive {
          --pill-bg: rgba(106, 158, 114, 1);
          --pill-border: rgba(106, 158, 114, 1);
          --pill-text: #141210;
        }

        .response-pill.tone-negative {
          --pill-bg: rgba(231, 111, 81, 0.75);
          --pill-border: rgba(231, 111, 81, 0.75);
          --pill-text: #F0EBE0;
        }

        .response-pill:hover:not(:disabled) {
          transform: translateY(-1px);
          border-color: rgba(240, 235, 224, 0.34);
          box-shadow: 0 10px 24px rgba(0, 0, 0, 0.16);
        }

        .response-pill.is-selected {
          background: var(--pill-bg);
          border-color: var(--pill-border);
          color: var(--pill-text);
          box-shadow: 0 0 0 1px rgba(240, 235, 224, 0.72), 0 0 0 6px rgba(240, 235, 224, 0.08);
          transform: translateY(-1px);
        }

        .response-pill:disabled {
          opacity: 0.55;
          cursor: not-allowed;
          transform: none;
        }

        .bucket-row-expanded {
          background: transparent;
          border-top: 1px dashed var(--border);
          padding: 12px 0 0;
          display: flex;
          flex-direction: column;
          gap: 12px;
        }

        .subgroup-strip {
          display: flex;
          flex-wrap: wrap;
          gap: 10px;
        }

        .subgroup-chip {
          position: relative;
          min-width: 140px;
          border-radius: 14px;
          border: 1px solid var(--border);
          background: transparent;
          padding: 12px 12px 10px;
        }

        .subgroup-chip-remove {
          position: absolute;
          top: 6px;
          right: 8px;
          border: none;
          background: transparent;
          color: var(--text-muted);
          font-size: 18px;
          line-height: 1;
          cursor: pointer;
        }

        .subgroup-chip-remove:disabled {
          opacity: 0.45;
          cursor: not-allowed;
        }

        .subgroup-chip-name {
          font-size: 13px;
          font-weight: 800;
          padding-right: 16px;
        }

        .subgroup-chip-count {
          margin-top: 6px;
          font-size: 12px;
          color: var(--text-muted);
        }

        .combo-row-footer,
        .screen3-action-row,
        .screen3-bet-row,
        .card-row {
          display: flex;
          gap: 10px;
          align-items: center;
          flex-wrap: wrap;
        }

        .screen3-left-actions,
        .screen3-action-stack,
        .section-stack,
        .actor-list {
          display: flex;
          flex-direction: column;
        }

        .screen3-left-actions,
        .screen3-action-stack,
        .section-stack {
          gap: 10px;
        }

        .actor-list {
          gap: 10px;
        }

        .screen3-right-sections {
          padding-top: 2px;
        }

        .soft-block {
          border-top: 1px solid var(--line-soft);
          background: transparent;
          padding: 14px 0 0;
          box-shadow: none;
        }

        .soft-block-title {
          margin: 0 0 10px;
          font-size: 11px;
          font-weight: 900;
          letter-spacing: 0.11em;
          text-transform: uppercase;
          color: var(--text-65);
        }

        .tight {
          margin: 0;
        }

        .screen3-actions-block.is-active {
          border-top-color: var(--accent);
          box-shadow: none;
        }

        .screen3-muted-block {
          color: var(--text-muted);
          font-size: 14px;
          line-height: 1.6;
        }

        .screen3-replay-preflop {
          border-top: 1px solid var(--line-soft);
          padding: 24px 0;
          display: grid;
          gap: 14px;
          min-height: 468px;
          align-content: start;
        }

        .screen3-replay-preflop h2 {
          margin: 0;
          font-size: clamp(28px, 3vw, 42px);
          line-height: 1.05;
          letter-spacing: -0.04em;
        }

        .screen3-replay-preflop p {
          margin: 0;
          color: var(--text-65);
          line-height: 1.6;
        }

        .screen3-replay-kicker {
          color: var(--accent);
          font-size: 12px;
          font-weight: 900;
          letter-spacing: 0.13em;
          text-transform: uppercase;
        }

        .screen3-replay-title {
          color: var(--text);
          font-size: 20px;
          font-weight: 900;
          line-height: 1.15;
          letter-spacing: -0.02em;
        }

        .screen3-replay-token-grid {
          display: flex;
          flex-wrap: wrap;
          gap: 10px;
          max-width: 900px;
        }

        .screen3-replay-token {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          min-height: 34px;
          padding: 7px 11px;
          border-radius: 999px;
          border: 1px solid var(--line);
          background: var(--surface-fill);
          color: var(--text);
          font-weight: 800;
          font-size: 13px;
        }

        .screen3-replay-controls {
          display: grid;
          gap: 12px;
        }

        .screen3-replay-nav {
          display: grid;
          grid-template-columns: repeat(2, minmax(0, 1fr));
          gap: 10px;
        }

        .screen3-replay-arrow {
          min-height: 46px;
          font-size: 28px;
          line-height: 1;
        }

        .screen3-replay-note-panel {
          border-top: 1px solid var(--line-soft);
          padding-top: 18px;
          display: grid;
          grid-template-columns: minmax(220px, 0.7fr) minmax(320px, 1.25fr) auto;
          gap: 16px;
          align-items: start;
        }

        .screen3-replay-note-title {
          margin-top: 6px;
          color: var(--text);
          font-weight: 900;
          font-size: 20px;
          line-height: 1.12;
        }

        .screen3-replay-note-meta,
        .screen3-replay-note-message {
          margin-top: 6px;
          color: var(--text-muted);
          font-size: 13px;
          line-height: 1.45;
        }

        .screen3-replay-note-grid {
          display: grid;
          grid-template-columns: repeat(2, minmax(0, 1fr));
          gap: 12px;
        }

        .screen3-replay-note-field {
          display: grid;
          gap: 7px;
        }

        .screen3-replay-note-field span {
          color: var(--text-65);
          font-size: 11px;
          font-weight: 900;
          letter-spacing: 0.09em;
          text-transform: uppercase;
        }

        .screen3-replay-note-field textarea {
          width: 100%;
          min-height: 86px;
          resize: vertical;
          border-radius: 14px;
          border: 1px solid var(--border);
          background: var(--surface-fill);
          color: var(--text);
          padding: 11px 12px;
          font: inherit;
          line-height: 1.45;
        }

        .screen3-replay-note-field textarea:disabled {
          opacity: 0.72;
        }

        .screen3-replay-note-actions {
          display: flex;
          gap: 10px;
          justify-content: flex-end;
          align-items: center;
          flex-wrap: wrap;
        }

        .screen3-stat-value {
          font-weight: 800;
        }

        .screen3-state {
          min-height: 70dvh;
          display: flex;
          align-items: center;
          justify-content: center;
        }

        .screen3-deal-state {
          flex-direction: column;
          gap: 18px;
        }

        .screen3-deal-animation {
          position: relative;
          width: 132px;
          height: 88px;
          filter: drop-shadow(0 22px 34px rgba(231, 111, 81, 0.14));
        }

        .screen3-deal-card {
          position: absolute;
          top: 9px;
          width: 50px;
          height: 68px;
          border-radius: 12px;
          border: 1px solid rgba(231, 111, 81, 0.54);
          background:
            radial-gradient(circle at 22% 18%, rgba(255, 214, 165, 0.24), transparent 34%),
            linear-gradient(145deg, rgba(49, 43, 37, 0.98), rgba(20, 18, 16, 0.98));
          color: var(--text);
          display: grid;
          place-items: center;
          font-weight: 950;
          box-shadow:
            inset 0 0 0 1px rgba(240, 235, 224, 0.08),
            0 18px 42px rgba(0, 0, 0, 0.34);
          will-change: left, transform, z-index;
        }

        .screen3-deal-card-a {
          animation: deal-card-a 1.45s ease-in-out infinite;
        }

        .screen3-deal-card-b {
          animation: deal-card-b 1.45s ease-in-out infinite;
        }

        .screen3-deal-card-c {
          animation: deal-card-c 1.45s ease-in-out infinite;
        }

        .screen3-deal-title {
          margin: 0;
          color: var(--text);
          font-size: 18px;
          font-weight: 900;
        }

        .screen3-spinner {
          width: 36px;
          height: 36px;
          border-radius: 999px;
          border: 3px solid rgba(240,235,224, 0.12);
          border-top-color: var(--accent-strong);
          animation: spin 0.9s linear infinite;
          margin: 0 auto 12px;
        }

        .screen3-error-title {
          margin: 0;
          font-size: 20px;
          font-weight: 800;
        }

        .screen3-center-copy {
          margin: 0;
          text-align: center;
          max-width: 460px;
        }

        .actor-row {
          position: relative;
          border-top: 1px solid var(--line-soft);
          background: transparent;
          padding: 14px 0;
          transition:
            opacity 140ms ease,
            border-color 140ms ease,
            box-shadow 140ms ease,
            transform 140ms ease,
            background 140ms ease;
          overflow: visible;
        }

        .actor-row.is-current {
          border-top-color: var(--accent);
          box-shadow: none;
          background: transparent;
        }

        .actor-row.is-dimmed {
          border-top-color: var(--line-soft);
          background: transparent;
        }

        .actor-row.is-dimmed .actor-avatar,
        .actor-row.is-dimmed .actor-row__header,
        .actor-row.is-dimmed .actor-row__footer {
          opacity: 0.56;
        }

        .actor-row.is-dimmed .actor-row__status {
          opacity: 0.74;
        }

        .actor-avatar {
          width: 62px;
          height: 62px;
          border-radius: 999px;
          overflow: hidden;
          background: rgba(20,18,16,1);
          border: 2px solid var(--line);
          display: flex;
          align-items: center;
          justify-content: center;
          font-weight: 800;
          color: var(--text);
          
        }

        .actor-row.is-current .actor-avatar {
          border-color: var(--accent);
          box-shadow: none;
        }

        .actor-hover-card {
          position: absolute;
          right: calc(100% + 14px);
          top: 50%;
          width: 280px;
          border-radius: 18px;
          border: 1px solid var(--text);
          background: rgba(20,18,16,1);
          box-shadow: 0 20px 44px rgba(20,18,16,0.62);
          padding: 14px;
          opacity: 0;
          pointer-events: none;
          transform: translateY(-50%) translateX(10px);
          transition:
            opacity 140ms ease,
            transform 140ms ease;
          z-index: 300;
        }

        .actor-avatar-shell:hover .actor-hover-card,
        .actor-avatar-shell:focus-within .actor-hover-card {
          opacity: 1;
          transform: translateY(-50%) translateX(0);
        }

        .actor-hover-card__top {
          display: grid;
          grid-template-columns: 58px 1fr;
          gap: 12px;
          align-items: center;
        }

        .actor-hover-card__image {
          width: 58px;
          height: 58px;
          border-radius: 14px;
          overflow: hidden;
          border: 1px solid var(--border);
          background: transparent;
        }

        .actor-hover-card__name {
          font-weight: 800;
          margin-bottom: 3px;
        }

        .actor-hover-card__type {
          font-size: 12px;
          color: var(--text-soft);
          text-transform: uppercase;
          letter-spacing: 0.08em;
          font-weight: 800;
        }

        .actor-hover-card__copy {
          margin: 12px 0 0;
          font-size: 13px;
          line-height: 1.55;
          color: var(--text-muted);
        }

        .actor-row__grid {
          display: grid;
          grid-template-columns: 62px minmax(0, 1fr) auto;
          gap: 14px;
          align-items: center;
        }

        .actor-row__content {
          min-width: 0;
          display: flex;
          flex-direction: column;
          gap: 4px;
        }

        .actor-row__header {
          display: flex;
          flex-direction: column;
          gap: 4px;
          min-width: 0;
        }

        .actor-row__title-line {
          display: flex;
          align-items: center;
          gap: 10px;
          flex-wrap: wrap;
          min-width: 0;
        }

        .actor-row__name {
          font-weight: 800;
          font-size: 15px;
          line-height: 1.1;
        }

        .actor-row__meta {
          font-size: 12px;
          color: var(--text-soft);
          line-height: 1.35;
        }

        .actor-row__right {
          min-width: 88px;
          display: flex;
          flex-direction: column;
          align-items: flex-end;
          gap: 8px;
        }

        .actor-row__stack-value {
          font-size: 14px;
          font-weight: 800;
          color: var(--text);
          letter-spacing: -0.01em;
          white-space: nowrap;
        }

        .actor-row__status {
          border-radius: 999px;
          padding: 6px 10px;
          font-size: 11px;
          font-weight: 950;
          letter-spacing: 0.05em;
          white-space: nowrap;
          border: 1px solid var(--line);
          background: transparent;
          color: var(--text);
        }

        .actor-row__status.is-active {
          background: var(--accent);
          border-color: rgba(231,111,81,0.40);
          color: var(--text);
        }

        .actor-row__status.is-thinking {
          background: var(--accent);
          border-color: rgba(231,111,81,0.34);
          color: var(--text);
        }

        .actor-action-pill {
          border-radius: 999px;
          padding: 7px 12px;
          font-size: 11px;
          font-weight: 950;
          letter-spacing: 0.035em;
          border: 1px solid var(--line);
          background: transparent;
          color: var(--text);
          white-space: nowrap;
          text-transform: uppercase;
        }

        .actor-action-pill.tone-neutral {
          background: rgba(20,18,16,1);
          border-color: var(--line);
          color: var(--text);
        }

        .actor-action-pill.tone-positive {
          background: var(--success);
          border-color: var(--success);
          color: var(--bg);
        }

        .actor-action-pill.tone-negative {
          background: var(--accent);
          border-color: var(--accent);
          color: var(--text);
        }

        @keyframes spin {
          to {
            transform: rotate(360deg);
          }
        }

        @keyframes deal-card-a {
          0%, 100% {
            left: 4px;
            z-index: 3;
            transform: rotate(-12deg) scale(1);
            opacity: 1;
          }
          33% {
            left: 41px;
            z-index: 2;
            transform: rotate(0deg) scale(0.96);
            opacity: 0.88;
          }
          66% {
            left: 78px;
            z-index: 1;
            transform: rotate(12deg) scale(0.92);
            opacity: 0.72;
          }
        }

        @keyframes deal-card-b {
          0%, 100% {
            left: 41px;
            z-index: 2;
            transform: rotate(0deg) scale(0.96);
            opacity: 0.88;
          }
          33% {
            left: 78px;
            z-index: 1;
            transform: rotate(12deg) scale(0.92);
            opacity: 0.72;
          }
          66% {
            left: 4px;
            z-index: 3;
            transform: rotate(-12deg) scale(1);
            opacity: 1;
          }
        }

        @keyframes deal-card-c {
          0%, 100% {
            left: 78px;
            z-index: 1;
            transform: rotate(12deg) scale(0.92);
            opacity: 0.72;
          }
          33% {
            left: 4px;
            z-index: 3;
            transform: rotate(-12deg) scale(1);
            opacity: 1;
          }
          66% {
            left: 41px;
            z-index: 2;
            transform: rotate(0deg) scale(0.96);
            opacity: 0.88;
          }
        }

        @media (max-width: 1280px) {
          .screen3-grid {
            grid-template-columns: 1fr;
          }

          .screen3-right {
            position: static;
          }
        }

        @media (max-width: 1200px) {
          .bucket-row-main,
          .bucket-row-main.two-actions {
            grid-template-columns: 1fr;
          }

          .bucket-row-header.columns-2,
          .bucket-row-header.columns-3 {
            grid-template-columns: 1fr;
          }

          .bucket-row-header-cell {
            text-align: left;
          }

          .bucket-meta {
            flex-direction: column;
            align-items: flex-start;
          }

          .bucket-stats {
            text-align: left;
          }

          .screen3-matrix-head,
          .screen3-bottom-actions,
          .row-between {
            flex-direction: column;
            align-items: flex-start;
          }

          .actor-row__grid {
            grid-template-columns: 62px minmax(0, 1fr);
          }

          .actor-row__right {
            grid-column: 2;
            align-items: flex-start;
          }

          .screen3-preview-grid {
            grid-template-columns: 1fr;
          }

          .screen3-replay-note-panel,
          .screen3-replay-note-grid {
            grid-template-columns: 1fr;
          }

          .screen3-replay-note-actions {
            justify-content: flex-start;
          }
        }

        @media (max-width: 880px) {
          .screen3-shell {
            padding: 14px;
          }

          .screen3-stepbar {
            grid-template-columns: 1fr;
          }

          .actor-hover-card {
            right: auto;
            left: 0;
            top: calc(100% + 12px);
            transform: translateY(0) translateY(8px);
            width: min(280px, calc(100vw - 56px));
          }

          .actor-avatar-shell:hover .actor-hover-card,
          .actor-avatar-shell:focus-within .actor-hover-card {
            transform: translateY(0) translateY(0);
          }
        }
      `}</style>
    </main>
  );
}

function initializeSelectionsFromHand(
  hand: HandState,
  columns: string[],
  existingSelections?: Record<string, Record<string, string>>,
  allowPartialExisting = false,
): Record<string, Record<string, string>> {
  const rows = hand.bucket_matrix_view.rows
    .filter((row) => row.combo_count > 0)
    .map((row) => row.bucket_name);

  const blankSelections: Record<string, Record<string, string>> = {};
  for (const rowName of rows) {
    blankSelections[rowName] = {};
    for (const column of columns) {
      blankSelections[rowName][column] = "";
    }
  }

  if (selectionsMatchShape(existingSelections, rows, columns)) {
    return existingSelections as Record<string, Record<string, string>>;
  }

  if (allowPartialExisting && existingSelections) {
    const mergedSelections = mergeSelectionsWithShape(blankSelections, existingSelections, rows, columns);
    if (hasAnySelection(mergedSelections)) {
      return mergedSelections;
    }
  }

  if (
    hand.response_matrix_saved &&
    "selections" in hand.response_matrix_saved &&
    hand.response_matrix_saved.selections &&
    selectionsMatchShape(hand.response_matrix_saved.selections, rows, columns)
  ) {
    return hand.response_matrix_saved.selections as Record<string, Record<string, string>>;
  }

  return blankSelections;
}

function buildReplayHandView(
  baseHand: HandState | null,
  replay: ReplayPayload | null,
  stepIndex: number,
): HandState | null {
  if (!baseHand || !replay || !replay.steps.length) return null;
  const boundedIndex = Math.max(0, Math.min(stepIndex, replay.steps.length - 1));
  const step = replay.steps[boundedIndex];
  const street = step.street === "preflop" ? "flop" : step.street;
  const board = step.street === "preflop" ? [] : step.board.length ? step.board : boardForStreet(replay.final_board, street);
  const actionEvents = replay.steps
    .slice(0, boundedIndex + 1)
    .map((item) => item.kind === "action" ? actionEventFromReplayStep(item) : null)
    .filter((event): event is ActionEvent => Boolean(event));
  const currentEvent = step.kind === "action" ? actionEventFromReplayStep(step) : null;
  const isResponseStep = isReplayResponseStep(step);
  const isPruneStep = isReplayPruneStep(step);
  const responseColumns = getReplayColumnsForStep(replay, boundedIndex);
  const responseSelections = getReplayVisibleResponseSelections(replay, boundedIndex);
  const replayBucketView = getReplayBucketViewForStep(baseHand.bucket_matrix_view, replay, boundedIndex);
  const currentPruneBucket = isPruneStep && typeof step.details?.actual_bucket === "string"
    ? step.details.actual_bucket
    : null;
  const currentPruneSubgroup = step.kind === "range_prune" && typeof step.details?.actual_subgroup === "string"
    ? String(step.details.actual_subgroup)
    : null;
  const shouldExposeSavedResponses = responseColumns.length > 0 && hasAnySelection(responseSelections);
  const currentPruneUiRow = currentPruneBucket
    ? replayBucketView.rows.find((row) => row.bucket_name === currentPruneBucket) ?? null
    : null;

  return {
    ...baseHand,
    street,
    board,
    pot: replay.pot,
    hero_stack: replay.hero_stack,
    villain_stack: replay.villain_stack,
    hero_hand: normalizeHoleCards(replay.hero_hand) ?? baseHand.hero_hand,
    bucket_matrix_view: replayBucketView,
    history: { events: actionEvents },
    current_actor: currentEvent?.actor ?? "hero",
    ui_gate: isResponseStep
      ? "must_fill_response_matrix"
      : isPruneStep
        ? "must_prune_range"
        : "hero_to_act",
    hand_over: boundedIndex === replay.steps.length - 1 && baseHand.hand_over,
    response_matrix_columns: responseColumns,
    response_matrix_saved: shouldExposeSavedResponses ? {
      street,
      columns: responseColumns,
      row_order: Object.keys(responseSelections),
      selections: responseSelections,
    } : {},
    prune_row_order: currentPruneBucket ? [currentPruneBucket] : [],
    prune_row_index: 0,
    current_prune_bucket: currentPruneBucket,
    current_prune_row_original: currentPruneBucket ? {
      bucket_name: currentPruneBucket,
      subgroups: currentPruneUiRow?.subgroups ?? (
        currentPruneSubgroup ? [{ subgroup_name: currentPruneSubgroup, combo_count: 0 }] : []
      ),
    } : null,
    current_prune_row_saved_version: null,
  };
}

function getReplayBucketViewForStep(
  fallbackView: BucketMatrixView,
  replay: ReplayPayload,
  stepIndex: number,
): BucketMatrixView {
  let view = cloneBucketMatrixView(fallbackView);
  const boundedIndex = Math.max(0, Math.min(stepIndex, replay.steps.length - 1));

  for (let index = 0; index <= boundedIndex; index += 1) {
    const step = replay.steps[index];
    if (isPlainRecord(step.details?.bucket_matrix_view)) {
      view = cloneBucketMatrixView(step.details.bucket_matrix_view as BucketMatrixView);
    }
    const isCurrentRemovalStep = index === boundedIndex && step.kind === "range_prune";
    if (step.kind === "range_prune" && !isCurrentRemovalStep) {
      view = bucketViewAfterReplayPruneStep(view, step);
    }
  }

  const currentStep = replay.steps[boundedIndex];
  if (currentStep.kind === "street_start") {
    const streetStartView = findReplayStreetStartBucketView(replay, boundedIndex);
    if (streetStartView) return cloneBucketMatrixView(streetStartView);
  }

  if (isReplayResponseStep(currentStep)) {
    return normalizeReplayBucketViewForStep(
      currentStep,
      view,
      getReplayVisibleResponseSelections(replay, boundedIndex),
    );
  }

  return view;
}

function findReplayStreetStartBucketView(
  replay: ReplayPayload,
  streetStartIndex: number,
): BucketMatrixView | null {
  const streetStartStep = replay.steps[streetStartIndex];
  const street = streetStartStep?.street;
  if (!street || street === "preflop") return null;

  for (let index = streetStartIndex; index < replay.steps.length; index += 1) {
    const step = replay.steps[index];
    if (index > streetStartIndex && step.kind === "street_start") break;
    if (step.street !== street) continue;
    if (isPlainRecord(step.details?.bucket_matrix_view)) {
      return step.details.bucket_matrix_view as BucketMatrixView;
    }
  }

  return null;
}

function cloneBucketMatrixView(view: BucketMatrixView): BucketMatrixView {
  return {
    ...view,
    row_order: [...(view.row_order ?? [])],
    rows: (view.rows ?? []).map((row) => ({
      ...row,
      hands: row.hands ? row.hands.map((hand) => ({ ...hand })) : [],
      subgroups: (row.subgroups ?? []).map((subgroup) => ({ ...subgroup })),
    })),
  };
}

function bucketViewAfterReplayPruneStep(
  view: BucketMatrixView,
  step: ReplayStep,
): BucketMatrixView {
  if (step.details?.replay_event_kind !== "prune_remove_subgroup") {
    return view;
  }

  const bucketName = typeof step.details.actual_bucket === "string"
    ? step.details.actual_bucket
    : typeof step.details.bucket === "string"
      ? step.details.bucket
      : "";
  const subgroupName = typeof step.details.actual_subgroup === "string"
    ? step.details.actual_subgroup
    : typeof step.details.subgroup === "string"
      ? step.details.subgroup
      : "";
  if (!bucketName || !subgroupName) return view;

  const totalLiveCombos = typeof step.details?.after_live_combos === "number"
    ? step.details.after_live_combos
    : Math.max(0, view.total_live_combos - (typeof step.details?.removed_combo_count === "number" ? step.details.removed_combo_count : 0));

  const rows = view.rows.map((row) => {
    if (row.bucket_name !== bucketName) {
      return {
        ...row,
        bucket_percent: totalLiveCombos > 0
          ? roundPercent((row.combo_count / totalLiveCombos) * 100)
          : 0,
      };
    }

    const removedFromSubgroups = row.subgroups.find((subgroup) => subgroup.subgroup_name === subgroupName)?.combo_count;
    const removedComboCount = typeof step.details?.removed_combo_count === "number"
      ? step.details.removed_combo_count
      : removedFromSubgroups ?? 0;
    const nextComboCount = Math.max(0, row.combo_count - removedComboCount);
    const nextHands = (row.hands ?? []).filter((hand) => hand.subgroup_name !== subgroupName);
    const nextSubgroups = row.subgroups.filter((subgroup) => subgroup.subgroup_name !== subgroupName);

    return {
      ...row,
      combo_count: nextComboCount,
      holdings_count: nextComboCount,
      bucket_percent: totalLiveCombos > 0
        ? roundPercent((nextComboCount / totalLiveCombos) * 100)
        : 0,
      hands: nextHands,
      subgroups: nextSubgroups,
    };
  });

  return {
    ...view,
    total_live_combos: totalLiveCombos,
    rows,
  };
}

function buildReplayResponseSelections(step: ReplayStep): Record<string, Record<string, string>> {
  if (!isReplayResponseStep(step) || !step.details) {
    return {};
  }
  if (isPlainRecord(step.details.selections)) {
    return step.details.selections as Record<string, Record<string, string>>;
  }
  if (typeof step.details.column !== "string") {
    return {};
  }
  const column = step.details.column;
  const out: Record<string, Record<string, string>> = {};
  const bucketScores = Array.isArray(step.details.bucket_level_scores)
    ? step.details.bucket_level_scores
    : [];
  for (const raw of bucketScores) {
    if (!isPlainRecord(raw) || typeof raw.bucket !== "string") continue;
    const predicted = typeof raw.predicted === "string" ? raw.predicted : "";
    out[raw.bucket] = { [column]: predicted };
  }
  return out;
}

function getReplayVisibleResponseSelections(
  replay: ReplayPayload,
  stepIndex: number,
): Record<string, Record<string, string>> {
  const boundedIndex = Math.max(0, Math.min(stepIndex, replay.steps.length - 1));
  const step = replay.steps[boundedIndex];

  if (isReplayResponseStep(step)) {
    const savedSelections = buildReplayResponseSelections(step);
    const revealCount = getReplayResponseRevealCount(step);
    if (revealCount == null) return savedSelections;
    return limitReplayResponseSelectionsForStep(step, savedSelections, revealCount);
  }

  const priorResponseStep = findPriorReplayResponseStep(replay, boundedIndex, step.street);
  return priorResponseStep ? buildReplayResponseSelections(priorResponseStep) : {};
}

function getReplayColumnsForStep(replay: ReplayPayload, stepIndex: number): string[] {
  const boundedIndex = Math.max(0, Math.min(stepIndex, replay.steps.length - 1));
  const step = replay.steps[boundedIndex];
  const responseStep = isReplayResponseStep(step)
    ? step
    : findPriorReplayResponseStep(replay, boundedIndex, step.street);

  if (!responseStep) return [];
  if (Array.isArray(responseStep.details?.columns)) {
    return responseStep.details.columns.map(String);
  }
  if (typeof responseStep.details?.column === "string") {
    return [responseStep.details.column];
  }
  return [];
}

function findPriorReplayResponseStep(
  replay: ReplayPayload,
  beforeIndex: number,
  street: ReplayStep["street"],
): ReplayStep | null {
  for (let index = beforeIndex; index >= 0; index -= 1) {
    const candidate = replay.steps[index];
    if (candidate.street !== street) continue;
    if (isReplayResponseStep(candidate)) return candidate;
    if (candidate.kind === "street_start") break;
  }
  return null;
}

function normalizeReplayBucketViewForStep(
  step: ReplayStep,
  view: BucketMatrixView,
  selections: Record<string, Record<string, string>>,
): BucketMatrixView {
  if (!isReplayResponseStep(step)) return view;

  const rowOrder = Array.isArray(step.details?.row_order)
    ? step.details.row_order.map(String).filter(Boolean)
    : Object.keys(selections);
  const uniqueRowOrder = Array.from(new Set(rowOrder));
  if (!uniqueRowOrder.length) return view;

  const existingRows = new Map((view.rows ?? []).map((row) => [row.bucket_name, row]));
  const scoreRows = new Map<string, BucketRow>();
  const bucketScores = Array.isArray(step.details?.bucket_level_scores)
    ? step.details.bucket_level_scores
    : [];

  for (const raw of bucketScores) {
    if (!isPlainRecord(raw) || typeof raw.bucket !== "string") continue;
    const bucketName = raw.bucket;
    const comboCount = typeof raw.combo_count === "number" ? raw.combo_count : 0;
    const bucketPercent = typeof raw.bucket_percent === "number" ? raw.bucket_percent : 0;
    scoreRows.set(bucketName, {
      bucket_name: bucketName,
      bucket_percent: bucketPercent,
      combo_count: comboCount,
      holdings_count: comboCount,
      subgroups: [],
      hands: [],
    });
  }

  const rows = uniqueRowOrder.map((bucketName) =>
    existingRows.get(bucketName) ??
    scoreRows.get(bucketName) ??
    {
      bucket_name: bucketName,
      bucket_percent: 0,
      combo_count: 0,
      holdings_count: 0,
      subgroups: [],
      hands: [],
    },
  );

  return {
    ...view,
    row_order: uniqueRowOrder,
    rows,
  };
}

function isReplayResponseStep(step: ReplayStep | null | undefined): boolean {
  return step?.kind === "response_matrix" || step?.kind === "response_matrix_cell";
}

function isReplayPruneStep(step: ReplayStep | null | undefined): boolean {
  return step?.kind === "range_prune" || step?.kind === "range_prune_start";
}

function getReplayResponseRevealCount(step: ReplayStep): number | null {
  if (!isReplayResponseStep(step)) return null;
  const raw = step.details?.reveal_count;
  if (typeof raw !== "number" || !Number.isFinite(raw)) return null;
  return Math.max(0, raw);
}

function expandReplayPayloadSteps(payload: ReplayPayload): ReplayPayload {
  return {
    ...payload,
    steps: expandReplaySteps(payload.steps),
  };
}

function expandReplaySteps(steps: ReplayStep[]): ReplayStep[] {
  const expanded: ReplayStep[] = [];
  const insertedPruneStarts = new Set<string>();
  for (const step of steps) {
    if (step.kind === "range_prune" && step.details?.replay_event_kind === "prune_remove_subgroup") {
      const bucket = typeof step.details.actual_bucket === "string"
        ? step.details.actual_bucket
        : typeof step.details.bucket === "string"
          ? step.details.bucket
          : "";
      const historyCount = typeof step.details.history_event_count === "number"
        ? step.details.history_event_count
        : String(step.details.history_event_count ?? "");
      const key = `${step.street}:${historyCount}:${bucket}`;
      if (bucket && !insertedPruneStarts.has(key)) {
        insertedPruneStarts.add(key);
        expanded.push({
          ...step,
          kind: "range_prune_start",
          title: `${bucket} range prune`,
          summary: `Review ${bucket} before removing subgroups.`,
          details: {
            ...(step.details ?? {}),
            replay_event_kind: "prune_start",
            actual_bucket: bucket,
            actual_subgroup: "",
          },
        });
      }
    }

    if (step.kind !== "response_matrix") {
      expanded.push(step);
      continue;
    }

    const sequence = replayResponseFillSequence(step);
    if (!sequence.length) {
      expanded.push(step);
      continue;
    }

    sequence.forEach((entry, index) => {
      expanded.push({
        ...step,
        kind: "response_matrix_cell",
        title: "Response matrix",
        summary: `${entry.bucket} · ${COLUMN_LABELS[entry.column] ?? titleCase(entry.column)}: ${entry.value}`,
        details: {
          ...(step.details ?? {}),
          reveal_count: index + 1,
          active_bucket: entry.bucket,
          active_column: entry.column,
          active_value: entry.value,
        },
      });
    });
  }
  return expanded;
}

function replayResponseFillSequence(
  step: ReplayStep,
): Array<{ bucket: string; column: string; value: string }> {
  const rawSequence = Array.isArray(step.details?.fill_sequence)
    ? step.details.fill_sequence
    : [];
  const sequence: Array<{ bucket: string; column: string; value: string }> = [];
  for (const raw of rawSequence) {
    if (!isPlainRecord(raw)) continue;
    const bucket = typeof raw.bucket === "string" ? raw.bucket : "";
    const column = typeof raw.column === "string" ? raw.column : "";
    const value = typeof raw.value === "string" ? raw.value : "";
    if (!bucket || !column || !value) continue;
    sequence.push({ bucket, column, value });
  }
  if (sequence.length) return sequence;

  const selections = buildReplayResponseSelections(step);
  for (const [bucket, row] of Object.entries(selections)) {
    for (const [column, value] of Object.entries(row)) {
      if (value) sequence.push({ bucket, column, value });
    }
  }
  return sequence;
}

function limitReplayResponseSelectionsForStep(
  step: ReplayStep,
  selections: Record<string, Record<string, string>>,
  limit: number,
): Record<string, Record<string, string>> {
  const out: Record<string, Record<string, string>> = {};
  for (const [bucket, row] of Object.entries(selections)) {
    out[bucket] = {};
    for (const column of Object.keys(row)) {
      out[bucket][column] = "";
    }
  }
  const fillSequence = Array.isArray(step.details?.fill_sequence)
    ? step.details.fill_sequence
    : [];
  if (fillSequence.length) {
    for (const raw of fillSequence.slice(0, limit)) {
      if (!isPlainRecord(raw)) continue;
      const bucket = typeof raw.bucket === "string" ? raw.bucket : "";
      const column = typeof raw.column === "string" ? raw.column : "";
      const value = typeof raw.value === "string" ? raw.value : "";
      if (!bucket || !column || !value || !(bucket in out)) continue;
      out[bucket][column] = value;
    }
    return out;
  }

  let shown = 0;
  for (const [bucket, row] of Object.entries(selections)) {
    for (const [column, value] of Object.entries(row)) {
      if (!value || shown >= limit) continue;
      out[bucket][column] = value;
      shown += 1;
    }
  }
  return out;
}

function actionEventFromReplayStep(step: ReplayStep): ActionEvent | null {
  const event = step.details?.event;
  if (!isPlainRecord(event)) return null;
  if (!isStreet(event.street) || !isActor(event.actor) || !isAction(event.action)) return null;
  return {
    street: event.street,
    actor: event.actor,
    action: event.action,
    amount: typeof event.amount === "number" ? event.amount : Number(event.amount ?? 0),
    note: typeof event.note === "string" ? event.note : "",
    forced: Boolean(event.forced),
  };
}

function normalizeHoleCards(cards: string[]): [string, string] | null {
  if (cards.length < 2) return null;
  return [cards[0], cards[1]];
}

function boardForStreet(board: string[], street: "flop" | "turn" | "river") {
  if (street === "river") return board.slice(0, 5);
  if (street === "turn") return board.slice(0, 4);
  return board.slice(0, 3);
}

function titleCase(value: string) {
  return value.slice(0, 1).toUpperCase() + value.slice(1);
}

function isPlainRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

function isStreet(value: unknown): value is ActionEvent["street"] {
  return value === "preflop" || value === "flop" || value === "turn" || value === "river";
}

function isActor(value: unknown): value is ActionEvent["actor"] {
  return value === "hero" || value === "villain";
}

function isAction(value: unknown): value is ActionEvent["action"] {
  return value === "check" || value === "bet" || value === "call" || value === "raise" || value === "fold";
}

function selectionsMatchShape(
  selections: Record<string, Record<string, string>> | null | undefined,
  rows: string[],
  columns: string[],
): boolean {
  if (!selections) return false;

  const savedRows = Object.keys(selections);
  const sameRows = savedRows.length === rows.length && rows.every((row) => row in selections);
  if (!sameRows) return false;

  return rows.every((row) => {
    const savedCols = Object.keys(selections[row] ?? {});
    return savedCols.length === columns.length && columns.every((column) => column in (selections[row] ?? {}));
  });
}


function filterSelectionsForRowsAndColumns(
  selections: Record<string, Record<string, string>>,
  rows: string[],
  columns: string[],
): Record<string, Record<string, string>> {
  const filtered: Record<string, Record<string, string>> = {};
  for (const row of rows) {
    filtered[row] = {};
    for (const column of columns) {
      filtered[row][column] = selections[row]?.[column] ?? "";
    }
  }
  return filtered;
}


function mergeSelectionsWithShape(
  blankSelections: Record<string, Record<string, string>>,
  existingSelections: Record<string, Record<string, string>>,
  rows: string[],
  columns: string[],
): Record<string, Record<string, string>> {
  const merged: Record<string, Record<string, string>> = {};
  for (const row of rows) {
    merged[row] = {};
    for (const column of columns) {
      merged[row][column] = existingSelections[row]?.[column] ?? blankSelections[row]?.[column] ?? "";
    }
  }
  return merged;
}

function hasAnySelection(selections: Record<string, Record<string, string>>): boolean {
  return Object.values(selections).some((row) => Object.values(row).some(Boolean));
}

function savedResponseSelectionsFromHand(
  hand: HandState | null,
): Record<string, Record<string, string>> {
  if (
    hand?.response_matrix_saved &&
    "selections" in hand.response_matrix_saved &&
    hand.response_matrix_saved.selections
  ) {
    return hand.response_matrix_saved.selections as Record<string, Record<string, string>>;
  }
  return {};
}

function roundPercent(value: number): number {
  return Math.round(value * 100) / 100;
}

function getResponseNodeSignature(hand: HandState, columns: string[]): string {
  return [
    hand.hand_id,
    hand.street,
    hand.ui_gate,
    hand.history.events.length,
    hand.betting_round.current_bet,
    hand.betting_round.hero_contrib,
    hand.betting_round.villain_contrib,
    columns.join("|"),
  ].join(":");
}

function getSavedResponseColumns(hand: HandState | null): string[] {
  if (
    hand?.response_matrix_saved &&
    "selections" in hand.response_matrix_saved &&
    hand.response_matrix_saved.selections
  ) {
    const saved = hand.response_matrix_saved.selections as Record<string, Record<string, string>>;
    const firstRow = Object.values(saved)[0];
    if (firstRow) {
      return Object.keys(firstRow);
    }
  }

  return [];
}

function getSelectionColumns(
  selections: Record<string, Record<string, string>>,
): string[] {
  const columns: string[] = [];
  const seen = new Set<string>();
  for (const row of Object.values(selections)) {
    for (const column of Object.keys(row)) {
      if (seen.has(column)) continue;
      seen.add(column);
      columns.push(column);
    }
  }
  return columns;
}

function resolveDisplayResponseColumns(
  hand: HandState | null,
  resolvedColumns: string[],
  selections: Record<string, Record<string, string>>,
): string[] {
  if (hand?.ui_gate !== "must_prune_range") return resolvedColumns;

  const selectedColumns = getSelectionColumns(selections);
  if (selectedColumns.length) return selectedColumns;

  const savedColumns = getSavedResponseColumns(hand);
  if (savedColumns.length) return savedColumns;

  return resolvedColumns;
}

function inferResponseColumnsFromState(hand: HandState | null): string[] {
  if (!hand) return [];
  const savedColumns = getSavedResponseColumns(hand);
  if (savedColumns.length) return savedColumns;

  if (hand.betting_round.current_bet > 0) {
    const toCall = getToCallForHero(hand);
    if (toCall > 0) {
      return ["call", "raise"];
    }
  }

  return ["check", "bet_small", "bet_big"];
}

function resolveResponseColumns(
  hand: HandState | null,
  rememberedColumns: string[],
): string[] {
  if (!hand) return rememberedColumns;
  if (hand.response_matrix_columns.length) return hand.response_matrix_columns;

  const savedColumns = getSavedResponseColumns(hand);
  if (savedColumns.length) return savedColumns;
  if (rememberedColumns.length) return rememberedColumns;

  return inferResponseColumnsFromState(hand);
}

function areSelectionsComplete(
  rows: BucketRow[],
  columns: string[],
  selections: Record<string, Record<string, string>>,
): boolean {
  if (!rows.length || !columns.length) return false;

  return rows.every((row) =>
    columns.every((column) => Boolean(selections[row.bucket_name]?.[column])),
  );
}

function getDisplayedBucketRows(hand: HandState, forcePercentOrder = false): BucketRow[] {
  const rows = hand.bucket_matrix_view.rows.filter((row) => row.combo_count > 0);

  const rowsByPercent = [...rows].sort((a, b) => {
    if (b.bucket_percent !== a.bucket_percent) {
      return b.bucket_percent - a.bucket_percent;
    }
    if (b.combo_count !== a.combo_count) {
      return b.combo_count - a.combo_count;
    }
    return a.bucket_name.localeCompare(b.bucket_name);
  });

  if (forcePercentOrder) return rowsByPercent;

  if (hand.ui_gate !== "must_prune_range" || hand.prune_row_order.length === 0) {
    if (
      hand.ui_gate === "must_fill_response_matrix" &&
      "row_order" in hand.response_matrix_saved &&
      Array.isArray(hand.response_matrix_saved.row_order) &&
      hand.response_matrix_saved.row_order.length > 0
    ) {
      const rank = new Map<string, number>();
      hand.response_matrix_saved.row_order.forEach((bucket, index) => {
        rank.set(bucket, index);
      });
      return rowsByPercent.sort((a, b) => {
        const aRank = rank.get(a.bucket_name) ?? Number.MAX_SAFE_INTEGER;
        const bRank = rank.get(b.bucket_name) ?? Number.MAX_SAFE_INTEGER;
        if (aRank !== bRank) return aRank - bRank;
        return a.bucket_name.localeCompare(b.bucket_name);
      });
    }
    return rowsByPercent;
  }

  const rank = new Map<string, number>();
  hand.prune_row_order.forEach((bucket, index) => {
    rank.set(bucket, index);
  });

  return rowsByPercent.sort((a, b) => {
    const aRank = rank.get(a.bucket_name) ?? Number.MAX_SAFE_INTEGER;
    const bRank = rank.get(b.bucket_name) ?? Number.MAX_SAFE_INTEGER;

    if (aRank !== bRank) return aRank - bRank;
    if (b.bucket_percent !== a.bucket_percent) {
      return b.bucket_percent - a.bucket_percent;
    }
    if (b.combo_count !== a.combo_count) {
      return b.combo_count - a.combo_count;
    }
    return a.bucket_name.localeCompare(b.bucket_name);
  });
}

function getDisplayedPruneSubgroups(
  row: BucketRow,
  hand: HandState,
): BucketSubgroup[] {
  const liveByName = new Map(
    (row.subgroups ?? []).map((subgroup) => [subgroup.subgroup_name, subgroup]),
  );

  const preferredOrderSource =
    hand.current_prune_row_original?.subgroups ??
    hand.current_prune_row_saved_version?.subgroups ??
    [];

  const ordered: BucketSubgroup[] = [];
  const seen = new Set<string>();

  for (const subgroup of preferredOrderSource) {
    const live = liveByName.get(subgroup.subgroup_name);
    if (live) {
      ordered.push(live);
      seen.add(subgroup.subgroup_name);
    }
  }

  for (const subgroup of row.subgroups ?? []) {
    if (!seen.has(subgroup.subgroup_name)) {
      ordered.push(subgroup);
    }
  }

  return ordered;
}

function getToCallForHero(hand: HandState): number {
  return Math.max(
    0,
    round2(
      (hand.betting_round.current_bet ?? 0) -
        (hand.betting_round.hero_contrib ?? 0),
    ),
  );
}

function round2(value: number): number {
  return Math.round(value * 100) / 100;
}

function formatBb(amount: number): string {
  const rounded = round2(amount);
  return `${Number(rounded.toFixed(2)).toString()}bb`;
}

function formatRoundedScore(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return `${Math.round(value)}`;
}

function formatShortDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function formatGateLabel(gate: HandState["ui_gate"]): string {
  if (gate === "must_prune_range") return "Prune Range";
  if (gate === "must_fill_response_matrix") return "Fill Matrix";
  if (gate === "hero_to_act") return "Take Action";
  return "Hand Over";
}

function getCurrentStepKey(
  gate: HandState["ui_gate"] | undefined,
  handOver?: boolean,
  isVillainThinking?: boolean,
): PhaseKey {
  if (isVillainThinking) return null;
  if (handOver) return "done";
  if (gate === "must_prune_range") return "prune";
  if (gate === "must_fill_response_matrix") return "matrix";
  if (gate === "hero_to_act") return "action";
  return null;
}

function buildWorkflowSteps(
  currentStep: PhaseKey,
  handOver: boolean,
  heroIsOop = false,
): WorkflowStep[] {
  const orderedSteps: Array<{ key: Exclude<PhaseKey, null | "done">; label: string }> = heroIsOop
    ? [
        { key: "matrix", label: "Step 1 · Fill Matrix" },
        { key: "action", label: "Step 2 · Take Action" },
        { key: "prune", label: "Step 3 · Prune Range" },
      ]
    : [
        { key: "prune", label: "Step 1 · Prune Range" },
        { key: "matrix", label: "Step 2 · Fill Matrix" },
        { key: "action", label: "Step 3 · Take Action" },
      ];

  if (handOver) {
    return orderedSteps.map((step) => ({ ...step, state: "complete" }));
  }

  const activeIndex = orderedSteps.findIndex((step) => step.key === currentStep);
  return orderedSteps.map((step, index): WorkflowStep => ({
    ...step,
    state: activeIndex === -1 ? "upcoming" : index < activeIndex ? "complete" : index === activeIndex ? "active" : "upcoming",
  }));
}

function getWorkflowHelperText(
  hand: HandState | null,
  isVillainThinking: boolean,
): string {
  if (isVillainThinking) {
    return "Waiting for villain action to resolve.";
  }
  if (!hand) return "";
  if (hand.hand_over) {
    return "The hand is complete. Reveal villain's hand when you're ready.";
  }
  if (hand.ui_gate === "must_prune_range") {
    return "Remove villain hand subgroups based on their latest action.";
  }
  if (hand.ui_gate === "must_fill_response_matrix") {
    return "Predict how every villain range bucket will respond to each action option by us.";
  }
  if (hand.ui_gate === "hero_to_act") {
    return "Choose your action.";
  }
  return "";
}

function getTimedStepSignature(
  hand: HandState | null,
  isVillainThinking: boolean,
  isTimeoutTransitioning: boolean,
): string | null {
  if (!hand || hand.hand_over || isVillainThinking || isTimeoutTransitioning) {
    return null;
  }

  if (
    hand.ui_gate === "must_prune_range" ||
    hand.ui_gate === "must_fill_response_matrix" ||
    hand.ui_gate === "hero_to_act"
  ) {
    return [
      hand.hand_id,
      hand.street,
      hand.ui_gate,
      hand.history.events.length,
    ].join(":");
  }

  return null;
}

function getWorkflowTimerLabel(
  configuredSeconds: number | null | undefined,
  timeLeftSeconds: number | null,
  isCountingDown: boolean,
): string {
  if (!configuredSeconds || configuredSeconds <= 0) return "Off";
  if (isCountingDown && timeLeftSeconds !== null) {
    return `${Math.max(0, timeLeftSeconds)}s`;
  }
  return `${configuredSeconds}s`;
}

function getScreenSubtitle(
  hand: HandState | null,
  isVillainThinking: boolean,
): string {
  if (isVillainThinking) {
    return "Villain is thinking. Once the pause finishes, the current villain action will appear and the next hero step will open.";
  }
  if (!hand) return "";
  if (hand.ui_gate === "must_prune_range") {
    return "Prune villain’s live range row by row by removing subgroups from the active bucket.";
  }
  if (hand.ui_gate === "must_fill_response_matrix") {
    return "Assign predicted responses for each broad bucket before taking your action.";
  }
  if (hand.ui_gate === "hero_to_act") {
    return "Review the current bucketed range, the latest street actions, and choose hero’s next action.";
  }
  return "Hand complete. Reveal villain’s hand when you’re ready.";
}

function SimplePhaseStep({
  label,
  isActive,
  isComplete,
}: {
  label: string;
  isActive: boolean;
  isComplete: boolean;
}) {
  return (
    <div
      className={[
        "screen3-step-pill",
        isActive ? "is-active" : "",
        isComplete ? "is-complete" : "",
      ]
        .filter(Boolean)
        .join(" ")}
    >
      {isComplete && !isActive ? `✓ ${label}` : label}
    </div>
  );
}

function ReplayPreflopPanel({ step }: { step: ReplayStep }) {
  const tokens = Array.isArray(step.details?.range_tokens)
    ? step.details?.range_tokens.map(String)
    : [];
  return (
    <div className="screen3-replay-preflop">
      <div className="screen3-replay-kicker">Saved setup</div>
      <h2>{step.title}</h2>
      <p>{step.summary}</p>
      <div className="screen3-replay-token-grid">
        {tokens.length ? tokens.map((token) => (
          <span key={token} className="screen3-replay-token">{token}</span>
        )) : <span className="screen3-muted-block">No range labels were stored for this step.</span>}
      </div>
    </div>
  );
}

function ReplayControls({
  step,
  stepIndex,
  totalSteps,
  onPrevious,
  onNext,
}: {
  step: ReplayStep;
  stepIndex: number;
  totalSteps: number;
  onPrevious: () => void;
  onNext: () => void;
}) {
  const stepDetail = replayStepDetailLabel(step);
  return (
    <div className="screen3-replay-controls">
      <div className="screen3-replay-kicker">Step {stepIndex + 1} of {totalSteps}</div>
      <div className="screen3-replay-title">{step.title}</div>
      <div className="screen3-muted-block">{stepDetail || step.summary}</div>
      <div className="screen3-replay-nav">
        <button type="button" className="btn btn-ghost screen3-replay-arrow" onClick={onPrevious} disabled={stepIndex <= 0} aria-label="Previous replay step">
          ‹
        </button>
        <button type="button" className="btn btn-ghost screen3-replay-arrow" onClick={onNext} disabled={stepIndex >= totalSteps - 1} aria-label="Next replay step">
          ›
        </button>
      </div>
    </div>
  );
}

function replayStepDetailLabel(step: ReplayStep): string {
  if (step.kind === "response_matrix_cell") {
    const bucket = typeof step.details?.active_bucket === "string" ? step.details.active_bucket : "";
    const column = typeof step.details?.active_column === "string" ? step.details.active_column : "";
    const value = typeof step.details?.active_value === "string" ? step.details.active_value : "";
    if (bucket && column && value) {
      return `${bucket}: ${COLUMN_LABELS[column] ?? titleCase(column)} = ${value}`;
    }
  }
  if (step.kind === "range_prune_start") {
    const bucket = typeof step.details?.actual_bucket === "string"
      ? step.details.actual_bucket
      : typeof step.details?.bucket === "string"
        ? step.details.bucket
        : "";
    if (bucket) return `Review ${bucket} before pruning`;
  }
  if (step.kind === "range_prune") {
    const subgroup = typeof step.details?.actual_subgroup === "string"
      ? step.details.actual_subgroup
      : typeof step.details?.subgroup === "string"
        ? step.details.subgroup
        : "";
    const bucket = typeof step.details?.actual_bucket === "string"
      ? step.details.actual_bucket
      : typeof step.details?.bucket === "string"
        ? step.details.bucket
        : "";
    if (bucket && subgroup) return `Removed ${subgroup} from ${bucket}`;
  }
  if (step.kind === "action") return step.title;
  return "";
}

function buildHeroActor(scenario: Scenario, hand: HandState | null) {
  return {
    id: "hero" as const,
    name: HERO_NAME,
    subtitle: scenario.hero_position,
    typeLabel: "Hero",
    stack: hand?.hero_stack ?? 0,
    avatarKind: "hero" as const,
  };
}

function buildVillainActor(
  scenario: Scenario,
  villain: VillainProfile,
  hand: HandState | null,
) {
  return {
    id: "villain" as const,
    name: villain.display_name,
    subtitle: scenario.villain_position,
    typeLabel: villain.type_label,
    stack: hand?.villain_stack ?? 0,
    avatarKind: "villain" as const,
    imageName: villain.image_name,
    description: villain.description,
  };
}

function getLatestStreetEventForActor(
  hand: HandState,
  actorId: "hero" | "villain",
): ActionEvent | null {
  const streetEvents = hand.history.events.filter(
    (event) => event.street === hand.street && event.actor === actorId,
  );
  return streetEvents.length ? streetEvents[streetEvents.length - 1] : null;
}

function formatActionLabel(event: ActionEvent): string {
  if (event.action === "bet") {
    return `Bet ${formatBb(event.amount)}`;
  }
  if (event.action === "raise") {
    return `Raise to ${formatBb(event.amount)}`;
  }
  if (event.action === "call") {
    return `Call ${formatBb(event.amount)}`;
  }
  if (event.action === "check") {
    return "Check";
  }
  return "Fold";
}

function getActorActionDisplay(
  actorId: "hero" | "villain",
  hand: HandState,
  isVillainThinking: boolean,
): { label: string; tone: ActionTone } {
  if (isVillainThinking && actorId === "villain") {
    return { label: "Thinking...", tone: "neutral" };
  }

  const latestEvent = getLatestStreetEventForActor(hand, actorId);
  if (!latestEvent) {
    return { label: "To Act", tone: "neutral" };
  }

  if (latestEvent.action === "call") {
    return { label: formatActionLabel(latestEvent), tone: "positive" };
  }

  if (latestEvent.action === "bet" || latestEvent.action === "raise") {
    return { label: formatActionLabel(latestEvent), tone: "negative" };
  }

  return { label: formatActionLabel(latestEvent), tone: "neutral" };
}

function getActorStatusLabel(
  actorId: "hero" | "villain",
  hand: HandState,
  isCurrent: boolean,
  isVillainThinking: boolean,
): string | null {
  if (isVillainThinking && actorId === "villain") return "Thinking";
  if (hand.hand_over) return null;
  if (isCurrent) return "Action On";
  return null;
}

function getResponseOptionsForColumn(
  column: string,
  hand: HandState,
  scenario: Scenario,
): Array<{ value: string; label: string; semantic: string }> {
  if (column === "check") {
    if (isRiverIpCheckbackNode(hand, scenario)) {
      return RIVER_CHECKBACK_SHOWDOWN_OPTIONS;
    }

    if (isIpCheckbackNode(hand, scenario)) {
      return RESPONSE_OPTIONS.call;
    }
  }

  if (column === "call" && hand.street === "river") {
    return RIVER_CHECKBACK_SHOWDOWN_OPTIONS;
  }

  return RESPONSE_OPTIONS[column] ?? [];
}

function getResponseOptionsForDisplay(
  column: string,
  hand: HandState,
  scenario: Scenario,
  selections: Record<string, Record<string, string>>,
): Array<{ value: string; label: string; semantic: string }> {
  if (
    hand.ui_gate === "must_prune_range" &&
    columnUsesPassiveAggressiveValues(column, selections)
  ) {
    return RESPONSE_OPTIONS.call;
  }

  return getResponseOptionsForColumn(column, hand, scenario);
}

function columnUsesPassiveAggressiveValues(
  column: string,
  selections: Record<string, Record<string, string>>,
): boolean {
  return Object.values(selections).some((row) => {
    const value = row[column];
    return value === "P" || value === "A";
  });
}

function getLatestVillainEvent(hand: HandState | null): ActionEvent | null {
  if (!hand) return null;
  const villainEvents = hand.history.events.filter(
    (event) => event.actor === "villain",
  );
  return villainEvents.length ? villainEvents[villainEvents.length - 1] : null;
}

function getVillainEventSignature(hand: HandState | null): string {
  if (!hand) return "";
  const villainEvents = hand.history.events.filter(
    (event) => event.actor === "villain",
  );
  if (!villainEvents.length) return "";
  const last = villainEvents[villainEvents.length - 1];
  return [
    villainEvents.length,
    last.street,
    last.action,
    last.amount,
    last.note,
    last.forced,
  ].join("|");
}

function hasNewVillainAction(
  previousHand: HandState | null,
  nextHand: HandState,
): boolean {
  return getVillainEventSignature(previousHand) !== getVillainEventSignature(nextHand);
}

function shouldStartImmediateVillainPause(hand: HandState, action: string): boolean {
  if (hand.hand_over || hand.ui_gate !== "hero_to_act") return false;
  if (action === "bet" || action === "raise") return true;
  if (action !== "check") return false;

  const latestStreetEvent = getLatestStreetEvent(hand);
  return !latestStreetEvent || latestStreetEvent.actor !== "villain";
}

function buildImmediateHeroActionPreview(
  hand: HandState,
  action: string,
  amount?: number,
): HandState {
  const preview = JSON.parse(JSON.stringify(hand)) as HandState;
  const eventAmount = round2(amount ?? (action === "call" ? getToCallForHero(hand) : 0));
  const event: ActionEvent = {
    street: hand.street,
    actor: "hero",
    action: isAction(action) ? action : "check",
    amount: eventAmount,
    note: "",
    forced: false,
  };

  preview.history = {
    events: [...hand.history.events, event],
  };
  preview.current_actor = "villain";
  preview.ui_gate = "hero_to_act";
  preview.hand_over = false;
  preview.villain_hand_revealed = false;
  preview.prune_row_order = [];
  preview.prune_row_index = 0;
  preview.current_prune_bucket = null;
  preview.current_prune_row_saved_version = null;
  preview.current_prune_row_original = null;

  if (action === "bet" && eventAmount > 0) {
    const previousHeroContrib = round2(hand.betting_round.hero_contrib ?? 0);
    const putIn = Math.max(0, round2(eventAmount - previousHeroContrib));
    preview.pot = round2(hand.pot + putIn);
    preview.hero_stack = round2(hand.hero_stack - putIn);
    preview.betting_round = {
      ...hand.betting_round,
      current_bet: eventAmount,
      hero_contrib: eventAmount,
      last_raise_size: eventAmount,
      folded: false,
    };
    preview.current_aggressor = "hero";
  }

  if (action === "raise" && eventAmount > 0) {
    const previousHeroContrib = round2(hand.betting_round.hero_contrib ?? 0);
    const priorBet = round2(hand.betting_round.current_bet ?? 0);
    const putIn = Math.max(0, round2(eventAmount - previousHeroContrib));
    preview.pot = round2(hand.pot + putIn);
    preview.hero_stack = round2(hand.hero_stack - putIn);
    preview.betting_round = {
      ...hand.betting_round,
      current_bet: eventAmount,
      hero_contrib: eventAmount,
      last_raise_size: Math.max(0, round2(eventAmount - priorBet)),
      folded: false,
    };
    preview.current_aggressor = "hero";
  }

  return preview;
}

function isIpCheckbackNode(hand: HandState, scenario: Scenario): boolean {
  if (!scenario.hero_is_ip) return false;
  if (hand.current_actor !== "hero") return false;
  if (getToCallForHero(hand) > 0) return false;

  const latestStreetEvent = getLatestStreetEvent(hand);
  if (!latestStreetEvent) return false;

  return (
    latestStreetEvent.actor === "villain" &&
    latestStreetEvent.action === "check" &&
    latestStreetEvent.street === hand.street
  );
}

function isRiverIpCheckbackNode(hand: HandState, scenario: Scenario): boolean {
  return isIpCheckbackNode(hand, scenario) && hand.street === "river";
}

function getLatestStreetEvent(hand: HandState): ActionEvent | null {
  const streetEvents = hand.history.events.filter(
    (event) => event.street === hand.street,
  );
  return streetEvents.length ? streetEvents[streetEvents.length - 1] : null;
}

function getResponseTone(value: string, semantic?: string): ActionTone {
  if (semantic === "win") return "positive";
  if (semantic === "lose") return "negative";

  if (value === "C") return "positive";
  if (value === "R" || value === "B" || value === "A") return "negative";
  return "neutral";
}

function getLastVillainEventIndex(hand: HandState): number {
  for (let index = hand.history.events.length - 1; index >= 0; index -= 1) {
    if (hand.history.events[index]?.actor === "villain") {
      return index;
    }
  }
  return -1;
}

function getPriorVillainContributionForRaise(
  events: ActionEvent[],
  street: HandState["street"],
  beforeIndex: number,
): number {
  for (let index = beforeIndex - 1; index >= 0; index -= 1) {
    const event = events[index];
    if (!event || event.street !== street || event.actor !== "villain") continue;
    if (event.action === "bet" || event.action === "raise") {
      return round2(event.amount);
    }
  }
  return 0;
}

function buildVillainPausePreview(
  previousHand: HandState | null,
  nextHand: HandState,
): HandState | null {
  const latestVillainIndex = getLastVillainEventIndex(nextHand);
  if (latestVillainIndex < 0) return previousHand ?? nextHand;

  const latestVillainEvent = nextHand.history.events[latestVillainIndex];
  if (!latestVillainEvent) return previousHand ?? nextHand;

  const preview = JSON.parse(JSON.stringify(nextHand)) as HandState;
  preview.history.events = nextHand.history.events.filter(
    (_, index) => index !== latestVillainIndex,
  );
  preview.current_actor = "villain";
  preview.hand_over = false;
  preview.ui_gate = "hero_to_act";
  preview.villain_hand_revealed = false;
  preview.betting_round.folded = false;
  preview.prune_row_order = [];
  preview.prune_row_index = 0;
  preview.current_prune_bucket = null;
  preview.current_prune_row_saved_version = null;
  preview.current_prune_row_original = null;
  preview.response_matrix_saved = previousHand?.response_matrix_saved ?? preview.response_matrix_saved;

  if (latestVillainEvent.action === "check") {
    preview.current_aggressor = previousHand?.current_aggressor ?? preview.current_aggressor;
    return preview;
  }

  if (latestVillainEvent.action === "bet") {
    preview.pot = round2(nextHand.pot - latestVillainEvent.amount);
    preview.villain_stack = round2(nextHand.villain_stack + latestVillainEvent.amount);
    preview.betting_round.current_bet = 0;
    preview.betting_round.hero_contrib = 0;
    preview.betting_round.villain_contrib = 0;
    preview.betting_round.last_raise_size = 0;
    preview.current_aggressor = previousHand?.current_aggressor ?? null;
    return preview;
  }

  if (latestVillainEvent.action === "call") {
    preview.pot = round2(nextHand.pot - latestVillainEvent.amount);
    preview.villain_stack = round2(nextHand.villain_stack + latestVillainEvent.amount);
    preview.betting_round.villain_contrib = round2(
      Math.max(0, nextHand.betting_round.villain_contrib - latestVillainEvent.amount),
    );
    preview.current_aggressor = "hero";
    return preview;
  }

  if (latestVillainEvent.action === "raise") {
    const priorVillainContrib = getPriorVillainContributionForRaise(
      nextHand.history.events,
      nextHand.street,
      latestVillainIndex,
    );
    const putIn = round2(latestVillainEvent.amount - priorVillainContrib);

    preview.pot = round2(nextHand.pot - putIn);
    preview.villain_stack = round2(nextHand.villain_stack + putIn);
    preview.betting_round.villain_contrib = priorVillainContrib;
    preview.betting_round.current_bet = nextHand.betting_round.hero_contrib;
    preview.betting_round.last_raise_size = round2(
      Math.max(0, nextHand.betting_round.hero_contrib - priorVillainContrib),
    );
    preview.current_aggressor = "hero";
    return preview;
  }

  if (latestVillainEvent.action === "fold") {
    preview.current_aggressor = "hero";
    return preview;
  }

  return preview;
}

function buildInitialVillainPausePreview(
  hand: HandState,
  session: SessionState,
  scenario: Scenario,
): HandState | null {
  if (scenario.first_to_act_postflop !== "villain") return null;
  if (hand.hand_over) return null;

  const streetEvents = hand.history.events.filter(
    (event) => event.street === hand.street,
  );

  if (streetEvents.length !== 1) return null;
  if (streetEvents[0]?.actor !== "villain") return null;

  return {
    ...hand,
    pot: session.pot ?? hand.pot,
    hero_stack: session.hero_stack ?? hand.hero_stack,
    villain_stack: session.villain_stack ?? hand.villain_stack,
    betting_round: {
      current_bet: 0,
      hero_contrib: 0,
      villain_contrib: 0,
      last_raise_size: 0,
      folded: false,
    },
    history: {
      events: hand.history.events.filter(
        (event) => !(event.street === hand.street && event.actor === "villain"),
      ),
    },
    current_actor: "villain",
    current_aggressor:
      scenario.preflop_aggressor === "villain"
        ? "villain"
        : scenario.preflop_aggressor === "hero"
          ? "hero"
          : null,
    ui_gate: "hero_to_act",
    response_matrix_columns: [],
    response_matrix_saved: {},
    prune_row_order: [],
    prune_row_index: 0,
    current_prune_bucket: null,
    current_prune_row_saved_version: null,
    current_prune_row_original: null,
  };
}

function ActorRow({
  actor,
  hand,
  isCurrent,
  isDimmed,
  isVillainThinking,
}: {
  actor: {
    id: "hero" | "villain";
    name: string;
    subtitle: string;
    typeLabel: string;
    stack: number;
    avatarKind: "hero" | "villain";
    imageName?: string;
    description?: string;
  };
  hand: HandState;
  isCurrent: boolean;
  isDimmed: boolean;
  isVillainThinking: boolean;
}) {
  const actionDisplay = getActorActionDisplay(actor.id, hand, isVillainThinking);
  const statusLabel = getActorStatusLabel(
    actor.id,
    hand,
    isCurrent,
    isVillainThinking,
  );

  return (
    <div
      className={[
        "actor-row",
        isCurrent ? "is-current" : "",
        isDimmed ? "is-dimmed" : "",
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <div className="actor-row__grid">
        <div className="actor-avatar-shell">
          <div className="actor-avatar">
            {actor.avatarKind === "villain" ? (
              <Avatar
                name={actor.name}
                imageSrc={actor.imageName ? `/villains/${actor.imageName}` : undefined}
                size={62}
                title={actor.name}
              />
            ) : (
              <span>⭐</span>
            )}
          </div>

          {actor.avatarKind === "villain" && actor.imageName && actor.description ? (
            <div className="actor-hover-card">
              <div className="actor-hover-card__top">
                <div className="actor-hover-card__image">
                  <Avatar
                    name={actor.name}
                    imageSrc={actor.imageName ? `/villains/${actor.imageName}` : undefined}
                    size={58}
                    title={actor.name}
                  />
                </div>

                <div>
                  <div className="actor-hover-card__name">{actor.name}</div>
                  <div className="actor-hover-card__type">{actor.typeLabel}</div>
                </div>
              </div>

              <p className="actor-hover-card__copy">{actor.description}</p>
            </div>
          ) : null}
        </div>

        <div className="actor-row__content">
          <div className="actor-row__header">
            <div className="actor-row__title-line">
              <div className="actor-row__name">{actor.name}</div>

              {statusLabel ? (
                <div
                  className={[
                    "actor-row__status",
                    isVillainThinking && actor.id === "villain"
                      ? "is-thinking"
                      : isCurrent
                        ? "is-active"
                        : "",
                  ]
                    .filter(Boolean)
                    .join(" ")}
                >
                  {statusLabel}
                </div>
              ) : null}
            </div>

            <div className="actor-row__meta">
              {actor.subtitle} · {actor.typeLabel}
            </div>
          </div>
        </div>

        <div className="actor-row__right">
          <div className="actor-row__stack-value">{formatBb(actor.stack)}</div>
          <div className={`actor-action-pill tone-${actionDisplay.tone}`}>
            {actionDisplay.label}
          </div>
        </div>
      </div>
    </div>
  );
}

function PlayingCard({ card }: { card: string }) {
  const rank = card[0] ?? "";
  const suit = card[1] ?? "";
  return (
    <div
      style={{
        width: 42,
        height: 58,
        borderRadius: 10,
        background: "#F0EBE0",
        border: "1px solid rgba(20,18,16,0.08)",
        display: "flex",
        flexDirection: "column",
        justifyContent: "space-between",
        padding: "6px 7px",
        boxShadow: "0 8px 16px rgba(20,18,16,0.18)",
      }}
    >
      <span
        style={{
          fontWeight: 800,
          lineHeight: 1,
          color: getSuitColor(suit),
        }}
      >
        {rank}
      </span>
      <span
        style={{
          alignSelf: "center",
          fontSize: 16,
          lineHeight: 1,
          color: getSuitColor(suit),
        }}
      >
        {renderSuit(suit)}
      </span>
    </div>
  );
}

function renderSuit(suit: string) {
  if (suit === "h") return "♥";
  if (suit === "d") return "♦";
  if (suit === "c") return "♣";
  if (suit === "s") return "♠";
  return "?";
}

function getSuitColor(suit: string): string {
  if (suit === "h" || suit === "d") return THEME.primary;
  return THEME.bg;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

function isNetworkFetchError(err: unknown): boolean {
  return err instanceof TypeError && err.message === "Failed to fetch";
}

async function apiFetchWithRetry(
  input: RequestInfo | URL,
  init: RequestInit = {},
  retries = 1,
): Promise<Response> {
  let lastError: unknown = null;

  for (let attempt = 0; attempt <= retries; attempt += 1) {
    try {
      return await apiFetch(input, init);
    } catch (err) {
      lastError = err;
      if (!isNetworkFetchError(err) || attempt >= retries) break;
      await sleep(650);
    }
  }

  throw lastError instanceof Error
    ? lastError
    : new Error("Could not reach the training server.");
}

function trainingServerErrorMessage(err: unknown): string {
  if (isNetworkFetchError(err)) {
    return "Could not reach the training server. Please reload; your setup and saved hand state are still preserved.";
  }
  return err instanceof Error ? err.message : "Failed to load Screen 3.";
}

async function safeReadError(res: Response): Promise<string | null> {
  try {
    const data = (await res.json()) as { detail?: string };
    return data.detail ?? null;
  } catch {
    return null;
  }
}

export default function Screen3Page() {
  return (
    <Suspense fallback={null}>
      <Screen3PageContent />
    </Suspense>
  );
}

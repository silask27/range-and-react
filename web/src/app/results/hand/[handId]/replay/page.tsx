"use client";

import { useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import { API_BASE, apiFetch } from "../../../../../lib/api";
import { useRequireAuth } from "../../../../../lib/hooks/useRequireAuth";

type ReplayPayload = {
  hand_id: string;
  session_id: string;
};

export default function LegacyReplayRedirectPage() {
  const params = useParams<{ handId: string }>();
  const router = useRouter();
  const handId = Array.isArray(params?.handId) ? params.handId[0] : params?.handId;
  const { user, isAuthLoading, authError } = useRequireAuth();

  useEffect(() => {
    if (!user || !handId) return;
    let cancelled = false;
    async function loadAndRedirect() {
      const res = await apiFetch(`${API_BASE}/results/hand/${encodeURIComponent(handId)}/replay`, { cache: "no-store" });
      const data = await res.json();
      if (cancelled) return;
      if (!res.ok) {
        router.replace(`/results/hand/${encodeURIComponent(handId)}`);
        return;
      }
      const replay = data as ReplayPayload;
      router.replace(`/screen-1?session_id=${encodeURIComponent(replay.session_id)}&hand_id=${encodeURIComponent(replay.hand_id)}&replay=1`);
    }
    void loadAndRedirect();
    return () => {
      cancelled = true;
    };
  }, [user, handId, router]);

  if (isAuthLoading) return <main style={stateStyle}>Loading replay...</main>;
  if (authError) return <main style={stateStyle}>{authError}</main>;
  return <main style={stateStyle}>Opening replay in Train...</main>;
}

const stateStyle = {
  minHeight: "100dvh",
  display: "grid",
  placeItems: "center",
  background: "#141210",
  color: "#F0EBE0",
  fontWeight: 800,
};

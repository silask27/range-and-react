"use client";

import AppShell from "../../components/app/AppShell";
import WorkbenchStudy from "../../components/preflop/WorkbenchStudy";
import { useRequireAuth } from "../../lib/hooks/useRequireAuth";

export default function StudyPage() {
  const { isAuthLoading, authError } = useRequireAuth();

  return (
    <AppShell
      title="Study"
      subtitle="Review default preflop charts and the main adjustment points before training."
    >
      {isAuthLoading ? <div style={{ color: "var(--text-65)" }}>Loading study…</div> : null}
      {authError ? <div style={{ color: "var(--accent)", fontWeight: 800 }}>{authError}</div> : null}
      <WorkbenchStudy />
    </AppShell>
  );
}

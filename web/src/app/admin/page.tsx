"use client";

import { useEffect, useMemo, useState, type CSSProperties, type FormEvent } from "react";
import AppShell from "../../components/app/AppShell";
import TrendChart from "../../components/app/TrendChart";
import { API_BASE, apiFetch } from "../../lib/api";
import { useRequireAuth } from "../../lib/hooks/useRequireAuth";

type UserEntry = {
  user_id: string;
  email: string;
  display_name: string | null;
  role: string;
  is_active: boolean;
};

type AssignmentEntry = {
  assignment_id: string;
  title: string;
  target_user_id: string;
  organization_id?: string | null;
  scenario_id: string | null;
  scenario_display_name?: string | null;
  villain_profile_id: string | null;
  villain_display_name?: string | null;
  repetition_target: number;
  status: string;
  due_at: string | null;
  progress: {
    progress_count: number;
    repetition_target: number;
    progress_percent: number;
    status: string;
    is_overdue: boolean;
  };
};

type Option = { id: string; display_name: string };

type AnalyticsPayload = {
  summary: {
    completed_hands: number;
    users_tracked: number;
    assignments_tracked: number;
    avg_overall_score: number | null;
    avg_ranging_score: number | null;
    avg_response_score: number | null;
  };
  trend_points: Array<{ label: string; ranging_score: number | null; response_score: number | null }>;
  users_needing_attention: Array<{ user_id: string; display_name: string; completed_hands: number; avg_ranging_score: number | null; avg_response_score: number | null; overdue_assignments: number; active_assignments: number; is_active: boolean }>;
  strongest_users: Array<{ user_id: string; display_name: string; completed_hands: number; avg_ranging_score: number | null; avg_response_score: number | null }>;
  assignment_status_counts: Record<string, number>;
  insight_drivers: {
    ranging: { low: string; high: string };
    response: { low: string; high: string };
  };
};

type AuditEntry = { audit_log_id: string; action_type: string; created_at: string; target_user_id: string | null };
type OrganizationEntry = { organization_id: string; name: string; slug: string; external_provider: string | null; members: Array<{ user_id: string; display_name: string | null; email: string; membership_role: string }> };
type InviteEntry = { invite_id: string; invite_code: string; email: string | null; role: string; organization_id: string | null; membership_role: string; expires_at: string | null; consumed_at: string | null; status: string; invite_url?: string; email_delivery?: { status?: string; detail?: string | null } | null };
type TabKey = "analytics" | "assignments" | "members";

const PALETTE = { cream: "#F0EBE0", coral: "#E76F51", green: "#6A9E72", muted: "rgba(240,235,224,0.45)", soft: "rgba(240,235,224,0.08)" };
const ACCOUNT_ROLE_OPTIONS = ["member", "coach", "admin"] as const;
const ORG_ROLE_OPTIONS = ["member", "coach", "admin", "owner"] as const;

function roleOptionsForUser(canManageRoles: boolean) {
  return canManageRoles ? ACCOUNT_ROLE_OPTIONS : (["member"] as const);
}

export default function AdminPage() {
  const { user, isAuthLoading, authError } = useRequireAuth();
  const [users, setUsers] = useState<UserEntry[]>([]);
  const [assignments, setAssignments] = useState<AssignmentEntry[]>([]);
  const [villains, setVillains] = useState<Option[]>([]);
  const [scenarios, setScenarios] = useState<Option[]>([]);
  const [analytics, setAnalytics] = useState<AnalyticsPayload | null>(null);
  const [auditLogs, setAuditLogs] = useState<AuditEntry[]>([]);
  const [organizations, setOrganizations] = useState<OrganizationEntry[]>([]);
  const [invites, setInvites] = useState<InviteEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<TabKey>("analytics");
  const [createState, setCreateState] = useState({ target_user_id: "", title: "", description: "", scenario_id: "", villain_profile_id: "", repetition_target: 20, minimum_overall_score: "", due_at: "" });
  const [externalState, setExternalState] = useState({ user_id: "", provider: "", external_user_id: "", external_email: "" });
  const [orgState, setOrgState] = useState({ name: "", slug: "", external_provider: "", external_org_id: "" });
  const [orgMemberState, setOrgMemberState] = useState({ organization_id: "", user_id: "", membership_role: "member" });
  const [inviteState, setInviteState] = useState({ email: "", role: "member", organization_id: "", expires_in_days: 14 });
  const [bulkInviteState, setBulkInviteState] = useState({ emails: "", role: "member", organization_id: "", expires_in_days: 14 });

  const canManageRoles = user?.role === "owner" || user?.role === "admin";
  const canDeleteUsers = user?.role === "owner";

  const membershipSummaryByUserId = useMemo(() => {
    const summary = new Map<string, string[]>();
    organizations.forEach((org) => {
      org.members.forEach((member) => {
        const next = summary.get(member.user_id) ?? [];
        next.push(`${org.name} (${member.membership_role})`);
        summary.set(member.user_id, next);
      });
    });
    return summary;
  }, [organizations]);

  const inviteOrganizationName = useMemo(() => {
    const summary = new Map<string, string>();
    organizations.forEach((org) => {
      summary.set(org.organization_id, org.name);
    });
    return summary;
  }, [organizations]);

  const memberPerformanceRows = useMemo(() => {
    if (!analytics) return [];

    const byUserId = new Map<string, {
      user_id: string;
      display_name: string;
      completed_hands: number;
      avg_ranging_score: number | null;
      avg_response_score: number | null;
      active_assignments?: number;
      overdue_assignments?: number;
      is_active?: boolean;
    }>();

    analytics.users_needing_attention.forEach((entry) => {
      byUserId.set(entry.user_id, {
        user_id: entry.user_id,
        display_name: entry.display_name,
        completed_hands: entry.completed_hands,
        avg_ranging_score: entry.avg_ranging_score,
        avg_response_score: entry.avg_response_score,
        active_assignments: entry.active_assignments,
        overdue_assignments: entry.overdue_assignments,
        is_active: entry.is_active,
      });
    });

    analytics.strongest_users.forEach((entry) => {
      byUserId.set(entry.user_id, {
        ...(byUserId.get(entry.user_id) ?? {}),
        user_id: entry.user_id,
        display_name: entry.display_name,
        completed_hands: entry.completed_hands,
        avg_ranging_score: entry.avg_ranging_score,
        avg_response_score: entry.avg_response_score,
      });
    });

    users.forEach((entry) => {
      if (!byUserId.has(entry.user_id)) {
        byUserId.set(entry.user_id, {
          user_id: entry.user_id,
          display_name: entry.display_name || entry.email,
          completed_hands: 0,
          avg_ranging_score: null,
          avg_response_score: null,
          is_active: entry.is_active,
        });
      }
    });

    return Array.from(byUserId.values()).sort((a, b) => {
      const aHands = a.completed_hands ?? 0;
      const bHands = b.completed_hands ?? 0;
      if (aHands !== bHands) return bHands - aHands;
      return a.display_name.localeCompare(b.display_name);
    });
  }, [analytics, users]);

  function updateInviteRole(role: string) {
    setInviteState((current) => ({ ...current, role }));
  }

  function updateBulkInviteRole(role: string) {
    setBulkInviteState((current) => ({ ...current, role }));
  }

  async function loadAll() {
    const [usersRes, assignmentsRes, villainsRes, scenariosRes, analyticsRes, auditsRes, orgsRes, invitesRes] = await Promise.all([
      apiFetch(`${API_BASE}/admin/users?limit=50`, { cache: "no-store" }),
      apiFetch(`${API_BASE}/admin/assignments?limit=50`, { cache: "no-store" }),
      apiFetch(`${API_BASE}/villains`, { cache: "no-store" }),
      apiFetch(`${API_BASE}/scenarios`, { cache: "no-store" }),
      apiFetch(`${API_BASE}/admin/analytics`, { cache: "no-store" }),
      apiFetch(`${API_BASE}/admin/audit-logs?limit=50`, { cache: "no-store" }),
      apiFetch(`${API_BASE}/admin/organizations`, { cache: "no-store" }),
      apiFetch(`${API_BASE}/admin/signup-invites?limit=50`, { cache: "no-store" }),
    ]);
    const [usersData, assignmentsData, villainsData, scenariosData, analyticsData, auditsData, orgsData, invitesData] = await Promise.all([
      usersRes.json(), assignmentsRes.json(), villainsRes.json(), scenariosRes.json(), analyticsRes.json(), auditsRes.json(), orgsRes.json(), invitesRes.json(),
    ]);
    if (!usersRes.ok) throw new Error(typeof usersData.detail === "string" ? usersData.detail : "Unable to load users.");
    if (!assignmentsRes.ok) throw new Error(typeof assignmentsData.detail === "string" ? assignmentsData.detail : "Unable to load assignments.");
    if (!villainsRes.ok) throw new Error(typeof villainsData.detail === "string" ? villainsData.detail : "Unable to load villains.");
    if (!scenariosRes.ok) throw new Error(typeof scenariosData.detail === "string" ? scenariosData.detail : "Unable to load scenarios.");
    if (!analyticsRes.ok) throw new Error(typeof analyticsData.detail === "string" ? analyticsData.detail : "Unable to load analytics.");
    if (!auditsRes.ok) throw new Error(typeof auditsData.detail === "string" ? auditsData.detail : "Unable to load audit logs.");
    if (!orgsRes.ok) throw new Error(typeof orgsData.detail === "string" ? orgsData.detail : "Unable to load organizations.");
    if (!invitesRes.ok) throw new Error(typeof invitesData.detail === "string" ? invitesData.detail : "Unable to load invites.");
    setUsers((usersData as { users: UserEntry[] }).users);
    setAssignments((assignmentsData as { assignments: AssignmentEntry[] }).assignments);
    setVillains((villainsData as Array<{ id: string; display_name: string }>).map((item) => ({ id: item.id, display_name: item.display_name })));
    setScenarios((scenariosData as Array<{ id: string; display_name: string }>).map((item) => ({ id: item.id, display_name: item.display_name })));
    setAnalytics(analyticsData as AnalyticsPayload);
    setAuditLogs((auditsData as { audit_logs: AuditEntry[] }).audit_logs);
    setOrganizations((orgsData as { organizations: OrganizationEntry[] }).organizations);
    setInvites((invitesData as { invites: InviteEntry[] }).invites);
  }

  useEffect(() => {
    if (!user) return;
    if (!(user.role === "owner" || user.role === "admin" || user.role === "coach")) {
      setError("You do not have access to Coach tools.");
      return;
    }
    void loadAll().catch((err) => setError(err instanceof Error ? err.message : "Unable to load coach tools."));
  }, [user]);

  async function handleCreateAssignment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null); setNotice(null);
    try {
      const res = await apiFetch(`${API_BASE}/admin/assignments`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(createState) });
      const data = await res.json();
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Unable to create assignment.");
      setCreateState({ target_user_id: "", title: "", description: "", scenario_id: "", villain_profile_id: "", repetition_target: 20, minimum_overall_score: "", due_at: "" });
      setNotice("Assignment created.");
      await loadAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to create assignment.");
    }
  }

  async function handleRoleChange(targetUserId: string, role: string) {
    try {
      const res = await apiFetch(`${API_BASE}/admin/users/${encodeURIComponent(targetUserId)}/role`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ role }) });
      const data = await res.json();
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Unable to update role.");
      setNotice("User role updated.");
      await loadAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to update role.");
    }
  }

  async function handleActiveToggle(targetUserId: string, isActive: boolean) {
    try {
      const res = await apiFetch(`${API_BASE}/admin/users/${encodeURIComponent(targetUserId)}/active`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ is_active: isActive }) });
      const data = await res.json();
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Unable to update user status.");
      setNotice(`User ${isActive ? "reactivated" : "deactivated"}.`);
      await loadAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to update user status.");
    }
  }

  async function handleCreateOrg(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null); setNotice(null);
    try {
      const res = await apiFetch(`${API_BASE}/admin/organizations`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(orgState) });
      const data = await res.json();
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Unable to create organization.");
      setOrgState({ name: "", slug: "", external_provider: "", external_org_id: "" });
      setNotice("Organization created.");
      await loadAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to create organization.");
    }
  }

  async function handleAddOrgMember(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null); setNotice(null);
    try {
      const res = await apiFetch(`${API_BASE}/admin/organizations/${encodeURIComponent(orgMemberState.organization_id)}/members`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ user_id: orgMemberState.user_id, membership_role: orgMemberState.membership_role }) });
      const data = await res.json();
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Unable to add organization member.");
      setOrgMemberState({ organization_id: "", user_id: "", membership_role: "member" });
      setNotice("Organization membership saved.");
      await loadAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to add organization member.");
    }
  }

  async function handleCreateInvite(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null); setNotice(null);
    try {
      const res = await apiFetch(`${API_BASE}/admin/signup-invites`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...inviteState, email: inviteState.email || undefined, organization_id: inviteState.organization_id || undefined, membership_role: inviteState.organization_id ? inviteState.role : undefined }) });
      const data = await res.json();
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Unable to create invite.");
      setInviteState({ email: "", role: "member", organization_id: "", expires_in_days: 14 });
      const invite = (data as { invite: InviteEntry }).invite;
      const deliveryStatus = invite.email_delivery?.status;
      const suffix = deliveryStatus === "sent" ? " · email sent" : invite.invite_url ? ` · share link: ${invite.invite_url}` : "";
      setNotice(`Invite created: ${invite.invite_code}${suffix}`);
      await loadAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to create invite.");
    }
  }


  async function handleCreateBulkInvites(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null); setNotice(null);
    try {
      const res = await apiFetch(`${API_BASE}/admin/signup-invites/bulk`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...bulkInviteState, organization_id: bulkInviteState.organization_id || undefined, membership_role: bulkInviteState.organization_id ? bulkInviteState.role : undefined }) });
      const data = await res.json();
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Unable to create bulk invites.");
      const createdCount = Number((data as { created_count?: number }).created_count ?? 0);
      const failureCount = Array.isArray((data as { failures?: unknown[] }).failures) ? (data as { failures?: unknown[] }).failures!.length : 0;
      setBulkInviteState({ emails: "", role: "member", organization_id: "", expires_in_days: 14 });
      setNotice(`Created ${createdCount} invite${createdCount === 1 ? "" : "s"}${failureCount ? ` · ${failureCount} failed` : ""}.`);
      await loadAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to create bulk invites.");
    }
  }

  async function handleLinkExternal(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null); setNotice(null);
    try {
      const res = await apiFetch(`${API_BASE}/admin/users/${encodeURIComponent(externalState.user_id)}/external-identities`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ provider: externalState.provider, external_user_id: externalState.external_user_id, external_email: externalState.external_email || undefined }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Unable to link external identity.");
      setExternalState({ user_id: "", provider: "", external_user_id: "", external_email: "" });
      setNotice("External identity linked.");
      await loadAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to link external identity.");
    }
  }

  async function handleDeleteUser(targetUserId: string, label: string) {
    if (!canDeleteUsers) return;
    const confirmed = window.confirm(`Delete ${label}? This permanently removes the account and linked memberships, sessions, tokens, and results.`);
    if (!confirmed) return;
    setError(null); setNotice(null);
    try {
      const res = await apiFetch(`${API_BASE}/admin/users/${encodeURIComponent(targetUserId)}`, { method: "DELETE" });
      const data = await res.json();
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Unable to delete user.");
      setNotice(`${label} deleted.`);
      await loadAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to delete user.");
    }
  }

  async function handleDeleteInvite(inviteId: string) {
    const confirmed = window.confirm("Delete this signup invite? Anyone using the link after this will be blocked.");
    if (!confirmed) return;
    setError(null); setNotice(null);
    try {
      const res = await apiFetch(`${API_BASE}/admin/signup-invites/${encodeURIComponent(inviteId)}`, { method: "DELETE" });
      const data = await res.json();
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Unable to delete invite.");
      setNotice("Signup invite deleted.");
      await loadAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to delete invite.");
    }
  }

  async function handleCopyInvite(url: string) {
    try {
      await navigator.clipboard.writeText(url);
      setNotice("Signup link copied.");
    } catch {
      setError("Unable to copy the signup link.");
    }
  }
  const headerStats = analytics ? (
    <>
      <HeaderStat label="Avg villain ranging" value={formatScore(analytics.summary.avg_ranging_score)} tone="coral" />
      <HeaderStat label="Avg action prediction" value={formatScore(analytics.summary.avg_response_score)} tone="green" />
      <HeaderStat label="Assignments" value={analytics.summary.assignments_tracked} tone="neutral" />
    </>
  ) : null;

  return (
    <AppShell title="Coach" subtitle="See what the member pool is struggling with, assign the next reps, and keep operations clean." headerContent={headerStats}>
      {isAuthLoading ? <div style={panelStyle}>Loading coach tools…</div> : null}
      {authError ? <div style={errorStyle}>{authError}</div> : null}
      {error ? <div style={errorStyle}>{error}</div> : null}
      {notice ? <div style={noticeStyle}>{notice}</div> : null}
      {analytics ? (
        <>
          <section style={panelStyle}>
            <div style={tabRowStyle}>
              <TabButton label="Analytics" active={activeTab === "analytics"} onClick={() => setActiveTab("analytics")} />
              <TabButton label="Assignments" active={activeTab === "assignments"} onClick={() => setActiveTab("assignments")} />
              <TabButton label="Members" active={activeTab === "members"} onClick={() => setActiveTab("members")} />
            </div>
          </section>

          {activeTab === "analytics" ? (
            <section style={mainGridStyle}>
              <div style={{ display: "grid", gap: 18 }}>
                <section style={panelStyle}>
                  <SectionHeader eyebrow="Trend" title="Member-pool score progression" />
                  {analytics.trend_points.length ? <TrendChart points={buildRunningAverageTrend(analytics.trend_points)} /> : <EmptyState copy="Complete more finished hands to unlock the pool trend." />}
                </section>
                <section style={panelStyle}>
                  <SectionHeader eyebrow="Member focus" title="Who needs help next" />
                  <div style={stackStyle}>
                    {analytics.users_needing_attention.length ? analytics.users_needing_attention.slice(0, 5).map((entry) => (
                      <MemberRow key={entry.user_id} title={entry.display_name} subtitle={`${entry.completed_hands} hands · ${entry.overdue_assignments} overdue assignments`} ranging={entry.avg_ranging_score} response={entry.avg_response_score} />
                    )) : <EmptyState copy="No members need attention yet." />}
                  </div>
                </section>
                <section style={panelStyle}>
                  <SectionHeader eyebrow="Individual results" title="Member performance snapshot" />
                  <div style={helperCopyStyle}>A coach-facing view of individual member volume, scores, and assignment pressure.</div>
                  <div style={{ ...stackStyle, marginTop: 14 }}>
                    {memberPerformanceRows.length ? memberPerformanceRows.slice(0, 10).map((entry) => (
                      <MemberDetailRow
                        key={entry.user_id}
                        title={entry.display_name}
                        hands={entry.completed_hands}
                        ranging={entry.avg_ranging_score}
                        response={entry.avg_response_score}
                        activeAssignments={entry.active_assignments}
                        overdueAssignments={entry.overdue_assignments}
                        isActive={entry.is_active}
                      />
                    )) : <EmptyState copy="No individual member results yet." />}
                  </div>
                </section>
              </div>
              <div style={{ display: "grid", gap: 18 }}>
                <section style={panelStyle}>
                  <SectionHeader eyebrow="Insights" title="What is driving the pool scores" />
                  <div style={stackStyle}>
                    <InsightCard tone="coral" title="Ranging struggle" copy={analytics.insight_drivers.ranging.low} />
                    <InsightCard tone="green" title="Ranging strength" copy={analytics.insight_drivers.ranging.high} />
                    <InsightCard tone="coral" title="Action-read struggle" copy={analytics.insight_drivers.response.low} />
                    <InsightCard tone="green" title="Action-read strength" copy={analytics.insight_drivers.response.high} />
                  </div>
                </section>
                <section style={panelStyle}>
                  <SectionHeader eyebrow="Top performers" title="Who is excelling" />
                  <div style={stackStyle}>
                    {analytics.strongest_users.length ? analytics.strongest_users.slice(0, 5).map((entry) => (
                      <MemberRow key={entry.user_id} title={entry.display_name} subtitle={`${entry.completed_hands} hands`} ranging={entry.avg_ranging_score} response={entry.avg_response_score} />
                    )) : <EmptyState copy="No top-performer data yet." />}
                  </div>
                </section>
              </div>
            </section>
          ) : null}

          {activeTab === "assignments" ? (
            <section style={mainGridStyle}>
              <section style={panelStyle}>
                <SectionHeader eyebrow="Create" title="Assign the next reps" />
                <form onSubmit={handleCreateAssignment} style={formGridStyle}>
                  <label style={labelStyle}>Member<select value={createState.target_user_id} onChange={(event) => setCreateState((current) => ({ ...current, target_user_id: event.target.value }))} style={inputStyle} required>
                    <option value="">Select member</option>
                    {users.map((entry) => <option key={entry.user_id} value={entry.user_id}>{entry.display_name || entry.email}</option>)}
                  </select></label>
                  <label style={labelStyle}><span style={labelTitleStyle}>Title <span style={requiredStyle}>*</span></span><input value={createState.title} onChange={(event) => setCreateState((current) => ({ ...current, title: event.target.value }))} style={inputStyle} placeholder="Ex. 25 reps of 3Bet IP vs Tom" required /></label>
                  <label style={labelStyle}>Description<textarea value={createState.description} onChange={(event) => setCreateState((current) => ({ ...current, description: event.target.value }))} style={{ ...inputStyle, minHeight: 92 }} placeholder="Optional assignment note" /></label>
                  <div style={twoColStyle}>
                    <label style={labelStyle}>Scenario<select value={createState.scenario_id} onChange={(event) => setCreateState((current) => ({ ...current, scenario_id: event.target.value }))} style={inputStyle}><option value="">Any scenario</option>{scenarios.map((option) => <option key={option.id} value={option.id}>{option.display_name}</option>)}</select></label>
                    <label style={labelStyle}>Villain<select value={createState.villain_profile_id} onChange={(event) => setCreateState((current) => ({ ...current, villain_profile_id: event.target.value }))} style={inputStyle}><option value="">Any villain</option>{villains.map((option) => <option key={option.id} value={option.id}>{option.display_name}</option>)}</select></label>
                  </div>
                  <div style={threeColStyle}>
                    <label style={labelStyle}>Rep target<input type="number" min={1} value={createState.repetition_target} onChange={(event) => setCreateState((current) => ({ ...current, repetition_target: Number(event.target.value) || 1 }))} style={inputStyle} required /></label>
                    <label style={labelStyle}>Min score<input type="number" min={0} max={100} value={createState.minimum_overall_score} onChange={(event) => setCreateState((current) => ({ ...current, minimum_overall_score: event.target.value }))} style={inputStyle} placeholder="Optional" /></label>
                    <label style={labelStyle}>Due date<input type="date" value={createState.due_at} onChange={(event) => setCreateState((current) => ({ ...current, due_at: event.target.value }))} style={inputStyle} /></label>
                  </div>
                  <button type="submit" style={primaryButtonStyle}>Create assignment</button>
                </form>
              </section>
              <section style={panelStyle}>
                <SectionHeader eyebrow="Queue" title="Active coach assignments" />
                <div style={stackStyle}>
                  {assignments.length ? assignments.slice(0, 8).map((assignment) => (
                    <div key={assignment.assignment_id} style={rowStyle}>
                      <div style={{ minWidth: 0 }}>
                        <div style={rowTitleStyle}>{assignment.title}</div>
                        <div style={rowMetaStyle}>{[assignment.scenario_display_name, assignment.villain_display_name].filter(Boolean).join(" · ") || "Open scope"}</div>
                        <div style={rowHelperStyle}>{assignment.progress.progress_count}/{assignment.progress.repetition_target} reps{assignment.due_at ? ` · due ${new Date(assignment.due_at).toLocaleDateString()}` : ""}</div>
                      </div>
                      <div style={tagStyle}>{assignment.status}</div>
                    </div>
                  )) : <EmptyState copy="No assignments yet." />}
                </div>
              </section>
            </section>
          ) : null}

          {activeTab === "members" ? (
            <section style={mainGridStyle}>
              <section style={{ display: "grid", gap: 18 }}>
                <section style={panelStyle}>
                  <SectionHeader eyebrow="Members" title="Accounts, roles, and organization access" />
                  <div style={helperPanelStyle}>Use signup links for brand-new accounts. Use the role dropdown here for existing accounts. Use organization membership only when you are attaching an existing user to a company roster.</div>
                  <div style={stackStyle}>
                    {users.length ? users.map((entry) => {
                      const memberships = membershipSummaryByUserId.get(entry.user_id) ?? [];
                      return (
                        <div key={entry.user_id} style={memberAdminRowStyle}>
                          <div style={{ minWidth: 0, display: "grid", gap: 8 }}>
                            <div>
                              <div style={rowTitleStyle}>{entry.display_name || entry.email}</div>
                              <div style={rowMetaStyle}>{entry.email}</div>
                            </div>
                            <div style={pillWrapStyle}>
                              <span style={tagStyle}>platform role {entry.role}</span>
                              <span style={entry.is_active ? activeTagStyle : inactiveTagStyle}>{entry.is_active ? "active" : "inactive"}</span>
                              {memberships.length ? memberships.map((membership) => <span key={membership} style={softTagStyle}>{membership}</span>) : <span style={softTagStyle}>No organization linked</span>}
                            </div>
                          </div>
                          <div style={actionClusterStyle}>
                            {canManageRoles ? (
                              <select value={entry.role} onChange={(event) => void handleRoleChange(entry.user_id, event.target.value)} style={compactInputStyle}>
                                <option value="member">member</option>
                                <option value="coach">coach</option>
                                <option value="admin">admin</option>
                                <option value="owner">owner</option>
                              </select>
                            ) : null}
                            {canManageRoles ? <button type="button" onClick={() => void handleActiveToggle(entry.user_id, !entry.is_active)} style={entry.is_active ? dangerButtonStyle : successButtonStyle}>{entry.is_active ? "Deactivate" : "Reactivate"}</button> : null}
                            {canDeleteUsers ? <button type="button" onClick={() => void handleDeleteUser(entry.user_id, entry.display_name || entry.email)} style={deleteButtonStyle}>Delete</button> : null}
                          </div>
                        </div>
                      );
                    }) : <EmptyState copy="No accounts yet." />}
                  </div>
                </section>

                <section style={panelStyle}>
                  <SectionHeader eyebrow="Invites" title="Pending signup links" />
                  <div style={helperCopyStyle}>Keep these links available until the person finishes account setup. Delete old links once they are no longer needed.</div>
                  <div style={{ ...stackStyle, marginTop: 14 }}>
                    {invites.length ? invites.slice(0, 12).map((invite) => (
                      <div key={invite.invite_id} style={inviteCardRowStyle}>
                        <div style={{ minWidth: 0, display: "grid", gap: 8 }}>
                          <div>
                            <div style={rowTitleStyle}>{invite.email || "Open invite"}</div>
                            <div style={pillWrapStyle}>
                              <span style={tagStyle}>platform role {invite.role}</span>
                              {invite.organization_id ? <span style={softTagStyle}>{inviteOrganizationName.get(invite.organization_id || "") || "Organization"}</span> : <span style={softTagStyle}>No organization</span>}
                              {invite.membership_role && invite.organization_id ? <span style={softTagStyle}>roster {invite.membership_role}</span> : null}
                            </div>
                          </div>
                          <div style={inviteUrlStyle}>{invite.invite_url || "Invite link unavailable"}</div>
                          <div style={pillWrapStyle}>
                            <span style={tagStyle}>{invite.status}</span>
                            <span style={softTagStyle}>{invite.expires_at ? `expires ${new Date(invite.expires_at).toLocaleDateString()}` : "no expiry"}</span>
                            <span style={softTagStyle}>code {invite.invite_code}</span>
                          </div>
                        </div>
                        <div style={actionClusterStyle}>
                          {invite.invite_url ? <button type="button" onClick={() => void handleCopyInvite(invite.invite_url!)} style={secondaryButtonStyle}>Copy link</button> : null}
                          <button type="button" onClick={() => void handleDeleteInvite(invite.invite_id)} style={deleteButtonStyle}>Delete link</button>
                        </div>
                      </div>
                    )) : <EmptyState copy="No signup invites yet." />}
                  </div>
                </section>
              </section>
              <section style={{ display: "grid", gap: 18 }}>
                <section style={panelStyle}>
                  <SectionHeader eyebrow="Admin tools" title="Organizations and access setup" />
                  <div style={helperPanelStyle}>Create the organization first, then send signup links. Existing users can be attached later without creating a new account.</div>
                  {canManageRoles ? (
                    <details style={detailsStyle}>
                      <summary style={summaryStyle}>Create organization</summary>
                      <form onSubmit={handleCreateOrg} style={stackStyle}>
                        <input value={orgState.name} onChange={(event) => setOrgState((current) => ({ ...current, name: event.target.value }))} placeholder="Organization name" style={inputStyle} required />
                        <input value={orgState.slug} onChange={(event) => setOrgState((current) => ({ ...current, slug: event.target.value }))} placeholder="organization-slug" style={inputStyle} required />
                        <input value={orgState.external_provider} onChange={(event) => setOrgState((current) => ({ ...current, external_provider: event.target.value }))} placeholder="External provider (optional)" style={inputStyle} />
                        <input value={orgState.external_org_id} onChange={(event) => setOrgState((current) => ({ ...current, external_org_id: event.target.value }))} placeholder="External org ID (optional)" style={inputStyle} />
                        <button type="submit" style={secondaryButtonStyle}>Create organization</button>
                      </form>
                    </details>
                  ) : null}
                  <details style={detailsStyle}>
                    <summary style={summaryStyle}>Add existing user to organization</summary>
                    <form onSubmit={handleAddOrgMember} style={stackStyle}>
                      <select value={orgMemberState.organization_id} onChange={(event) => setOrgMemberState((current) => ({ ...current, organization_id: event.target.value }))} style={inputStyle} required><option value="">Select organization</option>{organizations.map((org) => <option key={org.organization_id} value={org.organization_id}>{org.name}</option>)}</select>
                      <select value={orgMemberState.user_id} onChange={(event) => setOrgMemberState((current) => ({ ...current, user_id: event.target.value }))} style={inputStyle} required><option value="">Select user</option>{users.map((entry) => <option key={entry.user_id} value={entry.user_id}>{entry.display_name || entry.email}</option>)}</select>
                      <label style={labelStyle}><span style={labelTitleStyle}>Organization role</span><select value={orgMemberState.membership_role} onChange={(event) => setOrgMemberState((current) => ({ ...current, membership_role: event.target.value }))} style={inputStyle}>{ORG_ROLE_OPTIONS.map((option) => <option key={option} value={option}>{option}</option>)}</select></label>
                      <button type="submit" style={secondaryButtonStyle}>Save membership</button>
                    </form>
                  </details>
                  <details style={detailsStyle}>
                    <summary style={summaryStyle}>Create signup invite</summary>
                    <form onSubmit={handleCreateInvite} style={stackStyle}>
                      <label style={labelStyle}><span style={labelTitleStyle}>Invite email</span><input value={inviteState.email} onChange={(event) => setInviteState((current) => ({ ...current, email: event.target.value }))} placeholder="Required for account-specific invites" style={inputStyle} /></label>
                      <div style={twoColStyle}>
                        <label style={labelStyle}><span style={labelTitleStyle}>Account role</span><select value={inviteState.role} onChange={(event) => updateInviteRole(event.target.value)} style={inputStyle}>{roleOptionsForUser(canManageRoles).map((option) => <option key={option} value={option}>{option}</option>)}</select></label>
                        <label style={labelStyle}><span style={labelTitleStyle}>Organization</span><select value={inviteState.organization_id} onChange={(event) => setInviteState((current) => ({ ...current, organization_id: event.target.value }))} style={inputStyle}>
                          {canManageRoles ? <option value="">No organization</option> : <option value="">Select organization</option>}
                          {organizations.map((org) => <option key={org.organization_id} value={org.organization_id}>{org.name}</option>)}
                        </select></label>
                      </div>
                      <div style={twoColStyle}>
                        <div />
                        <label style={labelStyle}><span style={labelTitleStyle}>Invite expires in</span><input type="number" min={1} max={90} value={inviteState.expires_in_days} onChange={(event) => setInviteState((current) => ({ ...current, expires_in_days: Number(event.target.value) || 14 }))} placeholder="Expires in days" style={inputStyle} /></label>
                      </div>
                      <div style={helperCopyStyle}>This is the standard onboarding path for a brand-new person. The selected account role is what they will land with after signup. {inviteState.organization_id ? "Choosing an organization will also place them into that roster automatically." : "Choose an organization only when this new account should start inside a company roster."}</div>
                      <button type="submit" style={primaryButtonStyle}>Create invite</button>
                    </form>
                  </details>

                  <details style={detailsStyle}>
                    <summary style={summaryStyle}>Bulk roster invites</summary>
                    <form onSubmit={handleCreateBulkInvites} style={stackStyle}>
                      <label style={labelStyle}><span style={labelTitleStyle}>Email list</span><textarea value={bulkInviteState.emails} onChange={(event) => setBulkInviteState((current) => ({ ...current, emails: event.target.value }))} placeholder="One email per line" style={{ ...inputStyle, minHeight: 140, resize: "vertical" }} required /></label>
                      <div style={twoColStyle}>
                        <label style={labelStyle}><span style={labelTitleStyle}>Account role</span><select value={bulkInviteState.role} onChange={(event) => updateBulkInviteRole(event.target.value)} style={inputStyle}>{roleOptionsForUser(canManageRoles).map((option) => <option key={option} value={option}>{option}</option>)}</select></label>
                        <label style={labelStyle}><span style={labelTitleStyle}>Organization</span><select value={bulkInviteState.organization_id} onChange={(event) => setBulkInviteState((current) => ({ ...current, organization_id: event.target.value }))} style={inputStyle}>
                          {canManageRoles ? <option value="">No organization</option> : <option value="">Select organization</option>}
                          {organizations.map((org) => <option key={org.organization_id} value={org.organization_id}>{org.name}</option>)}
                        </select></label>
                      </div>
                      <div style={twoColStyle}>
                        <div />
                        <label style={labelStyle}><span style={labelTitleStyle}>Invite expires in</span><input type="number" min={1} max={90} value={bulkInviteState.expires_in_days} onChange={(event) => setBulkInviteState((current) => ({ ...current, expires_in_days: Number(event.target.value) || 14 }))} placeholder="Expires in days" style={inputStyle} /></label>
                      </div>
                      <div style={helperCopyStyle}>Use this when a training company sends you a member or coach list. Each new account gets the selected platform role, and choosing an organization places that person into the roster automatically.</div>
                      <button type="submit" style={primaryButtonStyle}>Create bulk invites</button>
                    </form>
                  </details>
                  {canManageRoles ? (
                    <details style={detailsStyle}>
                      <summary style={summaryStyle}>Advanced · link external identity</summary>
                      <form onSubmit={handleLinkExternal} style={stackStyle}>
                        <select value={externalState.user_id} onChange={(event) => setExternalState((current) => ({ ...current, user_id: event.target.value }))} style={inputStyle} required><option value="">Select user</option>{users.map((entry) => <option key={entry.user_id} value={entry.user_id}>{entry.display_name || entry.email}</option>)}</select>
                        <input value={externalState.provider} onChange={(event) => setExternalState((current) => ({ ...current, provider: event.target.value }))} placeholder="Provider" style={inputStyle} required />
                        <input value={externalState.external_user_id} onChange={(event) => setExternalState((current) => ({ ...current, external_user_id: event.target.value }))} placeholder="External user ID" style={inputStyle} required />
                        <input value={externalState.external_email} onChange={(event) => setExternalState((current) => ({ ...current, external_email: event.target.value }))} placeholder="External email (optional)" style={inputStyle} />
                        <button type="submit" style={secondaryButtonStyle}>Link identity</button>
                      </form>
                    </details>
                  ) : null}
                </section>
                <section style={panelStyle}>
                  <SectionHeader eyebrow="Audit" title="Recent admin activity" />
                  <div style={stackStyle}>
                    {auditLogs.length ? auditLogs.slice(0, 6).map((entry) => <div key={entry.audit_log_id} style={rowStyle}><div><div style={rowTitleStyle}>{entry.action_type}</div><div style={rowMetaStyle}>{new Date(entry.created_at).toLocaleString()}</div></div></div>) : <EmptyState copy="No audit events yet." />}
                  </div>
                </section>
              </section>
            </section>
          ) : null}
        </>
      ) : null}
    </AppShell>
  );
}

function HeaderStat({ label, value, tone, helper }: { label: string; value: string | number; tone: "coral" | "green" | "neutral"; helper?: string }) {
  const toneStyle = tone === "coral"
    ? { borderColor: PALETTE.coral, background: PALETTE.coral, color: PALETTE.cream }
    : tone === "green"
      ? { borderColor: PALETTE.green, background: PALETTE.green, color: "#141210" }
      : { borderColor: "var(--line)", background: "var(--surface-fill-strong)", color: PALETTE.cream };
  return <div style={{ ...headerStatStyle, ...toneStyle }}><div style={headerStatLabelStyle}>{label}</div><div style={headerStatValueStyle}>{value}</div>{helper ? <div style={headerStatHelperStyle}>{helper}</div> : null}</div>;
}

function SectionHeader({ eyebrow, title }: { eyebrow: string; title: string }) {
  return <div style={sectionHeaderStyle}><div style={eyebrowStyle}>{eyebrow}</div><h2 style={sectionTitleStyle}>{title}</h2></div>;
}
function TabButton({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) { return <button type="button" onClick={onClick} style={active ? activeTabButtonStyle : tabButtonStyle}>{label}</button>; }
function InsightCard({ tone, title, copy }: { tone: "coral" | "green"; title: string; copy: string }) {
  const parsed = parseInsight(copy);
  return (
    <div style={insightCardStyle}>
      <div style={{ ...eyebrowStyle, color: tone === "coral" ? PALETTE.coral : PALETTE.green }}>{title}</div>
      <div style={insightFocusStyle}>{parsed.focus}</div>
      <div style={insightCopyStyle}>{parsed.detail}</div>
    </div>
  );
}
function MemberRow({ title, subtitle, ranging, response }: { title: string; subtitle: string; ranging: number | null; response: number | null }) {
  return <div style={rowStyle}><div style={{ minWidth: 0 }}><div style={rowTitleStyle}>{title}</div><div style={rowMetaStyle}>{subtitle}</div></div><div style={memberMetricWrapStyle}><MetricPill label="Range" value={ranging} tone="coral" /><MetricPill label="Action" value={response} tone="green" /></div></div>;
}
function MemberDetailRow({ title, hands, ranging, response, activeAssignments, overdueAssignments, isActive }: { title: string; hands: number; ranging: number | null; response: number | null; activeAssignments?: number; overdueAssignments?: number; isActive?: boolean }) {
  const assignmentCopy = activeAssignments != null || overdueAssignments != null
    ? `${activeAssignments ?? 0} active · ${overdueAssignments ?? 0} overdue`
    : "No assignment pressure yet";
  return (
    <div style={memberDetailRowStyle}>
      <div style={{ minWidth: 0 }}>
        <div style={rowTitleStyle}>{title}</div>
        <div style={rowMetaStyle}>{hands} finished hands · {assignmentCopy}</div>
        {isActive === false ? <div style={{ ...rowMetaStyle, color: PALETTE.coral }}>Inactive account</div> : null}
      </div>
      <div style={memberDetailScoreWrapStyle}>
        <MetricPill label="Range" value={ranging} tone="coral" />
        <MetricPill label="Action" value={response} tone="green" />
      </div>
    </div>
  );
}
function MetricPill({ label, value, tone }: { label: string; value: number | null; tone: "coral" | "green" }) { return <div style={{ ...metricPillStyle, color: tone === "coral" ? PALETTE.coral : PALETTE.green }}>{label} {formatScore(value)}</div>; }
function EmptyState({ copy }: { copy: string }) { return <div style={emptyStateStyle}>{copy}</div>; }
function parseInsight(copy: string) {
  const marker = ' is ';
  const idx = copy.indexOf(marker);
  if (idx === -1) return { focus: copy, detail: '' };
  return { focus: copy.slice(0, idx), detail: copy.slice(idx + 1) };
}


function average(values: Array<number | null | undefined>): number | null {
  const nums = values.filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  if (!nums.length) return null;
  return nums.reduce((sum, value) => sum + value, 0) / nums.length;
}

function buildRunningAverageTrend(points: AnalyticsPayload["trend_points"]) {
  const seenRanges: number[] = [];
  const seenResponses: number[] = [];
  return points.map((point, index) => {
    if (point.ranging_score != null) seenRanges.push(point.ranging_score);
    if (point.response_score != null) seenResponses.push(point.response_score);
    return { label: `${point.label} #${index + 1}`, ranging: average(seenRanges), response: average(seenResponses) };
  });
}

function formatScore(value: number | null | undefined) { return value == null ? "—" : `${Math.round(value)}`; }

const panelStyle: CSSProperties = { borderTop: "1px solid var(--line-soft)", paddingTop: 18 };
const errorStyle: CSSProperties = { color: "var(--accent)", fontWeight: 700 };
const noticeStyle: CSSProperties = { color: "var(--success)", fontWeight: 700 };
const tabRowStyle: CSSProperties = { display: "flex", gap: 10, flexWrap: "wrap" };
const tabButtonStyle: CSSProperties = { padding: "11px 18px", borderRadius: 999, border: "1px solid var(--line)", background: "transparent", color: PALETTE.cream, fontWeight: 700 };
const activeTabButtonStyle: CSSProperties = { padding: "11px 18px", borderRadius: 999, border: `1px solid ${PALETTE.coral}`, background: PALETTE.coral, color: PALETTE.cream, fontWeight: 700 };
const mainGridStyle: CSSProperties = { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 430px), 1fr))", gap: 24, alignItems: "start" };
const sectionHeaderStyle: CSSProperties = { display: "grid", gap: 8, marginBottom: 16 };
const eyebrowStyle: CSSProperties = { color: PALETTE.coral, fontSize: 12, textTransform: "uppercase", letterSpacing: 1.3, fontWeight: 900 };
const sectionTitleStyle: CSSProperties = { margin: 0, fontSize: 26, lineHeight: 1.08 };
const headerStatStyle: CSSProperties = { width: 188, minHeight: 92, borderRadius: 18, padding: "14px 16px", border: "1px solid var(--line)", background: "rgba(20,18,16,1)", display: "flex", flexDirection: "column", justifyContent: "space-between" };
const headerStatLabelStyle: CSSProperties = { color: "inherit", opacity: 0.9, fontSize: 11, textTransform: "uppercase", letterSpacing: 1.1, fontWeight: 800 };
const headerStatValueStyle: CSSProperties = { marginTop: 6, fontSize: 28, fontWeight: 900, color: "inherit" };
const headerStatHelperStyle: CSSProperties = { marginTop: 4, opacity: 0.88, fontSize: 12, lineHeight: 1.45 };
const stackStyle: CSSProperties = { display: "grid", gap: 12 };
const rowStyle: CSSProperties = { display: "flex", justifyContent: "space-between", gap: 14, alignItems: "center", paddingTop: 14, borderTop: "1px solid var(--line-soft)" };
const memberAdminRowStyle: CSSProperties = { ...rowStyle, alignItems: "flex-start", padding: "18px 18px", border: "1px solid var(--line)", borderRadius: 18, background: "var(--surface-fill)", boxShadow: "0 10px 24px rgba(0,0,0,0.16)" };
const memberDetailRowStyle: CSSProperties = { display: "grid", gridTemplateColumns: "minmax(0, 1fr) auto", gap: 16, alignItems: "center", padding: "16px 18px", border: "1px solid var(--line)", borderRadius: 18, background: "var(--surface-fill)", boxShadow: "0 10px 24px rgba(0,0,0,0.14)" };
const memberDetailScoreWrapStyle: CSSProperties = { display: "flex", gap: 8, justifyContent: "flex-end", flexWrap: "wrap" };
const rowTitleStyle: CSSProperties = { fontWeight: 800, fontSize: 15, color: PALETTE.cream };
const rowMetaStyle: CSSProperties = { color: PALETTE.muted, fontSize: 13, marginTop: 4, lineHeight: 1.5 };
const rowHelperStyle: CSSProperties = { color: "rgba(240,235,224,0.65)", fontSize: 13, lineHeight: 1.55, marginTop: 4 };
const memberMetricWrapStyle: CSSProperties = { display: "grid", gap: 8, justifyItems: "end" };
const metricPillStyle: CSSProperties = { padding: "6px 10px", borderRadius: 999, border: "1px solid var(--line)", background: "var(--surface-fill)", fontWeight: 800, fontSize: 12 };
const insightCardStyle: CSSProperties = { padding: 16, borderRadius: 16, background: "var(--surface-fill)", border: "1px solid var(--line)" };
const insightFocusStyle: CSSProperties = { marginTop: 8, fontSize: 22, fontWeight: 900, color: PALETTE.cream, lineHeight: 1.12 };
const insightCopyStyle: CSSProperties = { marginTop: 8, color: "rgba(240,235,224,0.65)", lineHeight: 1.65 };
const formGridStyle: CSSProperties = { display: "grid", gap: 14 };
const twoColStyle: CSSProperties = { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 220px), 1fr))", gap: 12 };
const threeColStyle: CSSProperties = { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 150px), 1fr))", gap: 12 };
const labelStyle: CSSProperties = { display: "grid", gap: 8, color: PALETTE.cream, fontSize: 14 };
const labelTitleStyle: CSSProperties = { display: "inline-flex", alignItems: "center", gap: 6 };
const inputStyle: CSSProperties = { width: "100%", padding: "11px 12px", borderRadius: 12, border: "1px solid var(--line)", background: "var(--surface-fill)", color: PALETTE.cream };
const compactInputStyle: CSSProperties = { ...inputStyle, width: 120, padding: "9px 10px" };
const requiredStyle: CSSProperties = { color: PALETTE.coral, fontWeight: 900 };
const primaryButtonStyle: CSSProperties = { padding: "11px 15px", borderRadius: 14, border: "1px solid rgba(231,111,81,0.45)", background: "var(--accent)", color: PALETTE.cream, fontWeight: 800 };
const secondaryButtonStyle: CSSProperties = { padding: "10px 14px", borderRadius: 14, border: `1px solid ${PALETTE.coral}`, background: PALETTE.coral, color: PALETTE.cream, fontWeight: 800 };
const successButtonStyle: CSSProperties = { padding: "10px 14px", borderRadius: 14, border: `1px solid ${PALETTE.green}`, background: PALETTE.green, color: "#141210", fontWeight: 800 };
const dangerButtonStyle: CSSProperties = { padding: "10px 14px", borderRadius: 14, border: `1px solid ${PALETTE.coral}`, background: PALETTE.coral, color: PALETTE.cream, fontWeight: 800 };
const deleteButtonStyle: CSSProperties = { padding: "10px 14px", borderRadius: 14, border: "1px solid rgba(164, 64, 48, 0.8)", background: "#7C2D22", color: PALETTE.cream, fontWeight: 800 };
const helperCopyStyle: CSSProperties = { color: "rgba(240,235,224,0.62)", lineHeight: 1.6, fontSize: 13 };
const tagStyle: CSSProperties = { padding: "6px 10px", borderRadius: 999, background: "var(--surface-fill)", border: "1px solid var(--line)", color: PALETTE.cream, fontSize: 12, fontWeight: 800, textTransform: "uppercase" };
const actionWrapStyle: CSSProperties = { display: "flex", gap: 10, alignItems: "center", justifyContent: "flex-end", flexWrap: "wrap" };
const actionClusterStyle: CSSProperties = { display: "flex", gap: 10, alignItems: "center", justifyContent: "flex-end", flexWrap: "wrap" };
const pillWrapStyle: CSSProperties = { display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" };
const softTagStyle: CSSProperties = { padding: "6px 10px", borderRadius: 999, background: "rgba(240,235,224,0.06)", border: "1px solid var(--line)", color: "rgba(240,235,224,0.72)", fontSize: 12, fontWeight: 700 };
const activeTagStyle: CSSProperties = { ...tagStyle, background: PALETTE.green, border: `1px solid ${PALETTE.green}`, color: "#141210" };
const inactiveTagStyle: CSSProperties = { ...tagStyle, background: "rgba(231,111,81,0.14)", border: `1px solid rgba(231,111,81,0.55)`, color: PALETTE.coral };
const inviteCardRowStyle: CSSProperties = { display: "flex", justifyContent: "space-between", gap: 14, alignItems: "flex-start", padding: "16px 18px", borderRadius: 18, border: "1px solid var(--line)", background: "var(--surface-fill)" };
const inviteUrlStyle: CSSProperties = { fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace", fontSize: 12, lineHeight: 1.55, color: "rgba(240,235,224,0.72)", wordBreak: "break-all" };
const detailsStyle: CSSProperties = { marginTop: 12, borderRadius: 18, border: "1px solid rgba(231,111,81,0.28)", background: "linear-gradient(180deg, rgba(231,111,81,0.08), rgba(20,18,16,0.98))", padding: 14, boxShadow: "0 12px 30px rgba(0,0,0,0.18)" };
const summaryStyle: CSSProperties = { cursor: "pointer", fontWeight: 900, color: PALETTE.cream, marginBottom: 12, fontSize: 17, listStyle: "none", padding: "10px 12px", borderRadius: 14, border: "1px solid rgba(231,111,81,0.26)", background: "rgba(231,111,81,0.12)" };
const emptyStateStyle: CSSProperties = { color: PALETTE.muted, padding: "8px 0 4px", lineHeight: 1.6 };
const helperPanelStyle: CSSProperties = { padding: "14px 16px", borderRadius: 16, border: "1px solid var(--line)", background: "var(--surface-fill)", color: "rgba(240,235,224,0.7)", lineHeight: 1.65, fontSize: 13 };

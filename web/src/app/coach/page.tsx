"use client";

import { useEffect, useMemo, useState, type CSSProperties, type FormEvent } from "react";
import Link from "next/link";
import AppShell from "../../components/app/AppShell";
import ReviewQueuePanel from "../../components/coach/ReviewQueuePanel";
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
  weakest_scenarios: ScoreBreakdown[];
  weakest_villains: ScoreBreakdown[];
  cohort_completion: Array<{ cohort_id: string; organization_id: string; name: string; coach_user_ids?: string[]; coach_names?: string[]; member_count: number; assignment_count: number; completed_assignments: number; active_assignments: number; overdue_assignments: number; completion_rate: number | null; completed_reps: number; target_reps: number; rep_completion_rate: number | null }>;
  overdue_assignments: AssignmentEntry[];
  assignment_status_counts: Record<string, number>;
  insight_drivers: {
    ranging: { low: string; high: string };
    response: { low: string; high: string };
  };
};

type ScoreBreakdown = { key: string; label: string; hands: number; overall_score: number | null; ranging_score: number | null; response_score: number | null };
type AccountabilityDigest = {
  period: { days: number; from: string; to: string };
  summary: {
    active_members: number;
    members_trained: number;
    members_missed: number;
    completed_hands: number;
    active_assignments: number;
    overdue_assignments: number;
  };
  missed_members: Array<{ user_id: string; display_name: string; email: string; hands: number }>;
  weakest_members: Array<{ user_id: string; display_name: string; email: string; hands: number; avg_overall_score: number | null }>;
  weak_spots: Array<{ label: string; hands: number; avg_overall_score: number | null; avg_ranging_score: number | null; avg_response_score: number | null }>;
  overdue_assignments: Array<{ assignment_id: string; title: string; target_user_id: string; progress?: { progress_count: number; repetition_target: number } }>;
};

type AuditEntry = { audit_log_id: string; action_type: string; created_at: string; target_user_id: string | null };
type OrganizationEntry = { organization_id: string; name: string; slug: string; external_provider: string | null; metadata?: { logo_url?: string; invite_landing_copy?: string; brand_accent?: string; coach_roster_note?: string }; members: Array<{ user_id: string; display_name: string | null; email: string; membership_role: string }> };
type InviteEntry = { invite_id: string; invite_code: string; email: string | null; role: string; organization_id: string | null; membership_role: string; expires_at: string | null; consumed_at: string | null; status: string; invite_url?: string; email_delivery?: { status?: string; detail?: string | null } | null };
type CohortEntry = { cohort_id: string; organization_id: string; name: string; description: string | null; status: string; member_count: number; coach_user_ids?: string[]; coaches?: Array<{ user_id: string; email: string; display_name: string | null; role: string; is_active: boolean }> };
type DataDeliveryPreference = { cadence: string; include_member_summary: boolean; include_cohort_summary: boolean; include_org_summary: boolean; cohort_id: string | null; last_sent_at?: string | null; next_send_at?: string | null; updated_at?: string | null };
type TabKey = "analytics" | "assignments" | "review" | "reporting";

const PALETTE = { cream: "#F0EBE0", coral: "#E76F51", green: "#6A9E72", muted: "rgba(240,235,224,0.45)", soft: "rgba(240,235,224,0.08)" };
const EMPTY_ANALYTICS: AnalyticsPayload = {
  summary: {
    completed_hands: 0,
    users_tracked: 0,
    assignments_tracked: 0,
    avg_overall_score: null,
    avg_ranging_score: null,
    avg_response_score: null,
  },
  trend_points: [],
  users_needing_attention: [],
  strongest_users: [],
  weakest_scenarios: [],
  weakest_villains: [],
  cohort_completion: [],
  overdue_assignments: [],
  assignment_status_counts: {},
  insight_drivers: {
    ranging: {
      low: "Complete more member reps to surface the pool's biggest range leak.",
      high: "Complete more member reps to surface the pool's strongest range spot.",
    },
    response: {
      low: "Complete more member reps to surface the pool's biggest action leak.",
      high: "Complete more member reps to surface the pool's strongest action spot.",
    },
  },
};
const ACCOUNT_ROLE_OPTIONS = ["member", "coach", "admin"] as const;
const ORG_ROLE_OPTIONS = ["member", "coach", "admin", "owner"] as const;
const ADMIN_PAGE_SIZE = 500;
const ADMIN_COLLECTION_CAP = 500;
const ADMIN_TOOL_DISCLOSURE_CSS = `
  .admin-tool-disclosure > summary::-webkit-details-marker { display: none; }
  .admin-tool-disclosure > summary::marker { content: ""; }
  .admin-tool-caret {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 18px;
    min-width: 18px;
    height: 18px;
    color: var(--text-main, #F0EBE0);
    font-size: 18px;
    font-weight: 900;
    line-height: 1;
    transform: rotate(0deg);
    transform-origin: center;
    transition: transform 140ms ease;
  }
  .admin-tool-disclosure[open] > summary .admin-tool-caret {
    transform: rotate(90deg);
  }
`;

function roleOptionsForUser(canManageRoles: boolean) {
  return canManageRoles ? ACCOUNT_ROLE_OPTIONS : (["member"] as const);
}

async function loadPagedCollection<T>(path: string, key: string, cap = ADMIN_COLLECTION_CAP): Promise<T[]> {
  const out: T[] = [];
  let offset = 0;
  let total = Number.POSITIVE_INFINITY;
  while (offset < total && out.length < cap) {
    const sep = path.includes("?") ? "&" : "?";
    const res = await apiFetchWithRetry(`${API_BASE}${path}${sep}limit=${ADMIN_PAGE_SIZE}&offset=${offset}`);
    const data = await res.json();
    if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Unable to load records.");
    const rows = ((data as Record<string, unknown>)[key] ?? []) as T[];
    out.push(...rows);
    const meta = (data as { meta?: { total?: number; limit?: number } }).meta;
    total = typeof meta?.total === "number" ? meta.total : out.length;
    const step = typeof meta?.limit === "number" ? meta.limit : ADMIN_PAGE_SIZE;
    if (rows.length === 0 || step <= 0) break;
    offset += step;
  }
  return out.slice(0, cap);
}

async function loadJson<T>(path: string, fallbackMessage: string): Promise<T> {
  const res = await apiFetchWithRetry(`${API_BASE}${path}`);
  const data = await res.json();
  if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : fallbackMessage);
  return data as T;
}

async function apiFetchWithRetry(input: RequestInfo | URL, attempts = 2): Promise<Response> {
  let lastError: unknown = null;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      return await apiFetch(input, { cache: "no-store" });
    } catch (err) {
      lastError = err;
      if (attempt < attempts - 1) {
        await new Promise((resolve) => window.setTimeout(resolve, 450));
      }
    }
  }
  throw lastError instanceof Error ? lastError : new Error("Unable to reach Coach tools.");
}

async function loadOptional<T>(loader: () => Promise<T>, fallback: T): Promise<T> {
  try {
    return await loader();
  } catch {
    return fallback;
  }
}

function filenameFromResponse(res: Response, fallback: string) {
  const disposition = res.headers.get("Content-Disposition") || "";
  const match = disposition.match(/filename="?([^";]+)"?/i);
  return match?.[1] || fallback;
}

async function downloadCsvResponse(res: Response, fallbackFilename: string) {
  const blob = await res.blob();
  if (!res.ok) throw new Error("Unable to download CSV.");
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filenameFromResponse(res, fallbackFilename);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

function splitPreferenceCohortIds(value?: string | null) {
  const seen = new Set<string>();
  return String(value || "")
    .split(",")
    .map((item) => item.trim())
    .filter((item) => {
      if (!item || seen.has(item)) return false;
      seen.add(item);
      return true;
    });
}

function joinPreferenceCohortIds(ids: string[]) {
  const seen = new Set<string>();
  const clean = ids.map((id) => id.trim()).filter((id) => {
    if (!id || seen.has(id)) return false;
    seen.add(id);
    return true;
  });
  return clean.length ? clean.join(",") : null;
}

export default function CoachPage() {
  const { user, isAuthLoading, authError } = useRequireAuth();
  const [users, setUsers] = useState<UserEntry[]>([]);
  const [assignments, setAssignments] = useState<AssignmentEntry[]>([]);
  const [villains, setVillains] = useState<Option[]>([]);
  const [scenarios, setScenarios] = useState<Option[]>([]);
  const [analytics, setAnalytics] = useState<AnalyticsPayload | null>(null);
  const [auditLogs, setAuditLogs] = useState<AuditEntry[]>([]);
  const [organizations, setOrganizations] = useState<OrganizationEntry[]>([]);
  const [invites, setInvites] = useState<InviteEntry[]>([]);
  const [cohorts, setCohorts] = useState<CohortEntry[]>([]);
  const [deliveryPreference, setDeliveryPreference] = useState<DataDeliveryPreference | null>(null);
  const [isDeliveryBusy, setIsDeliveryBusy] = useState(false);
  const [isAnalyticsLoading, setIsAnalyticsLoading] = useState(false);
  const [isAssignmentDataLoading, setIsAssignmentDataLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<TabKey>("analytics");
  const [analyticsScope, setAnalyticsScope] = useState("all");
  const [createState, setCreateState] = useState({ target_type: "member", target_user_id: "", cohort_id: "", title: "", description: "", scenario_id: "", villain_profile_id: "", repetition_target: 20, minimum_overall_score: "", due_at: "" });
  const [externalState, setExternalState] = useState({ user_id: "", provider: "", external_user_id: "", external_email: "" });
  const [orgState, setOrgState] = useState({ name: "", slug: "", logo_url: "", invite_landing_copy: "", brand_accent: "", coach_roster_note: "", external_provider: "", external_org_id: "" });
  const [orgMemberState, setOrgMemberState] = useState({ organization_id: "", user_id: "", membership_role: "member" });
  const [inviteState, setInviteState] = useState({ email: "", role: "member", organization_id: "", expires_in_days: 14 });
  const [bulkInviteState, setBulkInviteState] = useState({ emails: "", role: "member", organization_id: "", expires_in_days: 14 });

  const canManageRoles = user?.role === "owner" || user?.role === "admin";
  const canCreateOrganizations = user?.role === "owner";
  const canDeleteUsers = user?.role === "owner" || user?.role === "admin";

  useEffect(() => {
    setActiveTab(parseCoachTab(new URLSearchParams(window.location.search).get("tab")));
  }, []);

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

  const userNameById = useMemo(() => {
    const summary = new Map<string, string>();
    users.forEach((entry) => {
      summary.set(entry.user_id, entry.display_name || entry.email);
    });
    return summary;
  }, [users]);

  const assignmentCountByUserId = useMemo(() => {
    const summary = new Map<string, number>();
    assignments.forEach((assignment) => {
      if (assignment.status === "completed") return;
      summary.set(assignment.target_user_id, (summary.get(assignment.target_user_id) ?? 0) + 1);
    });
    return summary;
  }, [assignments]);

  const activeAssignmentsSorted = useMemo(() => {
    return assignments
      .filter((assignment) => assignment.status !== "completed")
      .slice()
      .sort((a, b) => dueSortValue(a.due_at) - dueSortValue(b.due_at) || a.title.localeCompare(b.title));
  }, [assignments]);

  const pendingInvitesSorted = useMemo(() => {
    return invites
      .filter((invite) => invite.status !== "consumed")
      .slice()
      .sort((a, b) => dueSortValue(a.expires_at) - dueSortValue(b.expires_at) || (a.email || "").localeCompare(b.email || ""));
  }, [invites]);

  const auditLogsSorted = useMemo(() => {
    return auditLogs.slice().sort((a, b) => (b.created_at || "").localeCompare(a.created_at || ""));
  }, [auditLogs]);

  const memberPerformanceRows = useMemo(() => {
    if (!analytics) return [];

    const byUserId = new Map<string, {
      user_id: string;
      display_name: string;
      email?: string;
      role?: string;
      completed_hands: number;
      avg_ranging_score: number | null;
      avg_response_score: number | null;
      active_assignments: number;
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
        active_assignments: assignmentCountByUserId.get(entry.user_id) ?? byUserId.get(entry.user_id)?.active_assignments ?? 0,
      });
    });

    users.filter((entry) => entry.role === "member").forEach((entry) => {
      const existing = byUserId.get(entry.user_id);
      byUserId.set(entry.user_id, {
        ...(existing ?? {}),
        user_id: entry.user_id,
        display_name: entry.display_name || entry.email,
        email: entry.email,
        role: entry.role,
        completed_hands: existing?.completed_hands ?? 0,
        avg_ranging_score: existing?.avg_ranging_score ?? null,
        avg_response_score: existing?.avg_response_score ?? null,
        active_assignments: assignmentCountByUserId.get(entry.user_id) ?? existing?.active_assignments ?? 0,
        overdue_assignments: existing?.overdue_assignments ?? 0,
        is_active: entry.is_active,
      });
    });

    return Array.from(byUserId.values())
      .filter((entry) => users.find((userEntry) => userEntry.user_id === entry.user_id)?.role === "member")
      .filter((entry) =>
        (entry.overdue_assignments ?? 0) > 0 ||
        (
          entry.completed_hands >= 2 &&
          combinedScore(entry.avg_ranging_score, entry.avg_response_score) < 80
        )
      )
      .sort((a, b) => combinedScore(a.avg_ranging_score, a.avg_response_score) - combinedScore(b.avg_ranging_score, b.avg_response_score) || a.display_name.localeCompare(b.display_name));
  }, [analytics, users, assignmentCountByUserId]);

  function updateInviteRole(role: string) {
    setInviteState((current) => ({ ...current, role }));
  }

  function updateBulkInviteRole(role: string) {
    setBulkInviteState((current) => ({ ...current, role }));
  }

  async function loadAnalytics(scope = analyticsScope) {
    setIsAnalyticsLoading(true);
    setError(null);
    setAnalytics(EMPTY_ANALYTICS);
    const query = scope !== "all" ? `?cohort_id=${encodeURIComponent(scope)}` : "";
    const analyticsData = await loadOptional(
      () => loadJson<AnalyticsPayload>(`/admin/analytics${query}`, "Unable to load analytics."),
      EMPTY_ANALYTICS,
    );
    setAnalytics(analyticsData);
    setIsAnalyticsLoading(false);
  }

  async function loadCoachLookups() {
    const [orgsData, cohortsData, deliveryData] = await Promise.all([
      loadOptional(() => loadJson<{ organizations: OrganizationEntry[] }>("/admin/organizations", "Unable to load organizations."), { organizations: [] }),
      loadOptional(() => loadJson<{ cohorts: CohortEntry[] }>("/admin/cohorts", "Unable to load cohorts."), { cohorts: [] }),
      loadOptional(() => loadJson<{ preference: DataDeliveryPreference }>("/admin/data-delivery-preferences", "Unable to load delivery settings."), null),
    ]);
    setOrganizations(orgsData.organizations);
    setCohorts(cohortsData.cohorts);
    setDeliveryPreference(deliveryData?.preference ?? null);
  }

  async function loadAssignmentData() {
    setIsAssignmentDataLoading(true);
    const [usersData, assignmentsData, villainsData, scenariosData, orgsData, cohortsData] = await Promise.all([
      loadOptional(() => loadPagedCollection<UserEntry>("/admin/users", "users"), []),
      loadOptional(() => loadPagedCollection<AssignmentEntry>("/admin/assignments", "assignments"), []),
      loadOptional(() => loadJson<Array<{ id: string; display_name: string }>>("/villains", "Unable to load villains."), []),
      loadOptional(() => loadJson<Array<{ id: string; display_name: string }>>("/scenarios", "Unable to load scenarios."), []),
      loadOptional(() => loadJson<{ organizations: OrganizationEntry[] }>("/admin/organizations", "Unable to load organizations."), { organizations: [] }),
      loadOptional(() => loadJson<{ cohorts: CohortEntry[] }>("/admin/cohorts", "Unable to load cohorts."), { cohorts: [] }),
    ]);
    setUsers(usersData);
    setAssignments(assignmentsData);
    setVillains(villainsData.map((item) => ({ id: item.id, display_name: item.display_name })));
    setScenarios(scenariosData.map((item) => ({ id: item.id, display_name: item.display_name })));
    setOrganizations(orgsData.organizations);
    setCohorts(cohortsData.cohorts);
    setIsAssignmentDataLoading(false);
  }

  async function loadAll() {
    await Promise.all([loadAnalytics(), loadCoachLookups()]);
  }

  async function refreshActiveData() {
    await loadAll();
    if (activeTab === "assignments") await loadAssignmentData();
  }

  useEffect(() => {
    if (!user) return;
    if (!(user.role === "owner" || user.role === "admin" || user.role === "coach")) {
      setError("You do not have access to Coach tools.");
      return;
    }
    void loadAll().catch(() => {
      setAnalytics(EMPTY_ANALYTICS);
      setIsAnalyticsLoading(false);
      setError(null);
    });
  }, [user]);

  useEffect(() => {
    if (!user || activeTab !== "assignments") return;
    void loadAssignmentData().catch(() => {
      setIsAssignmentDataLoading(false);
      setError("Unable to load assignment tools.");
    });
  }, [user, activeTab]);

  async function handleCreateAssignment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null); setNotice(null);
    try {
      const payload = {
        title: createState.title,
        description: createState.description,
        scenario_id: createState.scenario_id,
        villain_profile_id: createState.villain_profile_id,
        repetition_target: createState.repetition_target,
        minimum_overall_score: createState.minimum_overall_score,
        due_at: createState.due_at,
        target_user_id: createState.target_user_id,
      };
      const endpoint = createState.target_type === "cohort"
        ? `${API_BASE}/admin/cohorts/${encodeURIComponent(createState.cohort_id)}/assignments`
        : `${API_BASE}/admin/assignments`;
      const res = await apiFetch(endpoint, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      const data = await res.json();
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Unable to create assignment.");
      setCreateState({ target_type: "member", target_user_id: "", cohort_id: "", title: "", description: "", scenario_id: "", villain_profile_id: "", repetition_target: 20, minimum_overall_score: "", due_at: "" });
      const createdCount = Number((data as { created_count?: number }).created_count ?? 1);
      setNotice(createState.target_type === "cohort" ? `Created ${createdCount} assignment${createdCount === 1 ? "" : "s"} for that cohort.` : "Assignment created.");
      await refreshActiveData();
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
      await refreshActiveData();
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
      await refreshActiveData();
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
      setOrgState({ name: "", slug: "", logo_url: "", invite_landing_copy: "", brand_accent: "", coach_roster_note: "", external_provider: "", external_org_id: "" });
      setNotice("Organization created.");
      await refreshActiveData();
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
      await refreshActiveData();
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
      await refreshActiveData();
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
      await refreshActiveData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to create bulk invites.");
    }
  }

  function handleDownloadRosterTemplate() {
    const csv = "email,display_name\nmember1@example.com,Demo Member 1\nmember2@example.com,Demo Member 2\n";
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "range-and-react-roster-template.csv";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }

  async function handleDownloadCohortMembersSummaryCsv() {
    setError(null); setNotice(null);
    try {
      const cohortIds = splitPreferenceCohortIds(deliveryPreference?.cohort_id || cohorts[0]?.cohort_id || "");
      if (!cohortIds.length) throw new Error("Select at least one cohort before downloading a cohort members summary.");
      const params = new URLSearchParams();
      cohortIds.forEach((cohortId) => params.append("cohort_ids", cohortId));
      const res = await apiFetch(`${API_BASE}/admin/cohort-members-summary.csv?${params.toString()}`, { cache: "no-store" });
      await downloadCsvResponse(res, "cohort-members-summary.csv");
      setNotice("Cohort Members Summary.csv downloaded.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to download cohort members summary.");
    }
  }

  async function handleDownloadOrgSummaryCsv() {
    setError(null); setNotice(null);
    try {
      const res = await apiFetch(`${API_BASE}/admin/cohort-summary.csv`, { cache: "no-store" });
      await downloadCsvResponse(res, "org-wide-summary.csv");
      setNotice("Org Wide Summary.csv downloaded.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to download org-wide summary.");
    }
  }

  function updateDeliveryPreference(patch: Partial<DataDeliveryPreference>) {
    setDeliveryPreference((current) => ({
      cadence: "weekly",
      include_member_summary: true,
      include_cohort_summary: false,
      include_org_summary: user?.role === "owner" || user?.role === "admin",
      cohort_id: cohorts[0]?.cohort_id ?? null,
      ...(current ?? {}),
      ...patch,
    }));
  }

  async function handleSaveDeliveryPreference() {
    if (!deliveryPreference) return;
    setError(null); setNotice(null); setIsDeliveryBusy(true);
    try {
      const res = await apiFetch(`${API_BASE}/admin/data-delivery-preferences`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...deliveryPreference,
          include_cohort_summary: false,
          cohort_id: joinPreferenceCohortIds(splitPreferenceCohortIds(deliveryPreference.cohort_id)),
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Unable to save delivery settings.");
      setDeliveryPreference((data as { preference: DataDeliveryPreference }).preference);
      setNotice("Delivery settings saved.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save delivery settings.");
    } finally {
      setIsDeliveryBusy(false);
    }
  }

  async function handleSendDeliveryNow() {
    if (!deliveryPreference) return;
    setError(null); setNotice(null); setIsDeliveryBusy(true);
    try {
      const res = await apiFetch(`${API_BASE}/admin/data-delivery/send`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...deliveryPreference,
          include_cohort_summary: false,
          cohort_id: joinPreferenceCohortIds(splitPreferenceCohortIds(deliveryPreference.cohort_id)),
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Unable to send CSV files.");
      const files = ((data as { files?: Array<{ filename: string }> }).files ?? []).map((item) => item.filename);
      const fileCopy = files.length ? ` ${files.join(", ")}` : "";
      setNotice((data as { queued?: boolean }).queued === false
        ? `Prepared${fileCopy}. Email delivery is not configured in this environment.`
        : `Queued${fileCopy} for email delivery.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to send CSV files.");
    } finally {
      setIsDeliveryBusy(false);
    }
  }

  async function handleRosterCsvUpload(file: File | null) {
    if (!file) return;
    setError(null);
    setNotice(null);
    const text = await file.text();
    const emails = extractEmailsFromCsv(text);
    if (!emails.length) {
      setError("No valid emails were found in that CSV.");
      return;
    }
    setBulkInviteState((current) => ({ ...current, emails: emails.join("\n") }));
    setNotice(`Loaded ${emails.length} email${emails.length === 1 ? "" : "s"} from the roster CSV.`);
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
      await refreshActiveData();
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
      await refreshActiveData();
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
      await refreshActiveData();
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

  function canMaintainEntry(entry: UserEntry) {
    if (!user || entry.user_id === user.user_id) return false;
    if (user.role === "owner") return true;
    if (user.role === "admin") return entry.role !== "owner";
    if (user.role === "coach") return entry.role === "member";
    return false;
  }

  function canRoleEditEntry(entry: UserEntry) {
    if (!user || entry.user_id === user.user_id) return false;
    if (user.role === "owner") return true;
    if (user.role === "admin") return entry.role !== "owner";
    return false;
  }

  function roleOptionsForEntry(entry: UserEntry) {
    if (user?.role === "owner") return ["member", "coach", "admin", "owner"];
    if (user?.role === "admin" && entry.role !== "owner") return ["member", "coach", "admin"];
    return ["member"];
  }

  const headerStats = analytics ? (
    <>
      <HeaderStat label="Avg Range Score" value={formatScore(analytics.summary.avg_ranging_score)} tone="green" />
      <HeaderStat label="Avg Action Score" value={formatScore(analytics.summary.avg_response_score)} tone="coral" />
      <HeaderStat label="Assignments" value={analytics.summary.assignments_tracked} tone="neutral" />
    </>
  ) : null;
  const averageCohortCompletion = analytics ? average(analytics.cohort_completion.map((entry) => entry.rep_completion_rate ?? entry.completion_rate)) : null;
  const weakestScenario = analytics?.weakest_scenarios?.[0] ?? null;
  const weakestVillain = analytics?.weakest_villains?.[0] ?? null;
  const workspaceName = organizations.length === 1 ? organizations[0].name : organizations.length > 1 ? "All workspaces" : "Workspace";
  const nextCoachActions = analytics ? buildCoachNextActions({ analytics, memberNames: userNameById, workspaceName }) : [];
  const selectedDeliveryCohortIds = splitPreferenceCohortIds(deliveryPreference?.cohort_id || cohorts[0]?.cohort_id || "");
  const selectedAnalyticsCohort = cohorts.find((cohort) => cohort.cohort_id === analyticsScope) ?? null;
  const analyticsViewLabel = selectedAnalyticsCohort?.name ?? "Pool-wide";

  function handleAnalyticsScopeChange(nextScope: string) {
    setAnalyticsScope(nextScope);
    void loadAnalytics(nextScope).catch(() => {
      setAnalytics(EMPTY_ANALYTICS);
      setIsAnalyticsLoading(false);
      setError("Unable to load analytics for that view.");
    });
  }

  function handleDeliveryCohortChange(ids: string[]) {
    updateDeliveryPreference({
      cohort_id: joinPreferenceCohortIds(ids),
      include_member_summary: true,
      include_cohort_summary: false,
    });
  }

  return (
    <AppShell title="Coach" subtitle="See what the member pool is struggling with, assign the next reps, and review flagged hands." headerContent={headerStats}>
      <style>{ADMIN_TOOL_DISCLOSURE_CSS}</style>
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
              <TabButton label="Review" active={activeTab === "review"} onClick={() => setActiveTab("review")} />
              <TabButton label="Reporting" active={activeTab === "reporting"} onClick={() => setActiveTab("reporting")} />
            </div>
          </section>

          {activeTab === "analytics" ? (
            <div style={{ display: "grid", gap: 24 }}>
              <section style={panelStyle}>
                <div style={splitSectionHeaderStyle}>
                  <SectionHeader eyebrow={analyticsScope === "all" ? workspaceName : "Cohort analytics"} title={`${analyticsViewLabel} performance`} />
                  <label style={{ ...labelStyle, width: 260 }}>
                    <span style={labelTitleStyle}>Analytics view</span>
                    <select value={analyticsScope} onChange={(event) => handleAnalyticsScopeChange(event.target.value)} style={inputStyle}>
                      <option value="all">Pool-wide</option>
                      {cohorts.map((cohort) => <option key={cohort.cohort_id} value={cohort.cohort_id}>{cohort.name}</option>)}
                    </select>
                  </label>
                </div>
                {isAnalyticsLoading ? <div style={helperCopyStyle}>Updating analytics...</div> : null}
                <div style={digestStatGridStyle}>
                  <DigestStat label="Range Score" value={formatScore(analytics.summary.avg_ranging_score)} />
                  <DigestStat label="Action Score" value={formatScore(analytics.summary.avg_response_score)} />
                  <DigestStat label="Finished reps" value={analytics.summary.completed_hands} />
                  <DigestStat label="Members tracked" value={analytics.summary.users_tracked} />
                </div>
              </section>

              <section style={mainGridStyle}>
                <div style={{ display: "grid", gap: 18 }}>
                <section style={panelStyle}>
                  <SectionHeader eyebrow="Trend" title={`${analyticsViewLabel} score progression`} />
                  {analytics.trend_points.length ? <TrendChart points={buildRunningAverageTrend(analytics.trend_points)} /> : <EmptyState copy="Complete more finished hands to unlock this trend." />}
                </section>
              </div>
              <div style={{ display: "grid", gap: 18 }}>
                <section style={panelStyle}>
                  <SectionHeader eyebrow="Insights" title={`What is driving ${analyticsViewLabel.toLowerCase()} scores`} />
                  <div style={stackStyle}>
                    <InsightCard tone="green" title="Range Score struggle" copy={analytics.insight_drivers.ranging.low} />
                    <InsightCard tone="green" title="Range Score strength" copy={analytics.insight_drivers.ranging.high} />
                    <InsightCard tone="coral" title="Action Score struggle" copy={analytics.insight_drivers.response.low} />
                    <InsightCard tone="coral" title="Action Score strength" copy={analytics.insight_drivers.response.high} />
                  </div>
                </section>
              </div>
              </section>
            </div>
          ) : null}

          {activeTab === "assignments" ? (
            <section style={mainGridStyle}>
              <section style={assignmentPanelStyle}>
                <SectionHeader eyebrow="Create" title="Assign the next reps" />
                <form onSubmit={handleCreateAssignment} style={formGridStyle}>
                  <div style={twoColStyle}>
                    <label style={labelStyle}>Assignment target<select value={createState.target_type} onChange={(event) => setCreateState((current) => ({ ...current, target_type: event.target.value, target_user_id: "", cohort_id: "" }))} style={inputStyle}>
                      <option value="member">Single member</option>
                      <option value="cohort">Cohort</option>
                    </select></label>
                    {createState.target_type === "cohort" ? (
                      <label style={labelStyle}>Cohort<select value={createState.cohort_id} onChange={(event) => setCreateState((current) => ({ ...current, cohort_id: event.target.value }))} style={inputStyle} required>
                        <option value="">Select cohort</option>
                        {cohorts.map((cohort) => <option key={cohort.cohort_id} value={cohort.cohort_id}>{cohort.name} ({cohort.member_count})</option>)}
                      </select></label>
                    ) : (
                      <SearchableUserSelect
                        label="Member"
                        users={users.filter((entry) => entry.role === "member")}
                        value={createState.target_user_id}
                        onChange={(userId) => setCreateState((current) => ({ ...current, target_user_id: userId }))}
                        required
                      />
                    )}
                  </div>
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
                  <button type="submit" style={primaryButtonStyle}>{createState.target_type === "cohort" ? "Assign to cohort" : "Create assignment"}</button>
                </form>
              </section>
              <section style={assignmentPanelStyle}>
                <SectionHeader eyebrow="Queue" title="Active coach assignments" />
                <div style={scrollBoxStyle}>
                  {activeAssignmentsSorted.length ? activeAssignmentsSorted.map((assignment) => (
                    <div key={assignment.assignment_id} style={scrollRowStyle}>
                      <div style={{ minWidth: 0 }}>
                        <div style={rowTitleStyle}>{assignment.title}</div>
                        <div style={rowMetaStyle}>{userNameById.get(assignment.target_user_id) || "Member"}</div>
                        <div style={rowHelperStyle}>{assignment.progress.progress_count}/{assignment.progress.repetition_target} reps{assignment.due_at ? ` · due ${new Date(assignment.due_at).toLocaleDateString()}` : ""}</div>
                      </div>
                      <div style={tagStyle}>{assignment.status}</div>
                    </div>
                  )) : <EmptyState copy="No active assignments yet." />}
                </div>
              </section>
              <section style={assignmentPanelStyle}>
                <div style={splitSectionHeaderStyle}>
                  <SectionHeader eyebrow="Cohort targets" title="Assignment groups" />
                  <Link href="/admin" style={{ ...secondaryButtonStyle, textDecoration: "none" }}>Manage cohorts</Link>
                </div>
                <div style={scrollBoxStyle}>
                  {cohorts.length ? cohorts.map((cohort) => (
                    <div key={cohort.cohort_id} style={scrollRowStyle}>
                      <div style={{ minWidth: 0 }}>
                        <div style={rowTitleStyle}>{cohort.name}</div>
                        <div style={rowMetaStyle}>{inviteOrganizationName.get(cohort.organization_id) || "Organization"} · {cohort.member_count} members</div>
                        <div style={rowHelperStyle}>{cohort.coaches?.length ? `Coaches: ${cohort.coaches.map((coach) => coach.display_name || coach.email).join(", ")}` : "No assigned coach/admin yet"}</div>
                      </div>
                      <span style={tagStyle}>{cohort.status}</span>
                    </div>
                  )) : <EmptyState copy="No cohort targets yet." />}
                </div>
              </section>
            </section>
          ) : null}

          {activeTab === "review" ? (
            <ReviewQueuePanel user={user} />
          ) : null}

          {activeTab === "reporting" ? (
            <div style={{ display: "grid", gap: 24 }}>
              <section style={panelStyle}>
                <div style={splitSectionHeaderStyle}>
                  <SectionHeader eyebrow="Reporting" title="CSV exports" />
                  <div style={actionClusterStyle}>
                    <button type="button" onClick={() => void handleDownloadCohortMembersSummaryCsv()} style={secondaryButtonStyle}>Cohort Members Summary.csv</button>
                    <button type="button" onClick={() => void handleDownloadOrgSummaryCsv()} style={secondaryButtonStyle}>Org Wide Summary.csv</button>
                  </div>
                </div>
                <CohortCheckboxList
                  cohorts={cohorts}
                  selectedIds={selectedDeliveryCohortIds}
                  onChange={handleDeliveryCohortChange}
                />
                <div style={helperCopyStyle}>Cohort Members Summary uses the selected cohort list. Org Wide Summary covers every cohort in your visible workspace.</div>
              </section>

              {deliveryPreference ? (
                <section style={panelStyle}>
                  <div style={splitSectionHeaderStyle}>
                    <SectionHeader eyebrow="Data delivery" title="Email CSV summaries" />
                    <div style={actionClusterStyle}>
                      <button type="button" onClick={() => void handleSaveDeliveryPreference()} disabled={isDeliveryBusy} style={secondaryButtonStyle}>Save settings</button>
                      <button type="button" onClick={() => void handleSendDeliveryNow()} disabled={isDeliveryBusy} style={primaryButtonStyle}>Send now</button>
                    </div>
                  </div>
                  <div style={deliveryGridStyle}>
                    <label style={labelStyle}>
                      <span style={labelTitleStyle}>Cadence</span>
                      <select value={deliveryPreference.cadence} onChange={(event) => updateDeliveryPreference({ cadence: event.target.value })} style={inputStyle}>
                        <option value="weekly">Weekly</option>
                        <option value="biweekly">Every 2 weeks</option>
                        <option value="monthly">Monthly</option>
                      </select>
                    </label>
                    <label style={checkboxRowStyle}>
                      <input type="checkbox" checked={deliveryPreference.include_member_summary} onChange={(event) => updateDeliveryPreference({ include_member_summary: event.target.checked })} />
                      <span>Cohort Members Summary.csv</span>
                    </label>
                    <label style={checkboxRowStyle}>
                      <input type="checkbox" checked={deliveryPreference.include_org_summary} onChange={(event) => updateDeliveryPreference({ include_org_summary: event.target.checked })} />
                      <span>Org Wide Summary.csv</span>
                    </label>
                  </div>
                  <div style={helperCopyStyle}>
                    {deliveryPreference.next_send_at ? `Next scheduled email: ${new Date(deliveryPreference.next_send_at).toLocaleDateString()}.` : "Save settings to schedule recurring delivery."}
                  </div>
                </section>
              ) : null}
            </div>
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
  return <div style={rowStyle}><div style={{ minWidth: 0 }}><div style={rowTitleStyle}>{title}</div><div style={rowMetaStyle}>{subtitle}</div></div><div style={memberMetricWrapStyle}><MetricPill label="Range" value={ranging} tone="green" /><MetricPill label="Action" value={response} tone="coral" /></div></div>;
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
        <MetricPill label="Range" value={ranging} tone="green" />
        <MetricPill label="Action" value={response} tone="coral" />
      </div>
    </div>
  );
}
function MetricPill({ label, value, tone }: { label: string; value: number | null; tone: "coral" | "green" }) { return <div style={{ ...metricPillStyle, color: tone === "coral" ? PALETTE.coral : PALETTE.green }}>{label} {formatScore(value)}</div>; }
function DigestStat({ label, value }: { label: string; value: string | number }) { return <div style={digestStatStyle}><div style={headerStatLabelStyle}>{label}</div><div style={digestStatValueStyle}>{value}</div></div>; }
function CommandRow({ title, meta, right }: { title: string; meta: string; right: string }) {
  return (
    <div style={commandRowStyle}>
      <div style={{ minWidth: 0 }}>
        <div style={rowTitleStyle}>{title}</div>
        <div style={rowMetaStyle}>{meta}</div>
      </div>
      <div style={commandRightStyle}>{right}</div>
    </div>
  );
}
function ScoreBreakdownList({ title, rows }: { title: string; rows: ScoreBreakdown[] }) {
  if (!rows.length) return null;
  return (
    <div style={scoreBreakdownStyle}>
      <div style={rowMetaStyle}>{title}</div>
      {rows.map((row) => (
        <div key={`${title}-${row.key}`} style={scoreBreakdownRowStyle}>
          <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{row.label}</span>
          <span>{formatScore(row.overall_score)}</span>
        </div>
      ))}
    </div>
  );
}
function EmptyState({ copy }: { copy: string }) { return <div style={emptyStateStyle}>{copy}</div>; }

function parseCoachTab(value: string | null): TabKey {
  return value === "assignments" || value === "review" || value === "reporting" ? value : "analytics";
}

function MemberCheckboxList({
  label,
  users,
  selectedIds,
  onChange,
  emptyCopy = "No active members are available.",
}: {
  label: string;
  users: UserEntry[];
  selectedIds: string[];
  onChange: (ids: string[]) => void;
  emptyCopy?: string;
}) {
  const [query, setQuery] = useState("");
  const selected = new Set(selectedIds);
  const normalizedQuery = query.trim().toLowerCase();
  const filteredUsers = normalizedQuery
    ? users.filter((entry) => `${entry.display_name || ""} ${entry.email}`.toLowerCase().includes(normalizedQuery))
    : users;

  function toggle(userId: string) {
    if (selected.has(userId)) {
      onChange(selectedIds.filter((id) => id !== userId));
      return;
    }
    onChange([...selectedIds, userId]);
  }

  return (
    <div style={labelStyle}>
      <span style={labelTitleStyle}>{label}</span>
      <input value={query} onChange={(event) => setQuery(event.target.value)} style={inputStyle} placeholder="Search members" />
      <div style={checkboxListStyle}>
        {filteredUsers.length ? filteredUsers.map((entry) => (
          <label key={entry.user_id} style={checkboxRowStyle}>
            <input
              type="checkbox"
              checked={selected.has(entry.user_id)}
              onChange={() => toggle(entry.user_id)}
            />
            <span>{entry.display_name || entry.email}</span>
          </label>
        )) : <div style={helperCopyStyle}>{users.length ? "No matches." : emptyCopy}</div>}
      </div>
    </div>
  );
}

function CohortCheckboxList({
  cohorts,
  selectedIds,
  onChange,
}: {
  cohorts: CohortEntry[];
  selectedIds: string[];
  onChange: (ids: string[]) => void;
}) {
  const selected = new Set(selectedIds);

  function toggle(cohortId: string) {
    if (selected.has(cohortId)) {
      onChange(selectedIds.filter((id) => id !== cohortId));
      return;
    }
    onChange([...selectedIds, cohortId]);
  }

  return (
    <div style={{ ...labelStyle, marginBottom: 14 }}>
      <span style={labelTitleStyle}>Cohorts included in Cohort Members Summary.csv</span>
      <div style={checkboxListStyle}>
        {cohorts.length ? cohorts.map((cohort) => (
          <label key={cohort.cohort_id} style={checkboxRowStyle}>
            <input
              type="checkbox"
              checked={selected.has(cohort.cohort_id)}
              onChange={() => toggle(cohort.cohort_id)}
            />
            <span>{cohort.name} ({cohort.member_count})</span>
          </label>
        )) : <div style={helperCopyStyle}>Create a cohort to export cohort members.</div>}
      </div>
    </div>
  );
}

function SearchableUserSelect({
  label,
  users,
  value,
  onChange,
  required = false,
}: {
  label: string;
  users: UserEntry[];
  value: string;
  onChange: (value: string) => void;
  required?: boolean;
}) {
  const [query, setQuery] = useState("");
  const normalizedQuery = query.trim().toLowerCase();
  const selectedUser = users.find((entry) => entry.user_id === value) ?? null;
  const filteredUsers = normalizedQuery
    ? users.filter((entry) => `${entry.display_name || ""} ${entry.email}`.toLowerCase().includes(normalizedQuery))
    : users;
  const options = selectedUser && !filteredUsers.some((entry) => entry.user_id === selectedUser.user_id)
    ? [selectedUser, ...filteredUsers]
    : filteredUsers;

  return (
    <label style={labelStyle}>
      {label}
      <input value={query} onChange={(event) => setQuery(event.target.value)} style={inputStyle} placeholder="Search by name or email" />
      <select value={value} onChange={(event) => onChange(event.target.value)} style={inputStyle} required={required}>
        <option value="">Select {label.toLowerCase()}</option>
        {options.map((entry) => <option key={entry.user_id} value={entry.user_id}>{entry.display_name || entry.email}</option>)}
      </select>
    </label>
  );
}

function buildCoachNextActions({ analytics, memberNames, workspaceName }: { analytics: AnalyticsPayload; memberNames: Map<string, string>; workspaceName: string }) {
  const actions: Array<{ title: string; meta: string; right: string }> = [];
  const overdue = analytics.overdue_assignments[0];
  if (overdue) {
    actions.push({
      title: "Nudge overdue work",
      meta: `${memberNames.get(overdue.target_user_id) || "Member"} has ${overdue.title} waiting.`,
      right: `${overdue.progress.progress_count}/${overdue.progress.repetition_target} reps`,
    });
  }
  const weakVillain = analytics.weakest_villains[0];
  if (weakVillain) {
    actions.push({
      title: "Assign opponent-specific reps",
      meta: `${workspaceName} is weakest against ${weakVillain.label}.`,
      right: `Action ${formatScore(weakVillain.response_score)}`,
    });
  }
  const weakScenario = analytics.weakest_scenarios[0];
  if (weakScenario) {
    actions.push({
      title: "Review the weakest scenario",
      meta: `${weakScenario.label} is the lowest scenario in the current pool.`,
      right: `Range ${formatScore(weakScenario.ranging_score)}`,
    });
  }
  const attention = analytics.users_needing_attention.find((entry) => entry.completed_hands > 0);
  if (attention) {
    actions.push({
      title: "Coach a struggling member",
      meta: `${attention.display_name} has the lowest current combined score pressure.`,
      right: `Range ${formatScore(attention.avg_ranging_score)} · Action ${formatScore(attention.avg_response_score)}`,
    });
  }
  return actions.slice(0, 4);
}

function buildCoachReportHtml({
  analytics,
  workspaceName,
  rows,
  nextActions,
}: {
  analytics: AnalyticsPayload;
  workspaceName: string;
  rows: Array<{ display_name: string; completed_hands: number; avg_ranging_score: number | null; avg_response_score: number | null; active_assignments: number; overdue_assignments?: number }>;
  nextActions: Array<{ title: string; meta: string; right: string }>;
}) {
  const generated = new Date().toLocaleString();
  const memberRows = rows.map((row) => `
    <tr>
      <td>${escapeHtml(row.display_name)}</td>
      <td>${row.completed_hands}</td>
      <td>${formatScore(row.avg_ranging_score)}</td>
      <td>${formatScore(row.avg_response_score)}</td>
      <td>${row.active_assignments}</td>
      <td>${row.overdue_assignments ?? 0}</td>
    </tr>
  `).join("");
  const actionRows = nextActions.map((item) => `<li><strong>${escapeHtml(item.title)}</strong><br><span>${escapeHtml(item.meta)} ${escapeHtml(item.right)}</span></li>`).join("");
  return `<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>${escapeHtml(workspaceName)} Coach Report</title>
  <style>
    body { font-family: Inter, Arial, sans-serif; margin: 40px; color: #171412; line-height: 1.45; }
    h1 { margin: 0 0 6px; font-size: 32px; }
    h2 { margin-top: 28px; font-size: 20px; }
    .meta { color: #6b625b; margin-bottom: 24px; }
    .stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 22px 0; }
    .stat { border: 1px solid #ded8ce; border-radius: 10px; padding: 14px; }
    .label { color: #6b625b; font-size: 11px; text-transform: uppercase; letter-spacing: .08em; font-weight: 800; }
    .value { margin-top: 8px; font-size: 26px; font-weight: 900; }
    table { width: 100%; border-collapse: collapse; margin-top: 12px; }
    th, td { border-bottom: 1px solid #ded8ce; padding: 10px 8px; text-align: left; }
    th { font-size: 11px; text-transform: uppercase; letter-spacing: .08em; color: #6b625b; }
    li { margin: 0 0 12px; }
    span { color: #6b625b; }
  </style>
</head>
<body>
  <h1>${escapeHtml(workspaceName)} Coach Report</h1>
  <div class="meta">Generated from Range & React on ${escapeHtml(generated)}</div>
  <div class="stats">
    <div class="stat"><div class="label">Finished reps</div><div class="value">${analytics.summary.completed_hands}</div></div>
    <div class="stat"><div class="label">Range Score</div><div class="value">${formatScore(analytics.summary.avg_ranging_score)}</div></div>
    <div class="stat"><div class="label">Action Score</div><div class="value">${formatScore(analytics.summary.avg_response_score)}</div></div>
    <div class="stat"><div class="label">Overdue work</div><div class="value">${analytics.overdue_assignments.length}</div></div>
  </div>
  <h2>Recommended next actions</h2>
  <ol>${actionRows || "<li>More completed reps will unlock clearer next actions.</li>"}</ol>
  <h2>Member snapshot</h2>
  <table>
    <thead><tr><th>Member</th><th>Reps</th><th>Range Score</th><th>Action Score</th><th>Active</th><th>Overdue</th></tr></thead>
    <tbody>${memberRows || "<tr><td colspan='6'>No member rows yet.</td></tr>"}</tbody>
  </table>
</body>
</html>`;
}

function escapeHtml(value: string) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

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
function formatPercent(value: number | null | undefined) { return value == null ? "—" : `${Math.round(value)}%`; }

function combinedScore(ranging: number | null | undefined, response: number | null | undefined) {
  const values = [ranging, response].filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  if (!values.length) return Number.POSITIVE_INFINITY;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function dueSortValue(value: string | null | undefined) {
  if (!value) return Number.MAX_SAFE_INTEGER;
  const timestamp = Date.parse(value);
  return Number.isFinite(timestamp) ? timestamp : Number.MAX_SAFE_INTEGER;
}

function extractEmailsFromCsv(text: string) {
  const lines = text.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  if (!lines.length) return [];
  const header = lines[0].toLowerCase().split(",").map((item) => item.trim());
  const emailIndex = header.includes("email") ? header.indexOf("email") : 0;
  const rows = header.includes("email") ? lines.slice(1) : lines;
  const emails: string[] = [];
  const seen = new Set<string>();
  for (const row of rows) {
    const cells = row.split(",").map((cell) => cell.trim().replace(/^"|"$/g, ""));
    const email = (cells[emailIndex] || "").toLowerCase();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) || seen.has(email)) continue;
    seen.add(email);
    emails.push(email);
  }
  return emails;
}

const panelStyle: CSSProperties = { borderTop: "1px solid var(--line-soft)", paddingTop: 18 };
const errorStyle: CSSProperties = { color: "var(--accent)", fontWeight: 700 };
const noticeStyle: CSSProperties = { color: "var(--success)", fontWeight: 700 };
const tabRowStyle: CSSProperties = { display: "flex", gap: 10, flexWrap: "wrap" };
const tabButtonStyle: CSSProperties = { padding: "11px 18px", borderRadius: 999, border: "1px solid var(--line)", background: "transparent", color: PALETTE.cream, fontWeight: 700 };
const activeTabButtonStyle: CSSProperties = { padding: "11px 18px", borderRadius: 999, border: `1px solid ${PALETTE.coral}`, background: PALETTE.coral, color: PALETTE.cream, fontWeight: 700 };
const mainGridStyle: CSSProperties = { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 430px), 1fr))", gap: 24, alignItems: "start" };
const commandCenterStyle: CSSProperties = { border: "1px solid var(--line)", borderRadius: 18, padding: 18, background: "rgba(20,18,16,0.52)", display: "grid", gap: 16 };
const commandHeaderStyle: CSSProperties = { display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 14, flexWrap: "wrap" };
const commandGridStyle: CSSProperties = { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 260px), 1fr))", gap: 14 };
const miniPanelStyle: CSSProperties = { border: "1px solid var(--line)", borderRadius: 16, padding: 16, background: "var(--surface-fill)" };
const commandRowStyle: CSSProperties = { display: "grid", gridTemplateColumns: "minmax(0, 1fr) auto", gap: 14, alignItems: "center", paddingTop: 11, borderTop: "1px solid var(--line-soft)" };
const commandRightStyle: CSSProperties = { color: PALETTE.cream, fontSize: 12, fontWeight: 850, textAlign: "right", maxWidth: 150, lineHeight: 1.45 };
const scoreBreakdownStyle: CSSProperties = { display: "grid", gap: 8, paddingTop: 12, borderTop: "1px solid var(--line-soft)" };
const scoreBreakdownRowStyle: CSSProperties = { display: "grid", gridTemplateColumns: "minmax(0, 1fr) auto", gap: 12, color: "rgba(240,235,224,0.72)", fontSize: 13, lineHeight: 1.45 };
const assignmentPanelStyle: CSSProperties = { ...panelStyle, minHeight: 560, display: "grid", alignContent: "start" };
const membersTopPanelStyle: CSSProperties = { ...panelStyle, minHeight: 620, display: "grid", alignContent: "start" };
const scrollBoxStyle: CSSProperties = { maxHeight: 360, overflowY: "auto", display: "grid", gap: 0, border: "1px solid var(--line)", borderRadius: 18, background: "rgba(20,18,16,0.42)" };
const scrollRowStyle: CSSProperties = { display: "flex", justifyContent: "space-between", gap: 16, alignItems: "center", padding: "15px 16px", borderTop: "1px solid var(--line-soft)" };
const memberFocusRowStyle: CSSProperties = { ...scrollRowStyle, textDecoration: "none", color: PALETTE.cream };
const memberFocusMetricWrapStyle: CSSProperties = { display: "flex", gap: 8, justifyContent: "flex-end", flexWrap: "wrap" };
const memberMaintenanceStyle: CSSProperties = { display: "flex", gap: 8, alignItems: "center", justifyContent: "flex-end", flexWrap: "wrap", minWidth: 220 };
const toolStackStyle: CSSProperties = { display: "grid", marginTop: 14 };
const workspacePreviewGridStyle: CSSProperties = { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 260px), 1fr))", gap: 12, marginTop: 14 };
const workspacePreviewStyle: CSSProperties = { display: "grid", gridTemplateColumns: "52px minmax(0, 1fr)", gap: 14, alignItems: "start", padding: 14, borderRadius: 16, border: "1px solid var(--line)", background: "var(--surface-fill)" };
const workspaceLogoStyle: CSSProperties = { width: 52, height: 52, borderRadius: 14, objectFit: "contain", border: "1px solid var(--line)", background: "rgba(240,235,224,0.04)", padding: 6 };
const workspaceLogoFallbackStyle: CSSProperties = { width: 52, height: 52, borderRadius: 14, display: "grid", placeItems: "center", border: "1px solid var(--line)", background: "rgba(231,111,81,0.16)", color: PALETTE.cream, fontWeight: 900 };
const sectionHeaderStyle: CSSProperties = { display: "grid", gap: 8, marginBottom: 16 };
const splitSectionHeaderStyle: CSSProperties = { display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 16, flexWrap: "wrap", marginBottom: 16 };
const eyebrowStyle: CSSProperties = { color: PALETTE.coral, fontSize: 12, textTransform: "uppercase", letterSpacing: 1.3, fontWeight: 900 };
const sectionTitleStyle: CSSProperties = { margin: 0, fontSize: 26, lineHeight: 1.08 };
const headerStatStyle: CSSProperties = { flex: "0 0 188px", width: "100%", maxWidth: 188, minHeight: 92, borderRadius: 18, padding: "14px 16px", border: "1px solid var(--line)", background: "rgba(20,18,16,1)", display: "flex", flexDirection: "column", justifyContent: "space-between" };
const headerStatLabelStyle: CSSProperties = { color: "inherit", opacity: 0.9, fontSize: 11, textTransform: "uppercase", letterSpacing: 1.1, fontWeight: 800 };
const headerStatValueStyle: CSSProperties = { marginTop: 6, fontSize: 28, fontWeight: 900, color: "inherit" };
const headerStatHelperStyle: CSSProperties = { marginTop: 4, opacity: 0.88, fontSize: 12, lineHeight: 1.45 };
const stackStyle: CSSProperties = { display: "grid", gap: 12 };
const digestStatGridStyle: CSSProperties = { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(90px, 1fr))", gap: 10 };
const digestStatStyle: CSSProperties = { minHeight: 82, borderRadius: 14, border: "1px solid var(--line)", background: "var(--surface-fill)", padding: "12px 13px", display: "grid", alignContent: "space-between" };
const digestStatValueStyle: CSSProperties = { marginTop: 7, color: PALETTE.cream, fontSize: 24, fontWeight: 900 };
const deliveryGridStyle: CSSProperties = { display: "grid", gridTemplateColumns: "minmax(min(100%, 210px), 260px) repeat(auto-fit, minmax(min(100%, 190px), 1fr))", gap: 12, alignItems: "end" };
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
const cohortEditorStyle: CSSProperties = { display: "grid", gap: 14, padding: 16, borderRadius: 18, border: "1px solid var(--line)", background: "rgba(20,18,16,0.42)" };
const checkboxListStyle: CSSProperties = { maxHeight: 220, overflowY: "auto", display: "grid", gap: 8, padding: 12, borderRadius: 14, border: "1px solid var(--line)", background: "var(--surface-fill)" };
const checkboxRowStyle: CSSProperties = { display: "grid", gridTemplateColumns: "auto minmax(0, 1fr)", alignItems: "center", gap: 10, color: "rgba(240,235,224,0.82)", lineHeight: 1.45 };
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
const detailsStyle: CSSProperties = { borderTop: "1px solid var(--line-soft)", padding: "14px 0", margin: 0 };
const summaryStyle: CSSProperties = { cursor: "pointer", fontWeight: 900, color: PALETTE.cream, marginBottom: 12, fontSize: 17, listStyle: "none", display: "flex", alignItems: "center", gap: 10 };
const emptyStateStyle: CSSProperties = { color: PALETTE.muted, padding: "8px 0 4px", lineHeight: 1.6 };
const helperPanelStyle: CSSProperties = { padding: "14px 16px", borderRadius: 16, border: "1px solid var(--line)", background: "var(--surface-fill)", color: "rgba(240,235,224,0.7)", lineHeight: 1.65, fontSize: 13 };

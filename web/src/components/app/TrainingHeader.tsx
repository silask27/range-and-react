"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import type { CSSProperties, ReactNode } from "react";
import { API_BASE, apiFetch } from "../../lib/api";
import { clearStoredAuth, getStoredAuthUser } from "../../lib/auth";

type Role = "owner" | "admin" | "coach" | "member";
type NavItem = { href: string; label: string; match: (pathname: string) => boolean; roles?: Role[] };

const NAV_ITEMS: NavItem[] = [
  { href: "/dashboard", label: "Home", match: (pathname) => pathname === "/dashboard" },
  { href: "/account", label: "Account", match: (pathname) => pathname.startsWith("/account") },
  { href: "/screen-1", label: "Train", match: (pathname) => pathname.startsWith("/screen-1") || pathname.startsWith("/screen-3") },
  { href: "/study", label: "Study", match: (pathname) => pathname.startsWith("/study") },
  { href: "/results", label: "Results", match: (pathname) => pathname.startsWith("/results") },
  { href: "/review", label: "Review", match: (pathname) => pathname.startsWith("/review"), roles: ["owner", "admin", "coach"] },
  { href: "/assignments", label: "Assignments", match: (pathname) => pathname.startsWith("/assignments"), roles: ["member"] },
  { href: "/admin", label: "Coach", match: (pathname) => pathname.startsWith("/admin"), roles: ["owner", "admin", "coach"] },
];

export default function TrainingHeader({ stepLabel, title, subtitle, stage, headerContent, subtitleMinHeight }: { stepLabel: string; title: string; subtitle: string; stage?: string; headerContent?: ReactNode; subtitleMinHeight?: CSSProperties["minHeight"] }) {
  const pathname = usePathname() || "/screen-1";
  const router = useRouter();
  const user = getStoredAuthUser();
  const currentRole = ((user?.role as Role | undefined) ?? "member");
  const navItems = NAV_ITEMS.filter((item) => !item.roles || item.roles.includes(currentRole));

  async function handleLogout() {
    try {
      await apiFetch(`${API_BASE}/auth/logout`, { method: "POST" });
    } finally {
      clearStoredAuth();
      router.replace("/login");
    }
  }

  const stageToneClass = stage?.toLowerCase().includes("train mode") ? "badge-primary" : "badge-muted";

  return (
    <>
      <div className="internal-top-nav">
        {navItems.map((item) => {
          const active = item.match(pathname);
          return (
            <Link key={item.href} href={item.href} className={`internal-top-nav__tab${active ? " active" : ""}`}>
              {item.label}
            </Link>
          );
        })}
        <button type="button" onClick={() => void handleLogout()} className="internal-top-nav__tab">Log out</button>
      </div>

      <header className="page-header" style={headerStyle}>
        <div className="page-title-group">
          <div className="page-eyebrow">Train</div>
          <h1 className="page-title">{title}</h1>
          <p className="page-subtitle" style={subtitleMinHeight ? { minHeight: subtitleMinHeight } : undefined}>{subtitle}</p>
        </div>

        {stepLabel || stage || headerContent ? (
          <div className="page-header-side" style={rightStyle}>
            {stepLabel || stage ? (
              <div style={badgeRowStyle}>
                {stepLabel ? <span className="badge badge-muted">{stepLabel}</span> : null}
                {stage ? <span className={`badge ${stageToneClass}`}>{stage}</span> : null}
              </div>
            ) : null}
            {headerContent ? <div style={headerContentStyle}>{headerContent}</div> : null}
          </div>
        ) : null}
      </header>

      <div style={dividerStyle} />
    </>
  );
}

const headerStyle: CSSProperties = { padding: "10px 0 14px" };
const rightStyle: CSSProperties = { display: "grid", gap: 12, justifyItems: "end", alignContent: "start", minWidth: 0 };
const badgeRowStyle: CSSProperties = { display: "flex", gap: 10, flexWrap: "wrap", justifyContent: "flex-end", minWidth: 0 };
const headerContentStyle: CSSProperties = { display: "flex", gap: 12, flexWrap: "wrap", justifyContent: "flex-end", alignItems: "center", minWidth: 0 };
const dividerStyle: CSSProperties = { borderTop: "1px solid var(--line-soft)" };

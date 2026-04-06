"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type CSSProperties, type ReactNode } from "react";
import { API_BASE, apiFetch } from "../../lib/api";
import { clearStoredAuth, getStoredAuthUser } from "../../lib/auth";
import SiteFooter from "./SiteFooter";

type Role = "owner" | "admin" | "coach" | "member";
type NavItem = { href: string; label: string; match: (pathname: string) => boolean; roles?: Role[] };

const NAV_ITEMS: NavItem[] = [
  { href: "/dashboard", label: "Home", match: (pathname) => pathname === "/dashboard" },
  { href: "/account", label: "Account", match: (pathname) => pathname.startsWith("/account") },
  { href: "/screen-1", label: "Train", match: (pathname) => pathname.startsWith("/screen-1") || pathname.startsWith("/screen-3") },
  { href: "/results", label: "Results", match: (pathname) => pathname.startsWith("/results") },
  { href: "/assignments", label: "Assignments", match: (pathname) => pathname.startsWith("/assignments"), roles: ["member"] },
  { href: "/admin", label: "Coach", match: (pathname) => pathname.startsWith("/admin"), roles: ["owner", "admin", "coach"] },
];

const PAGE_LABELS: Record<string, string> = {
  "/dashboard": "Home",
  "/account": "Account",
  "/screen-1": "Train",
  "/screen-3": "Train",
  "/results": "Results",
  "/assignments": "Assignments",
  "/admin": "Coach",
};

export default function AppShell({ children, title, subtitle, headerContent }: { children: ReactNode; title?: string; subtitle?: string; headerContent?: ReactNode }) {
  const pathname = usePathname() || "/dashboard";
  const router = useRouter();
  const [storedRole, setStoredRole] = useState<Role | null>(null);

  useEffect(() => {
    const user = getStoredAuthUser();
    setStoredRole((user?.role as Role | undefined) ?? null);
  }, [pathname]);

  const currentRole = storedRole ?? "member";
  const navItems = NAV_ITEMS.filter((item) => !item.roles || item.roles.includes(currentRole));
  const pageLabel = PAGE_LABELS[Object.keys(PAGE_LABELS).find((key) => pathname.startsWith(key)) || "/dashboard"];

  async function handleLogout() {
    try {
      await apiFetch(`${API_BASE}/auth/logout`, { method: "POST" });
    } finally {
      clearStoredAuth();
      router.replace("/login");
    }
  }

  return (
    <main style={{ minHeight: "100vh", background: "var(--bg)", color: "var(--text)" }}>
      <div className="app-shell">
        <div className="internal-top-nav">
          {navItems.map((item) => {
            const active = item.match(pathname);
            return (
              <Link key={item.href} href={item.href} className={`internal-top-nav__tab${active ? " active" : ""}`}>
                {item.label}
              </Link>
            );
          })}
          <button type="button" onClick={handleLogout} className="internal-top-nav__tab">Log out</button>
        </div>

        <div className="page-stack">
          <header className="page-header">
            <div className="page-title-group">
              <div className="page-eyebrow">{pageLabel}</div>
              <h1 className="page-title">{title ?? pageLabel}</h1>
              {subtitle ? <p className="page-subtitle">{subtitle}</p> : null}
            </div>
            <div style={headerRightStyle}>
              {headerContent ? <div style={headerMetricRowStyle}>{headerContent}</div> : null}
            </div>
          </header>
          {children}
          <SiteFooter compact />
        </div>
      </div>
    </main>
  );
}

const headerRightStyle: CSSProperties = { display: "flex", gap: 12, alignItems: "center", justifyContent: "flex-end", flexWrap: "wrap" };
const headerMetricRowStyle: CSSProperties = { display: "flex", gap: 12, alignItems: "stretch", flexWrap: "wrap", justifyContent: "flex-end" };

"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { getStoredAuthUser } from "../../lib/auth";
import SiteFooter from "./SiteFooter";

type Role = "owner" | "admin" | "coach" | "member";
type NavItem = { href: string; label: string; match: (pathname: string) => boolean; roles?: Role[] };

const NAV_ITEMS: NavItem[] = [
  { href: "/dashboard", label: "Home", match: (pathname) => pathname === "/dashboard" },
  { href: "/screen-1", label: "Train", match: (pathname) => pathname.startsWith("/screen-1") || pathname.startsWith("/screen-3") },
  { href: "/results", label: "Results", match: (pathname) => pathname.startsWith("/results") },
  { href: "/assignments", label: "Assignments", match: (pathname) => pathname.startsWith("/assignments"), roles: ["member"] },
  { href: "/coach", label: "Coach", match: (pathname) => pathname.startsWith("/coach"), roles: ["owner", "admin", "coach"] },
  { href: "/admin", label: "Admin", match: (pathname) => pathname.startsWith("/admin"), roles: ["owner", "admin", "coach"] },
  { href: "/account", label: "Account", match: (pathname) => pathname.startsWith("/account") },
];

const PAGE_LABELS: Record<string, string> = {
  "/dashboard": "Home",
  "/account": "Account",
  "/screen-1": "Train",
  "/screen-3": "Train",
  "/results": "Results",
  "/review": "Review",
  "/assignments": "Assignments",
  "/coach": "Coach",
  "/admin": "Admin",
  "/guide": "Guide",
};

export default function AppShell({ children, title, subtitle, headerContent }: { children: ReactNode; title?: string; subtitle?: string; headerContent?: ReactNode }) {
  const pathname = usePathname() || "/dashboard";
  const [storedRole, setStoredRole] = useState<Role | null>(null);

  useEffect(() => {
    const user = getStoredAuthUser();
    setStoredRole((user?.role as Role | undefined) ?? null);
  }, [pathname]);

  const currentRole = storedRole ?? "member";
  const navItems = NAV_ITEMS.filter((item) => !item.roles || item.roles.includes(currentRole));
  const pageLabel = PAGE_LABELS[Object.keys(PAGE_LABELS).find((key) => pathname.startsWith(key)) || "/dashboard"];

  return (
    <main style={{ minHeight: "100vh", background: "var(--bg)", color: "var(--text)" }}>
      <div className="app-shell">
        <div className="internal-top-nav">
          {navItems.map((item) => {
            const active = item.match(pathname);
            const classes = [
              "internal-top-nav__tab",
              active ? "active" : "",
              item.href === "/screen-1" ? "nav-train-link" : "",
            ].filter(Boolean).join(" ");
            return (
              <Link key={item.href} href={item.href} className={classes}>
                {item.label}
              </Link>
            );
          })}
        </div>

        <div className="page-stack">
          <header className="page-header">
            <div className="page-title-group">
              <div className="page-eyebrow">{pageLabel}</div>
              <h1 className="page-title">{title ?? pageLabel}</h1>
              {subtitle ? <p className="page-subtitle">{subtitle}</p> : null}
            </div>
            <div className="page-header-side">
              {headerContent ? <div className="page-metric-row">{headerContent}</div> : null}
            </div>
          </header>
          {children}
          <SiteFooter compact />
        </div>
      </div>
    </main>
  );
}

import type { ReactNode } from "react";
import SiteFooter from "./SiteFooter";

export default function PublicShell({ title, subtitle, children }: { title: string; subtitle?: string; children: ReactNode }) {
  return (
    <main style={{ minHeight: "100vh", background: "var(--bg)", color: "var(--text)" }}>
      <div className="public-wrap">
        <div className="public-stack">
          <section>
            <div className="page-title-group" style={{ marginBottom: 24 }}>
              <div className="page-eyebrow">Range & React</div>
              <h1 className="page-title">{title}</h1>
              {subtitle ? <p className="page-subtitle">{subtitle}</p> : null}
            </div>
            {children}
          </section>
          <SiteFooter />
        </div>
      </div>
    </main>
  );
}

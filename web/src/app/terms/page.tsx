"use client";

import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import PublicShell from "../../components/app/PublicShell";
import { fetchPublicConfig, type PublicConfig } from "../../lib/publicConfig";

export default function TermsPage() {
  const [config, setConfig] = useState<PublicConfig | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchPublicConfig().then((data) => {
      if (!cancelled) setConfig(data);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const companyName = config?.legal?.company_name ?? config?.app_name ?? "Live Range Lab";
  const supportEmail = config?.legal?.support_email ?? config?.support_email ?? "support@example.com";
  const effectiveDate = config?.legal?.effective_date ?? "2026-04-06";
  const jurisdiction = config?.legal?.jurisdiction ?? "Missouri, USA";

  return (
    <PublicShell
      title="Terms of use"
      subtitle={`Member and coach terms for ${companyName}. Effective ${effectiveDate}.`}
    >
      <div style={{ display: "grid", gap: 18, lineHeight: 1.7, color: "rgba(240,235,224,0.65)" }}>
        <Section title="Training use only">
          This product is an educational training platform designed to help users practice poker thought process, range construction, action anticipation, and assignment review. It does not guarantee financial outcomes and does not replace the user’s own decision-making.
        </Section>
        <Section title="Accounts and access">
          Access may be invite-only and may be managed by a coaching business, team, or platform operator. Users are responsible for maintaining the confidentiality of their credentials. The operator may suspend or revoke access for misuse, abuse, security concerns, or violation of organizational policies.
        </Section>
        <Section title="Coach and admin controls">
          Authorized coaches and admins may create assignments, review results summaries, manage member access, and operate organization-scoped dashboards in line with their configured permissions.
        </Section>
        <Section title="Availability and support">
          The platform is provided on an as-available basis. The operator may perform maintenance, deploy updates, or restrict access when needed to preserve service health or account security. Support requests can be sent to <a href={`mailto:${supportEmail}`} style={{ color: "var(--text)" }}>{supportEmail}</a>.
        </Section>
        <Section title="Governing framework">
          Unless superseded by a separate agreement between the operator and a coaching business, these terms are administered under the operator’s chosen jurisdiction: {jurisdiction}.
        </Section>
        <Section title="Changes">
          These terms may be updated as the platform evolves. The effective date above should be updated whenever materially revised terms are published.
        </Section>
      </div>
    </PublicShell>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section>
      <h2 style={{ margin: "0 0 8px", fontSize: 22 }}>{title}</h2>
      <div>{children}</div>
    </section>
  );
}

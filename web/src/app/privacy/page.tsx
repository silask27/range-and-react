"use client";

import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import PublicShell from "../../components/app/PublicShell";
import { fetchPublicConfig, type PublicConfig } from "../../lib/publicConfig";

export default function PrivacyPage() {
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

  const companyName = config?.legal?.company_name ?? config?.app_name ?? "Range & React";
  const supportEmail = config?.legal?.support_email ?? config?.support_email ?? "support@example.com";
  const effectiveDate = config?.legal?.effective_date ?? "2026-04-06";

  return (
    <PublicShell
      title="Privacy policy"
      subtitle={`How ${companyName} handles account, training, and coaching data. Effective ${effectiveDate}.`}
    >
      <div style={{ display: "grid", gap: 18, lineHeight: 1.7, color: "rgba(240,235,224,0.65)" }}>
        <Section title="What we collect">
          We collect account details such as email address, display name, authentication metadata, invite status, and access role. We also store training activity including sessions, hands, pruning actions, response-matrix entries, assignment progress, and results summaries so members and coaches can review performance over time.
        </Section>
        <Section title="How we use data">
          We use this information to operate the training platform, save progress, measure results, support coach dashboards, manage member access, secure accounts, and improve platform reliability.
        </Section>
        <Section title="Organization visibility">
          When the platform is deployed for a coaching business, authorized coaches and admins may review assignment progress, results summaries, and account metadata for members within their organization. Cross-organization visibility is restricted by role and organization membership.
        </Section>
        <Section title="Retention and deletion">
          Account, training, and results data are retained while an account remains active and as needed for legitimate business operations such as assignments, analytics, support, backup recovery, and audit history. Users can request account export or deletion through the support contact below.
        </Section>
        <Section title="Security and processors">
          The platform uses hosted infrastructure, database storage, transactional email delivery, and monitoring providers selected by the operator. Before public launch, the operator should keep this page aligned with the actual providers in use and the applicable company policy.
        </Section>
        <Section title="Contact">
          Questions about privacy or account data can be sent to <a href={`mailto:${supportEmail}`} style={{ color: "var(--text)" }}>{supportEmail}</a>.
        </Section>
      </div>
    </PublicShell>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section>
      <h2 style={{ margin: "0 0 8px", fontSize: 22, color: "var(--text)", letterSpacing: "-0.02em" }}>{title}</h2>
      <div>{children}</div>
    </section>
  );
}

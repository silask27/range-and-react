import Link from "next/link";
import { APP_NAME } from "../../lib/theme";

const SUPPORT_EMAIL = process.env.NEXT_PUBLIC_SUPPORT_EMAIL ?? "support@example.com";

export default function SiteFooter({ compact = false }: { compact?: boolean }) {
  return (
    <footer className="site-footer" style={compact ? { marginTop: 8 } : undefined}>
      <div>
        <div style={{ fontWeight: 800, color: "var(--text)" }}>{APP_NAME}</div>
        <div>Focused reps for range clarity and action reads.</div>
      </div>
      <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
        <Link href="/privacy">Privacy</Link>
        <Link href="/terms">Terms</Link>
        <Link href="/status">Status</Link>
        <a href={`mailto:${SUPPORT_EMAIL}`}>Support</a>
      </div>
    </footer>
  );
}

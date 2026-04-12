"use client";

import Link from "next/link";
import { useEffect, useState, type CSSProperties, type ReactNode } from "react";
import { getStoredAuthToken } from "../lib/auth";
import SiteFooter from "../components/app/SiteFooter";

const VILLAINS = [
  { src: "/villains/mike.png", name: "Mike", type: "Nit", desc: "Tight, face-up, and under-bluffing. Lets you make disciplined folds and value-bet thinner." },
  { src: "/villains/tom.png", name: "Tom", type: "Calling Station", desc: "Overcalls too often and pays off wider than he should." },
  { src: "/villains/blake.png", name: "Blake", type: "Loose Reg", desc: "Knows the basics, opens wider, and pressures weak passivity." },
  { src: "/villains/dave.png", name: "Dave", type: "Chaser", desc: "Hangs on with draws and weak made hands longer than he should." },
  { src: "/villains/alex.png", name: "Alex", type: "ABC Reg", desc: "Straightforward and structured, but still leaves exploitable patterns." },
  { src: "/villains/steve.png", name: "Steve", type: "Maniac", desc: "Aggressive, splashy, and willing to force action too often." },
  { src: "/villains/erik.png", name: "Erik", type: "Crusher", desc: "Balanced, sharp, and the toughest pool baseline to train against." },
];

const SUMMARY_CARDS = [
  {
    title: "Built for live poker",
    copy: "The goal is not to memorize solver output. It is to make range reading and reaction planning feel automatic at the table.",
  },
  {
    title: "Train the decision loop",
    copy: "Start with a player type, narrow their range street by street, then predict how each bucket responds before you act.",
  },
  {
    title: "Track what improves",
    copy: "Villain Ranging and Action Prediction stay separate, so players and coaches can see what is actually getting better.",
  },
  {
    title: "Coach-ready workflow",
    copy: "Assignments, pool analytics, recent debriefs, and player oversight all live inside one training environment.",
  },
];

export default function LandingPage() {
  const [hasToken, setHasToken] = useState(false);

  useEffect(() => {
    setHasToken(Boolean(getStoredAuthToken()));
  }, []);

  return (
    <main style={pageStyle}>
      <section style={heroStyle}>
        <div style={heroInnerStyle}>
          <div style={heroTextStyle}>
            <div className="page-eyebrow">Range & React</div>
            <h1 style={heroTitleStyle}>
              Know their range. Know their tendencies. Everything else is noise.
            </h1>
            <p style={heroCopyStyle}>
              A focused training site for serious live players and coaches who want reading and reacting to feel automatic when the pressure is on.
            </p>
            <p style={bodyStyle}>
              Most poker mistakes do not come from a lack of knowledge. They come from losing track of what matters in the moment. Range & React drills one repeatable process: narrow the range, predict the reaction, then choose the best line.
            </p>
            <div>
              <Link href={hasToken ? "/dashboard" : "/login"} className="btn-primary" style={ctaStyle}>
                Open the lab
              </Link>
            </div>
          </div>
        </div>
      </section>

      <section style={contentSectionStyle}>
        <div style={sectionShellStyle}>
          <div style={sectionHeaderStyle}>
            <div className="page-eyebrow">Website summary</div>
          </div>
          <div style={statsRowStyle}>
            <Stat value="7" label="Opponent types with real tendencies" />
            <Stat value="5" label="Range buckets you can actually hold in your head" />
            <Stat value="2" label="Core scores that show progress" />
          </div>
          <div style={featureGridStyle}>
            {SUMMARY_CARDS.map((item) => (
              <Feature key={item.title} title={item.title} copy={item.copy} />
            ))}
          </div>
        </div>
      </section>

      <section style={contentSectionStyle}>
        <div style={sectionShellStyle}>
          <div style={sectionHeaderStyle}>
            <div className="page-eyebrow">Meet your opponents</div>
            <h2 style={sectionTitleStyle}>Every villain is built around a real, defined tendency profile.</h2>
            <p style={bodyStyle}>
              The drill changes because the opponent changes. Each player type carries a different betting, calling, raising, and folding pattern, so the habits you train stay tied to how live poker is actually played.
            </p>
          </div>
          <div style={villainGridStyle}>
            {VILLAINS.map((villain) => (
              <div key={villain.name} style={villainCardStyle}>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={villain.src} alt={villain.name} style={villainImageStyle} />
                <div style={{ display: "grid", gap: 6 }}>
                  <div style={villainNameStyle}>{villain.name}</div>
                  <div style={villainMetaStyle}>{villain.type}</div>
                  <div style={villainCopyStyle}>{villain.desc}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section style={contentSectionStyle}>
        <PillarSection
          eyebrow="Core pillar"
          title="Narrowing down their range"
          description={
            <>
              <p style={bodyStyle}>
                Every rep starts with a realistic opponent profile and a live starting range. From there, the lab forces you to keep that range honest as the hand develops.
              </p>
              <p style={bodyStyle}>
                After each action, you remove what no longer fits, save what still survives, and carry that thread forward street by street. The point is not to guess once. It is to stay connected to the range all the way through the hand.
              </p>
            </>
          }
          visual={
            <div style={visualCardStyle}>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src="/range_logo_5x5_v3_no_text.svg" alt="Range & React logo" style={logoVisualStyle} />
            </div>
          }
        />
      </section>

      <section style={contentSectionStyle}>
        <PillarSection
          eyebrow="Core pillar"
          title="Anticipate their action"
          description={
            <>
              <p style={bodyStyle}>
                Once you have narrowed down their range, it is time to anticipate how each part of that range will react to the options in front of you.
              </p>
              <p style={bodyStyle}>
                In the lab, you map each bucket to likely reactions before you act. That turns every decision into a clean what-happens-if exercise, so you can compare lines, understand the likely outcomes, and land at the best decision instead of just a decent one.
              </p>
            </>
          }
          visual={
            <div style={visualCardStyle}>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src="/anticipate_action_icon.png" alt="Anticipate their action icon" style={logoVisualStyle} />
            </div>
          }
          reverse
        />
      </section>

      <div style={{ width: "min(100%, 1280px)", margin: "0 auto", padding: "0 32px 32px" }}>
        <SiteFooter />
      </div>
    </main>
  );
}

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <div style={statStyle}>
      <div style={statValueStyle}>{value}</div>
      <div style={statLabelStyle}>{label}</div>
    </div>
  );
}

function Feature({ title, copy }: { title: string; copy: string }) {
  return (
    <div style={featureStyle}>
      <h3 style={featureTitleStyle}>{title}</h3>
      <p style={bodyStyle}>{copy}</p>
    </div>
  );
}

function PillarSection({
  eyebrow,
  title,
  description,
  visual,
  reverse = false,
}: {
  eyebrow: string;
  title: string;
  description: ReactNode;
  visual: ReactNode;
  reverse?: boolean;
}) {
  const copyBlock = (
    <div style={sectionHeaderStyle}>
      <div className="page-eyebrow">{eyebrow}</div>
      <h2 style={sectionTitleStyle}>{title}</h2>
      <div style={pillarCopyStackStyle}>{description}</div>
    </div>
  );

  return (
    <div style={sectionShellStyle}>
      <div style={{ ...pillarGridStyle, ...(reverse ? pillarReverseStyle : null) }}>
        {reverse ? visual : copyBlock}
        {reverse ? copyBlock : visual}
      </div>
    </div>
  );
}

const pageStyle: CSSProperties = { minHeight: "100vh", background: "var(--bg)", color: "var(--text)" };
const heroStyle: CSSProperties = { minHeight: "100vh", display: "flex", alignItems: "center" };
const heroInnerStyle: CSSProperties = { width: "min(100%, 1280px)", margin: "0 auto", padding: "56px 32px 48px" };
const heroTextStyle: CSSProperties = { display: "grid", gap: 18, maxWidth: 1040 };
const heroTitleStyle: CSSProperties = { margin: 0, fontSize: "clamp(64px, 7vw, 96px)", lineHeight: 0.96, letterSpacing: "-.06em", fontWeight: 840, maxWidth: 1180 };
const heroCopyStyle: CSSProperties = { margin: 0, color: "var(--text-65)", fontSize: 28, lineHeight: 1.45, maxWidth: 980 };
const ctaStyle: CSSProperties = { minHeight: 54, padding: "0 24px", justifySelf: "start" };
const contentSectionStyle: CSSProperties = { width: "min(100%, 1280px)", margin: "0 auto", padding: "0 32px 56px" };
const sectionShellStyle: CSSProperties = { display: "grid", gap: 24, paddingTop: 28, borderTop: "1px solid var(--line-soft)" };
const sectionHeaderStyle: CSSProperties = { display: "grid", gap: 14, maxWidth: 920 };
const sectionTitleStyle: CSSProperties = { margin: 0, fontSize: 44, lineHeight: 1.05, letterSpacing: "-.04em", fontWeight: 800, maxWidth: 900 };
const bodyStyle: CSSProperties = { margin: 0, color: "var(--text-65)", lineHeight: 1.75, fontSize: 18 };
const statsRowStyle: CSSProperties = { display: "grid", gridTemplateColumns: "repeat(3, minmax(0,1fr))", gap: 18 };
const statStyle: CSSProperties = { display: "grid", gap: 8, paddingTop: 18, borderTop: "1px solid var(--line-soft)" };
const statValueStyle: CSSProperties = { fontSize: 58, lineHeight: 1, fontWeight: 840 };
const statLabelStyle: CSSProperties = { color: "var(--text-65)", lineHeight: 1.5, maxWidth: 220 };
const featureGridStyle: CSSProperties = { display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 32 };
const featureStyle: CSSProperties = { display: "grid", gap: 10, paddingTop: 18, borderTop: "1px solid var(--line-soft)" };
const featureTitleStyle: CSSProperties = { margin: 0, fontSize: 32, lineHeight: 1.08, letterSpacing: "-.03em", fontWeight: 800 };
const villainGridStyle: CSSProperties = { display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 22 };
const villainCardStyle: CSSProperties = { display: "grid", gridTemplateColumns: "88px minmax(0,1fr)", gap: 16, alignItems: "start", padding: "16px 0", borderTop: "1px solid var(--line-soft)" };
const villainImageStyle: CSSProperties = { width: 88, height: 88, objectFit: "cover", borderRadius: 999, border: "1px solid var(--line)" };
const villainNameStyle: CSSProperties = { fontSize: 26, fontWeight: 780 };
const villainMetaStyle: CSSProperties = { color: "var(--text-45)", fontSize: 15 };
const villainCopyStyle: CSSProperties = { color: "var(--text-65)", lineHeight: 1.6, fontSize: 15 };
const pillarGridStyle: CSSProperties = { display: "grid", gridTemplateColumns: "minmax(0, 1.05fr) minmax(280px, 0.95fr)", gap: 28, alignItems: "center" };
const pillarReverseStyle: CSSProperties = { gridTemplateColumns: "minmax(280px, 0.95fr) minmax(0, 1.05fr)" };
const pillarCopyStackStyle: CSSProperties = { display: "grid", gap: 14 };
const visualCardStyle: CSSProperties = { minHeight: 260, borderRadius: 28, border: "1px solid var(--line)", background: "var(--surface-fill)", display: "grid", placeItems: "center", padding: 28 };
const logoVisualStyle: CSSProperties = { width: "100%", maxWidth: 300, height: "auto", display: "block" };

"use client";

import Link from "next/link";
import { useEffect, useState, type CSSProperties, type ReactNode } from "react";
import { getStoredAuthToken } from "../lib/auth";
import SiteFooter from "../components/app/SiteFooter";

const VILLAINS = [
  {
    src: "/villains/mike.png",
    name: "Mike",
    type: "Nit",
    desc: "A tight, face-up opponent who under-bluffs, avoids big bets, and rarely goes for thin value.",
  },
  {
    src: "/villains/tom.png",
    name: "Tom",
    type: "Calling Station",
    desc: "A passive, sticky opponent who overcalls across streets, stays fairly inelastic, and is value-heavy when aggressive.",
  },
  {
    src: "/villains/blake.png",
    name: "Blake",
    type: "Loose Reg",
    desc: "A somewhat thinking opponent who opens too wide, overcalls a bit too much, and can become face-up in tougher spots.",
  },
  {
    src: "/villains/dave.png",
    name: "Dave",
    type: "Chaser",
    desc: "A passive, draw-driven opponent who overcalls early streets, value-oriented when aggressive, and wants to see all five cards.",
  },
  {
    src: "/villains/alex.png",
    name: "Alex",
    type: "ABC Reg",
    desc: "A straightforward, slightly winning opponent who is capable of bluffing, but ties aggression to stronger holdings and rarely finds creative lines.",
  },
  {
    src: "/villains/steve.png",
    name: "Steve",
    type: "Maniac",
    desc: "An erratic, action-driven opponent who loves to bluff, hates folding, and is not afraid to play big pots.",
  },
  {
    src: "/villains/erik.png",
    name: "Erik",
    type: "TAG",
    desc: "A sharp, aggressive opponent who is more balanced, applies pressure well, and is the toughest player in the pool to train against.",
  },
];

const SUMMARY_CARDS = [
  {
    title: "Built for live poker",
    copy: "The goal is not to memorize solver output. It is to understand how our opponents arrive at a spot and how they will react.",
  },
  {
    title: "Train the decision loop",
    copy: "Start with a player type, narrow their range street by street, then predict how each bucket responds before you act.",
  },
  {
    title: "Track what improves",
    copy: "Our two core metrics, Villain Ranging and Action Prediction, stay separate so players and coaches can see where players excel, where they struggle, and how they progress over time.",
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
              A training site for serious live players and coaches who want to prioritize focusing on what really matters.
            </p>
            <p style={bodyStyle}>
             Most poker mistakes do not come from a lack of knowledge. They come from losing focus on what matters most in the moment. Range & React helps players develop a repeatable thought process centered around our two core pillars: understanding how previous actions shape an opponent’s current range and how player-specific tendencies affect how that range will react.
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
            <Stat value="7" label="Common live opponent types with real tendencies" />
            <Stat value="5" label="Range buckets you can actually hold in your head" />
            <Stat value="2" label="Core metrics that track progress over time and reveal where players excel or struggle" />
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
              Each opponent has clearly defined tendencies, so training stays centered on the player in front of you, not generic strategy.            </p>
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
                Every rep starts with a selected preflop scenario and a default range tied to that spot. From there, you adjust that starting range based on the specific opponent type you are playing against.
              </p>
              <p style={bodyStyle}>
                As the hand develops, each action gives you new information. You remove what no longer fits, keep what still makes sense, and carry that updated range from preflop all the way to the river.
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
                Once you have an understanding of their current range, it is time to focus on how each part of that range will react to the available actions in front of you.
              </p>
              <p style={bodyStyle}>
                In the training environment, you map how each bucket in your opponent’s range is likely to respond to each action available to you, helping you compare outcomes and choose the best line instead of just a good one.
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

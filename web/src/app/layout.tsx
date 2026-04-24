import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "Range & React",
    template: "%s · Range & React",
  },
  description: "Poker training platform for players and coaches built around opponent range analysis, tendency recognition, and actionable performance insights. Players can see where they struggle, where they excel, and what to practice next, while coaches can track individual and pool performance, spot weaknesses, and assign targeted reps."
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

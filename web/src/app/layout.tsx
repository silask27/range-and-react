import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "Live Range Lab",
    template: "%s · Live Range Lab",
  },
  description: "Poker training platform for live range reading, action prediction, assignments, and coach-ready results.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

import type { Metadata } from "next";
import "./studio.css";
import "./query-studio.css";

export const metadata: Metadata = {
  title: "ArchPilot",
  description: "Evidence-driven multi-agent architecture decisions",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

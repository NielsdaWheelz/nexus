import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Nexus",
  description: "Reading-first knowledge management system",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

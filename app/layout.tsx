import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Omid · Content Studio",
  description: "Dein privates Studio für AI-gestützte Shorts. Skript entwerfen, prüfen und als vertikales Video produzieren.",
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="de">
      <body className="antialiased">{children}</body>
    </html>
  );
}

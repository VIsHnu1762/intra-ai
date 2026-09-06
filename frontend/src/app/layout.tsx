import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Intra AI — Adaptive Multi-Agent Voice Interview Platform",
  description:
    "Next-generation conversational AI hiring platform powered by multi-agent interviews, real-time voice intelligence, and adaptive competency assessment.",
  keywords: [
    "Intra AI",
    "AI voice interview",
    "multi-agent assessment",
    "Agora real-time voice",
    "adaptive interview",
    "engineering hiring",
  ],
  openGraph: {
    title: "Intra AI — Adaptive Multi-Agent Voice Interview Platform",
    description:
      "Conduct adaptive multi-agent AI voice interviews with real-time competency analysis and evidence-backed evaluation.",
    type: "website",
  },
  icons: {
    icon: [
      { url: "/favicon.ico", sizes: "any" },
      { url: "/intra-ai-logo.png", type: "image/png" },
    ],
    shortcut: "/favicon.ico",
    apple: "/apple-icon.png",
  },
};

import { QueryProvider } from "@/context/QueryProvider";
import { AuthProvider } from "@/context/AuthContext";

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={inter.variable}>
      <body className="font-sans antialiased">
        <QueryProvider>
          <AuthProvider>{children}</AuthProvider>
        </QueryProvider>
      </body>
    </html>
  );
}

import type { Metadata } from "next";
import "./globals.css";
import "./creative-director.css";
export const metadata: Metadata = { title: "AI Clip Factory — Free local video editing.", description: "Create vertical clips from authorized videos with local FFmpeg processing, manual review, and optional subtitle files. No paid AI API is required." };
export default function RootLayout({ children }: Readonly<{children: React.ReactNode}>) { return <html lang="en"><body>{children}</body></html>; }

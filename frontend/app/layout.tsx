import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = { title: "AI Clip Factory — Creative control. At cloud speed.", description: "Turn authorized source videos into distinctive, campaign-ready clips. Analyze, create, review, and publish in one workspace." };
export default function RootLayout({ children }: Readonly<{children: React.ReactNode}>) { return <html lang="en"><body>{children}</body></html>; }

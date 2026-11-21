import type { NextConfig } from "next";
const browserMode = process.env.NEXT_PUBLIC_BROWSER_MODE === "true";
const nextConfig: NextConfig = {
  ...(browserMode ? {} : { async rewrites() { return [{ source: "/api/:path*", destination: `${process.env.API_ORIGIN || "http://127.0.0.1:8000"}/api/:path*` }]; } }),
  output: browserMode ? "export" : "standalone",
  basePath: browserMode ? process.env.NEXT_PUBLIC_BASE_PATH || "" : "",
  trailingSlash: browserMode,
  images: { unoptimized: browserMode },
  poweredByHeader: false,
  devIndicators: false,
  async headers() { return [{ source: "/:path*", headers: [
    { key: "X-Content-Type-Options", value: "nosniff" },
    { key: "X-Frame-Options", value: "DENY" },
    { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
    { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
  ] }]; },
  experimental: { proxyClientMaxBodySize: process.env.LOCAL_AI_PROXY_SIZE === "1600mb" ? "1600mb" : "510mb", proxyTimeout: 300000 },
};
export default nextConfig;

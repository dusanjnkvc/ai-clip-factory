import type { NextConfig } from "next";
const nextConfig: NextConfig = {
  async rewrites() { return [{ source: "/api/:path*", destination: `${process.env.API_ORIGIN || "http://127.0.0.1:8000"}/api/:path*` }]; },
  output: "standalone",
  poweredByHeader: false,
  devIndicators: false,
  async headers() { return [{ source: "/:path*", headers: [
    { key: "X-Content-Type-Options", value: "nosniff" },
    { key: "X-Frame-Options", value: "DENY" },
    { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
    { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
  ] }]; },
  experimental: { proxyClientMaxBodySize: "510mb", proxyTimeout: 300000 },
};
export default nextConfig;

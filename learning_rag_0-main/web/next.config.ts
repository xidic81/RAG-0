import type { NextConfig } from "next";

// Where the FastAPI backend lives. Rewrites are resolved at build time, so on
// Vercel set API_URL (e.g. your Railway URL) before deploying. Trailing
// slashes are stripped so the destination never ends up with "//".
const apiUrl = (process.env.API_URL ?? "http://localhost:8000").replace(/\/+$/, "");

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiUrl}/:path*` }];
  },
};

export default nextConfig;

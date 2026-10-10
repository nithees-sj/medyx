import path from "node:path";

import { loadEnvConfig } from "@next/env";
import type { NextConfig } from "next";

// One .env for the whole repo: load the root file so NEXT_PUBLIC_* and BACKEND_URL apply here too.
loadEnvConfig(path.resolve(process.cwd(), ".."));

const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  experimental: {
    // Authenticated screens render behind a client-side role check, so they are
    // intentionally not instant. Only validate segments that opt in via `instant`.
    instantInsights: { validationLevel: "manual-warning" },
    // AI requests can wait in the backend's rate limiter, and chat answers stream; the default
    // 30 s rewrite-proxy timeout would cut them off.
    proxyTimeout: 180_000,
  },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  // Same-origin API: the browser only ever talks to :3000, so the httpOnly
  // session cookie set by FastAPI is first-party.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${BACKEND_URL}/api/:path*` }];
  },
};

export default nextConfig;

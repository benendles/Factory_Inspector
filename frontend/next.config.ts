import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  output: "standalone",
  // A dev server and `next build` may run at the same time during local
  // development. Separate caches prevent their manifests and CSS assets from
  // overwriting one another.
  distDir: process.env.NODE_ENV === "development" ? ".next-dev" : ".next",
  // Next 15.5 enables this experimental DevTools view by default. In this
  // project it can produce an invalid RSC client manifest in `next dev`.
  // This changes only the local development overlay, not application code or
  // the production build.
  experimental: {
    devtoolSegmentExplorer: false,
  },
};

export default nextConfig;

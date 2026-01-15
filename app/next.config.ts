import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Enable webpack externals for better-sqlite3
  webpack: (config, { isServer }) => {
    if (isServer) {
      config.externals = [...(config.externals || []), 'better-sqlite3'];
    }
    return config;
  },
};

export default nextConfig;

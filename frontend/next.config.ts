import type { NextConfig } from "next";

const isProd = process.env.NODE_ENV === "production";
const repo = "teamMakeBooks";

const nextConfig: NextConfig = {
  serverExternalPackages: ["js-yaml"],

  // GitHub Pages 정적 배포
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },

  // user.github.io/teamMakeBooks 서브패스 대응
  basePath: isProd ? `/${repo}` : "",
  assetPrefix: isProd ? `/${repo}/` : "",
};

export default nextConfig;

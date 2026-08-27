/** @type {import('next').NextConfig} */
const nextConfig = {
  // EconomyAdvisor 内部工具,关闭 telemetry
  reactStrictMode: true,
  // better-sqlite3 是 native 模块,不要被 webpack 打包,在 Node.js 里 require
  experimental: {
    serverComponentsExternalPackages: ["better-sqlite3"],
  },
  // EconomyWeb 根目录的 data/ 不在 frontend 作用域,但 frontend/lib/db.ts 用了相对路径
  outputFileTracingRoot: require("path").join(__dirname, ".."),
};

module.exports = nextConfig;

import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "EconomyAdvisor · 5 指标看板",
  description: "20-经济-Economy 行业 Web 端 · 5 核心宏观指标速查",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}

/**
 * [INPUT]: 依赖 Vite、@vitejs/plugin-react 与环境变量 VITE_API_PROXY_TARGET
 * [OUTPUT]: 对外提供 Vite React 构建配置与本地 /api 代理
 * [POS]: frontend 的开发服务器边界，避免浏览器 CORS 干扰本地 FastAPI 联调
 * [PROTOCOL]: 变更时更新此头部，然后检查 CLAUDE.md
 */

import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const apiTarget = process.env.VITE_API_PROXY_TARGET || "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: apiTarget,
        changeOrigin: true,
      },
    },
  },
});
